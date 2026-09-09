"""Rendering a sample week: the cards expand, and nulls render as em dashes.

The renderer is pure, so the whole document is available to assert against as
a string. Structure is checked rather than styling: that a click target exists
and points at a card, that the card carries all five sections, that a missing
field prints an em dash instead of `None`, and that nothing hard-fails on a
week with no enrichment at all.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
import tempfile
import unittest

from wheel.enrich import build_enrichment, write_enrichment
from wheel.monitored import SIDECAR_SUFFIX
from wheel.render_html import (
    SIZE_CEILING_BYTES,
    detail_id,
    parse_weekly_screen,
    render_document,
    render_html,
    render_latest,
    size_warning,
    truncate_words,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "enrichment_info_cases.json"
RUN_DATE = "2026-09-06"

MARKDOWN = """# Wheel screen — 2026-09-06

- Funnel: universe 5,334 → stage 1 1,204 → scored 812 → monitored 3

## Monitored tier

| Ticker | Score | Price | Sector | Dividend | Volatility | 2y high | Earnings | Flags |
|---|---|---|---|---|---|---|---|---|
| **FULL** | 88.5 | $11.07 | Consumer Cyclical | 5.42% | 31% | 22% below | 2026-10-28 | — |
| **SPARSE** | 74.0 | $28.40 | Industrials | 1.10% | 24% | 8% below | — | earnings soon |
| **EMPTY** | 66.2 | $44.10 | Technology | — | 38% | 3% below | — | — |
| **PLAIN** | 61.0 | $19.55 | Utilities | 2.80% | 19% | 12% below | — | — |

## Flagged
"""

SIDECAR = {
    "run_date": RUN_DATE,
    "entries": {
        "FULL": {"score": 88.5, "zone": "Zone 1", "thesis_backed": False},
        "SPARSE": {"score": 74.0, "zone": "Zone 1", "thesis_backed": True},
        "EMPTY": {"score": 66.2, "zone": "Zone 2", "thesis_backed": False},
        "PLAIN": {"score": 61.0, "zone": "Zone 2", "thesis_backed": False},
    },
}


def info_cases() -> dict[str, dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {key: value for key, value in payload.items() if not key.startswith("_")}


def records(*tickers: str) -> dict[str, dict]:
    """Enrichment for the named cases; PLAIN is deliberately never enriched."""

    cases = info_cases()
    return {
        ticker: build_enrichment(ticker, cases[ticker], fetched_on=date(2026, 9, 6))
        for ticker in tickers
    }


def record_as(ticker: str, case: str) -> dict[str, dict]:
    """One fixture case attached to a ticker the sample week actually lists."""

    return {
        ticker: build_enrichment(
            ticker, info_cases()[case], fetched_on=date(2026, 9, 6)
        )
    }


def document(enrichment: dict | None = None) -> str:
    screen = parse_weekly_screen(MARKDOWN, SIDECAR, frozenset(), enrichment)
    return render_html(screen, net_liq=12000.0, per_name_cap=0.25)


THREE = ("FULL", "SPARSE", "EMPTY")


class ExpansionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = document(records(*THREE))

    def test_each_enriched_row_is_a_click_target_pointing_at_its_card(self) -> None:
        for ticker in THREE:
            with self.subTest(ticker=ticker):
                zone = SIDECAR["entries"][ticker]["zone"]
                target = detail_id(zone, ticker)
                self.assertIn(f'data-expands="{target}"', self.html)
                self.assertIn(f'aria-controls="{target}"', self.html)
                self.assertIn(f'id="{target}" hidden', self.html)

    def test_cards_start_collapsed(self) -> None:
        # Scoped to rows: the stylesheet legitimately mentions the open state.
        rows = re.findall(r"<tr[^>]*>", self.html)
        self.assertEqual(sum('aria-expanded="false"' in row for row in rows), len(THREE))
        self.assertFalse([row for row in rows if 'aria-expanded="true"' in row])

    def test_an_unenriched_row_is_not_a_click_target(self) -> None:
        self.assertIn("PLAIN", self.html)
        self.assertNotIn(detail_id("Zone 2", "PLAIN"), self.html)

    def test_a_row_is_reachable_by_keyboard(self) -> None:
        self.assertIn('role="button" tabindex="0"', self.html)
        self.assertIn("event.key==='Enter'", self.html)

    def test_the_toggle_is_vanilla_and_self_contained(self) -> None:
        self.assertNotIn("<script src=", self.html)
        self.assertNotIn("<link rel=\"stylesheet\"", self.html)
        self.assertIn("document.querySelectorAll('tr[data-expands]')", self.html)

    def test_every_section_is_present_in_a_card(self) -> None:
        for heading in (
            "Financials at a glance",
            "Cash flow and dividends",
            "Analyst view",
            "Leadership",
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"<h4>{heading}</h4>", self.html)

    def test_the_ids_are_unique(self) -> None:
        ids = re.findall(r'id="(detail-[^"]+)"', self.html)
        self.assertEqual(sorted(ids), sorted(set(ids)))

    def test_the_metric_row_reports_enrichment_coverage(self) -> None:
        self.assertIn("<span>Enriched</span><strong>3/4</strong>", self.html)


class BusinessSectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = document(records(*THREE))

    def test_name_website_and_meta_render(self) -> None:
        self.assertIn("<h3>Ford Motor Company</h3>", self.html)
        self.assertIn('href="https://www.ford.com"', self.html)
        self.assertIn(">ford.com<", self.html)
        self.assertIn("Consumer Cyclical · Auto Manufacturers · 177,000 employees", self.html)

    def test_the_summary_is_present_and_bounded(self) -> None:
        self.assertIn("Ford Motor Company develops, delivers, and services", self.html)

    def test_a_card_with_no_name_falls_back_to_the_ticker(self) -> None:
        self.assertIn("<h3>EMPTY</h3>", self.html)

    def test_a_missing_summary_says_so_rather_than_printing_nothing(self) -> None:
        self.assertIn("No business summary available.", self.html)


class NullRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = document(records(*THREE))

    def test_no_python_none_reaches_the_document(self) -> None:
        self.assertNotIn(">None<", self.html)
        self.assertNotIn("None</dd>", self.html)
        self.assertNotIn("nan", self.html.lower().replace("financial", ""))

    def test_missing_numbers_render_as_an_em_dash(self) -> None:
        self.assertIn("<dd>—</dd>", self.html)

    def test_a_fully_null_card_is_all_dashes_but_still_complete(self) -> None:
        empty_card = document(records("EMPTY"))
        self.assertIn("No analyst coverage available.", empty_card)
        self.assertIn("No officer list available.", empty_card)
        self.assertIn("<h4>Financials at a glance</h4>", empty_card)

    def test_analyst_absence_is_stated_and_presence_is_shown(self) -> None:
        self.assertIn("No analyst coverage available.", self.html)  # EMPTY
        self.assertIn("<dt>Analysts covering</dt><dd>21</dd>", self.html)  # FULL
        self.assertIn("<dd>Hold</dd>", self.html)

    def test_a_partial_record_mixes_values_and_dashes(self) -> None:
        sparse = document(records("SPARSE"))
        self.assertIn("<dt>Trailing P/E</dt><dd>18.60</dd>", sparse)
        self.assertIn("<dt>Forward P/E</dt><dd>—</dd>", sparse)
        self.assertIn("<dt>Revenue (TTM)</dt><dd>$812.00M</dd>", sparse)


class FormattingTests(unittest.TestCase):
    def test_large_figures_are_scaled(self) -> None:
        html = document(records("FULL"))
        self.assertIn("<dd>$176.19B</dd>", html)   # revenue
        self.assertIn("<dd>$6.03B</dd>", html)     # free cash flow
        self.assertIn("<dd>$15.42B</dd>", html)    # operating cash flow

    def test_negative_cash_flow_keeps_its_sign(self) -> None:
        self.assertIn("<dd>-$412.00M</dd>", document(record_as("FULL", "MESSY")))

    def test_per_share_figures_carry_a_currency_symbol(self) -> None:
        html = document(records("FULL"))
        self.assertIn("<dt>Revenue per share</dt><dd>$44.28</dd>", html)
        self.assertIn("<dt>Dividend rate</dt><dd>$0.60</dd>", html)
        self.assertIn("<dt>Mean target price</dt><dd>$12.35</dd>", html)

    def test_provider_fractions_render_as_percentages(self) -> None:
        html = document(records("FULL"))
        self.assertIn("<dt>Return on equity</dt><dd>7.7%</dd>", html)
        self.assertIn("<dt>Profit margin</dt><dd>3.2%</dd>", html)
        self.assertIn("<dt>Payout ratio</dt><dd>65.2%</dd>", html)

    def test_a_reported_percentage_is_carried_through_not_multiplied(self) -> None:
        self.assertIn("<dt>Dividend yield</dt><dd>5.42%</dd>", document(records("FULL")))

    def test_the_ex_dividend_date_renders_as_a_date(self) -> None:
        self.assertIn("<dd>2026-11-05</dd>", document(records("FULL")))

    def test_truncate_words_only_adds_an_ellipsis_when_it_cuts(self) -> None:
        self.assertEqual(truncate_words("one two three", 5), "one two three")
        self.assertEqual(truncate_words("one two three", 2), "one two …")
        self.assertEqual(truncate_words(None), "")
        self.assertEqual(truncate_words("   "), "")

    def test_the_summary_is_capped_at_three_hundred_words(self) -> None:
        long_summary = " ".join(f"word{n}" for n in range(900))
        record = build_enrichment(
            "LONG", {"longBusinessSummary": long_summary}, fetched_on=date(2026, 9, 6)
        )
        html = document({"FULL": record})
        body = re.search(r'<p class="summary">(.*?)</p>', html, re.DOTALL)
        self.assertIsNotNone(body)
        self.assertEqual(len(body.group(1).split()), 301)  # 300 words plus the ellipsis
        self.assertNotIn("word300 ", html)


class LeadershipTests(unittest.TestCase):
    def test_officers_render_with_titles(self) -> None:
        html = document(records("FULL"))
        self.assertIn("<strong>Mr. William Clay Ford Jr.</strong><span>Executive Chairman</span>", html)

    def test_a_short_list_shows_no_overflow_note(self) -> None:
        self.assertNotIn("more</p>", document(records("FULL")))

    def test_the_list_caps_at_eight_and_counts_the_rest(self) -> None:
        html = document(record_as("FULL", "MESSY"))
        self.assertEqual(html.count("<li><strong>"), 8)
        self.assertIn("and 4 more", html)


class EscapingTests(unittest.TestCase):
    def test_provider_text_cannot_inject_markup(self) -> None:
        record = build_enrichment(
            "XSS",
            {
                "longName": "<script>alert(1)</script>",
                "longBusinessSummary": "Sells <b>widgets</b> & things.",
                "website": 'https://x.test/"onmouseover="alert(1)',
                "companyOfficers": [{"name": "A & B", "title": "<em>CEO</em>"}],
            },
            fetched_on=date(2026, 9, 6),
        )
        html = document({"FULL": record})
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;widgets&lt;/b&gt; &amp; things.", html)
        self.assertIn("A &amp; B", html)
        self.assertNotIn('"onmouseover="alert(1)"', html)


class SizeCeilingTests(unittest.TestCase):
    def test_a_small_report_carries_no_note(self) -> None:
        self.assertEqual(size_warning(1024), "")
        self.assertEqual(size_warning(SIZE_CEILING_BYTES), "")

    def test_an_oversize_report_names_the_lever(self) -> None:
        note = size_warning(SIZE_CEILING_BYTES + 1)
        self.assertIn("200KB", note)
        self.assertIn("enrichment.top_n", note)

    def test_the_note_lands_in_the_footer_and_the_report_still_renders(self) -> None:
        screen = parse_weekly_screen(MARKDOWN, SIDECAR, frozenset(), records(*THREE))
        html = render_html(
            screen, net_liq=12000.0, per_name_cap=0.25, oversize_note="TOO BIG"
        )
        self.assertIn("TOO BIG", html)
        self.assertIn("<footer>", html)

    def test_a_normal_week_renders_well_under_the_ceiling(self) -> None:
        screen = parse_weekly_screen(MARKDOWN, SIDECAR, frozenset(), records(*THREE))
        html, note = render_document(screen, net_liq=12000.0, per_name_cap=0.25)
        self.assertEqual(note, "")
        self.assertLess(len(html.encode("utf-8")), SIZE_CEILING_BYTES)

    def test_fifty_enriched_candidates_stay_under_the_ceiling(self) -> None:
        """The stated design target: 50 cards in one file, under 200KB."""

        case = info_cases()["FULL"]
        entries = {}
        enrichment = {}
        rows = []
        for index in range(50):
            ticker = f"T{index:02d}"
            entries[ticker] = {
                "score": 90.0 - index,
                "zone": "Zone 1",
                "thesis_backed": False,
            }
            enrichment[ticker] = build_enrichment(
                ticker, case, fetched_on=date(2026, 9, 6)
            )
            rows.append(
                f"| **{ticker}** | {90.0 - index:.1f} | $11.07 | Consumer Cyclical "
                "| 5.42% | 31% | 22% below | 2026-10-28 | — |"
            )
        markdown = MARKDOWN.replace("## Flagged", "\n".join(rows) + "\n\n## Flagged")
        screen = parse_weekly_screen(
            markdown, {"run_date": RUN_DATE, "entries": entries}, frozenset(), enrichment
        )
        html, note = render_document(screen, net_liq=12000.0, per_name_cap=0.25)
        self.assertEqual(len(screen.candidates), 50)
        self.assertEqual(screen.enriched_count, 50)
        self.assertEqual(note, "", f"50 cards rendered {len(html.encode()) / 1024:.0f}KB")


class PrintTests(unittest.TestCase):
    def test_expanded_cards_print_and_collapsed_ones_do_not(self) -> None:
        html = document(records(*THREE))
        self.assertIn("@media print", html)
        self.assertIn('.detail-row[hidden]{display:none!important}', html)
        self.assertIn('[role="tabpanel"][hidden]{display:block!important}', html)


class NoEnrichmentTests(unittest.TestCase):
    def test_a_week_with_no_records_renders_the_old_report(self) -> None:
        html = document(None)
        # The toggle script always ships; what is absent is any row for it.
        self.assertNotIn('data-expands="', html)
        self.assertNotIn('<div class="detail">', html)
        self.assertIn("<span>Enriched</span><strong>0/4</strong>", html)
        for ticker in ("FULL", "SPARSE", "EMPTY", "PLAIN"):
            self.assertIn(f"<strong>{ticker}</strong>", html)


class RenderLatestTests(unittest.TestCase):
    """The IO edge: discovery, enrichment lookup, atomic write."""

    def _wheelops(self, temporary: str, *, enrich: bool) -> Path:
        wheelops = Path(temporary)
        weeks = wheelops / "weeks"
        weeks.mkdir(parents=True)
        (weeks / f"{RUN_DATE}.md").write_text(MARKDOWN, encoding="utf-8")
        (weeks / f"{RUN_DATE}{SIDECAR_SUFFIX}").write_text(
            json.dumps(SIDECAR), encoding="utf-8"
        )
        if enrich:
            for record in records(*THREE).values():
                write_enrichment(wheelops, RUN_DATE, record)
        return wheelops

    @staticmethod
    def _config(wheelops: Path) -> dict:
        return {
            "paths": {"wheelops": str(wheelops)},
            "account": {"net_liq": 12000, "per_name_cap": 0.25},
        }

    def test_it_picks_up_the_enrichment_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = self._wheelops(temporary, enrich=True)
            path, screen, note = render_latest(self._config(wheelops))
            self.assertEqual(path.name, f"{RUN_DATE}.html")
            self.assertEqual(screen.enriched_count, 3)
            self.assertEqual(note, "")
            self.assertIn("Ford Motor Company", path.read_text(encoding="utf-8"))

    def test_a_missing_enrichment_folder_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = self._wheelops(temporary, enrich=False)
            path, screen, _ = render_latest(self._config(wheelops))
            self.assertEqual(screen.enriched_count, 0)
            self.assertTrue(path.is_file())

    def test_no_temporary_file_survives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = self._wheelops(temporary, enrich=True)
            render_latest(self._config(wheelops))
            self.assertEqual(list((wheelops / "weeks").glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
