"""Offline tests for the weekly report: classification, composite, render.

Driven by the four golden snapshots. Expected shape:
- F     -- candidate, in zone, composite 100
- MARA  -- candidate, in zone, three flags, composite 62.5
- SPY   -- candidate, OUT of zone ($618 vs $30 ceiling), ranked below the
           separator; analyst weight renormalized away (ETF)
- APLD  -- rejected on two fitness gates; its thesis gap must NOT put it in
           the thesis-required section (rejection wins)
"""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from wheel.scorers import SelectionThresholds, evaluate_single_ticker_rules
from wheel.week_report import (
    ScoredName,
    assignment_capacity,
    classify,
    composite_score,
    in_zone,
    open_positions,
    render_week_report,
    sector_exposure,
    unlock_net_liq,
    zone_ceiling,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
THRESHOLDS = SelectionThresholds(
    min_ttm_net_income=0.0,
    min_operating_cash_flow=0.0,
    min_price=10.0,
    max_price=50.0,
    max_mean_rating=2.5,
    max_single_day_move=0.15,
    earnings_flag_days=45,
)
WEIGHTS = {
    "stability": 0.30,
    "iv_proxy_quality": 0.25,
    "chart_position": 0.20,
    "dividend": 0.15,
    "analyst_strength": 0.10,
}
RUN_DATE = date(2026, 8, 15)


def load(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text())


def scored(document: dict) -> ScoredName:
    return ScoredName(
        document=document,
        results=evaluate_single_ticker_rules(document, THRESHOLDS),
    )


def render(scored_names, position_rows=(), missing=()):
    return render_week_report(
        run_date=RUN_DATE,
        net_liq=12_000.0,
        per_name_cap=0.25,
        scored=scored_names,
        cross_results=(),
        position_rows=list(position_rows),
        missing=list(missing),
        weights=WEIGHTS,
    )


class ClassificationTests(unittest.TestCase):
    def test_compliant_equity_is_a_candidate(self) -> None:
        self.assertEqual(classify(scored(load("2026-08-15_F.json")).results), "candidate")

    def test_rejection_wins_over_missing_thesis(self) -> None:
        # APLD fails ST-SEL-01 and ST-SEL-10 and has no thesis; it must land
        # in rejected, not thesis-required.
        self.assertEqual(
            classify(scored(load("2026-08-15_APLD-highvol.json")).results),
            "rejected",
        )

    def test_fitness_cleared_name_without_thesis_needs_a_thesis(self) -> None:
        document = load("2026-08-15_F.json")
        document["operator_gates"]["thesis_note_exists"] = False
        document["operator_gates"]["thesis_note_path"] = None
        self.assertEqual(classify(scored(document).results), "thesis_required")

    def test_unanswerable_gate_is_unevaluable_not_rejected(self) -> None:
        document = load("2026-08-15_F.json")
        document["price"]["current"] = None
        self.assertEqual(classify(scored(document).results), "unevaluable")


class CompositeTests(unittest.TestCase):
    def test_all_pass_scores_100(self) -> None:
        name = scored(load("2026-08-15_F.json"))
        self.assertEqual(composite_score(name.results, WEIGHTS), 100.0)

    def test_flags_and_fails_blend(self) -> None:
        # MARA: ST-SEL-05 fail (16.4% move > 15% limit), ST-SEL-10 flag(50),
        # ST-SEL-12 flag(50), ST-SEL-06 fail(0), ST-SEL-02 pass(100)
        # -> 30*0 + 25*50 + 20*50 + 15*0 + 10*100 = 32.5 under the weights.
        name = scored(load("2026-08-15_MARA-flagvol.json"))
        self.assertAlmostEqual(composite_score(name.results, WEIGHTS), 32.5)

    def test_not_applicable_weight_is_renormalized_not_zeroed(self) -> None:
        # SPY's analyst consensus is N/A (ETF); remaining weights renormalize:
        # (30*100 + 25*100 + 20*50 + 15*100) / 90 = 88.9
        name = scored(load("2026-08-15_SPY-minimal.json"))
        self.assertAlmostEqual(
            composite_score(name.results, WEIGHTS), 88.888, places=2
        )


class ZoneTests(unittest.TestCase):
    def test_ceiling_follows_the_constitution_formula(self) -> None:
        self.assertEqual(zone_ceiling(12_000, 0.25), 30.0)

    def test_in_and_out_of_zone(self) -> None:
        self.assertTrue(in_zone(12.30, 30.0))
        self.assertFalse(in_zone(618.42, 30.0))

    def test_unlock_threshold_inverts_the_formula(self) -> None:
        # $618.42 at a 25% cap needs a ~$247K account.
        self.assertAlmostEqual(unlock_net_liq(618.42, 0.25), 247_368.0)


class PositionsTests(unittest.TestCase):
    ROWS = [
        {"ticker": "F", "sector": "Consumer Cyclical", "strike": "11.0",
         "contracts": "1", "status": "open"},
        {"ticker": "T", "sector": "Communication Services", "strike": "27",
         "contracts": "1", "status": "closed"},
        {"ticker": "KO", "sector": "Consumer Defensive", "strike": "junk",
         "contracts": "1", "status": "open"},
    ]

    def test_open_positions_filters_closed_and_unparseable(self) -> None:
        kept = open_positions(self.ROWS)
        self.assertEqual([p["ticker"] for p in kept], ["F"])
        self.assertEqual(kept[0]["collateral"], 1_100.0)

    def test_assignment_capacity(self) -> None:
        capacity = assignment_capacity(open_positions(self.ROWS), 12_000.0)
        self.assertEqual(capacity["needed"], 1_100.0)
        self.assertEqual(capacity["available"], 12_000.0)
        self.assertAlmostEqual(capacity["reserve_fraction"], 0.9083, places=3)

    def test_sector_exposure_fractions(self) -> None:
        rows = self.ROWS + [
            {"ticker": "GM", "sector": "Consumer Cyclical", "strike": "33",
             "contracts": "1", "status": "open"},
        ]
        exposure = sector_exposure(open_positions(rows))
        self.assertEqual(list(exposure), ["Consumer Cyclical"])
        self.assertAlmostEqual(exposure["Consumer Cyclical"], 1.0)


class RenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.names = [
            scored(load("2026-08-15_F.json")),
            scored(load("2026-08-15_SPY-minimal.json")),
            scored(load("2026-08-15_APLD-highvol.json")),
            scored(load("2026-08-15_MARA-flagvol.json")),
        ]
        self.markdown = render(self.names)

    def test_five_sections_in_order(self) -> None:
        positions = [
            self.markdown.index("# Wheel screen — 2026-08-15"),
            self.markdown.index("## Thesis required"),
            self.markdown.index("## Ranked candidates"),
            self.markdown.index("## Portfolio context"),
            self.markdown.index("## Flagged / rejected"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_header_shows_derived_zone_ceiling(self) -> None:
        self.assertIn("zone ceiling $30.00", self.markdown)

    def test_ranked_in_zone_order_is_composite_descending(self) -> None:
        self.assertLess(
            self.markdown.index("| 1 | F |"), self.markdown.index("| 2 | MARA |")
        )

    def test_out_of_zone_is_below_the_separator_with_unlock(self) -> None:
        separator = self.markdown.index("Out of zone — displayed but locked")
        self.assertGreater(self.markdown.index("| · | SPY |"), separator)
        self.assertIn("unlocks at ~$247,368", self.markdown)
        self.assertIn("if assigned 515% of net liq", self.markdown)

    def test_rejected_name_lists_its_failing_gates(self) -> None:
        section = self.markdown[self.markdown.index("## Flagged / rejected"):]
        self.assertIn("**APLD**", section)
        self.assertIn("ST-SEL-01", section)
        self.assertIn("ST-SEL-10", section)

    def test_flag_zone_candidate_shows_warnings_inline(self) -> None:
        mara_row = next(
            line for line in self.markdown.splitlines() if "| MARA |" in line
        )
        self.assertEqual(mara_row.count("⚠"), 3)  # vol, chart, earnings

    def test_thesis_required_section_lists_fitness_cleared_names(self) -> None:
        document = load("2026-08-15_F.json")
        document["operator_gates"]["thesis_note_exists"] = False
        document["operator_gates"]["thesis_note_path"] = None
        markdown = render([scored(document)])
        section = markdown[markdown.index("## Thesis required"):]
        self.assertIn("`notes/F.md`", section)
        self.assertIn("worth writing theses for", section)

    def test_no_positions_reads_as_absence_not_zero(self) -> None:
        self.assertIn("no open positions recorded", self.markdown)

    def test_positions_feed_reserve_and_capacity(self) -> None:
        markdown = render(
            self.names,
            position_rows=[
                {"ticker": "F", "sector": "Consumer Cyclical", "strike": "11",
                 "contracts": "1", "status": "open"},
            ],
        )
        self.assertIn("$1,100 needed vs $12,000 available", markdown)
        self.assertIn("Reserve: 91% of net liq uncommitted — meets", markdown)

    def test_reserve_breach_is_loud(self) -> None:
        markdown = render(
            self.names,
            position_rows=[
                {"ticker": "X", "sector": "Tech", "strike": "70",
                 "contracts": "1", "status": "open"},
            ],
        )
        self.assertIn("**BREACHES**", markdown)

    def test_missing_names_are_surfaced_never_dropped(self) -> None:
        markdown = render(self.names, missing=[("GHOST", "no snapshot")])
        self.assertIn("**GHOST**", markdown)

    def test_approximation_footnote_is_always_present(self) -> None:
        self.assertIn("not implied volatility", self.markdown)

    def test_render_is_deterministic(self) -> None:
        self.assertEqual(self.markdown, render(self.names))


if __name__ == "__main__":
    unittest.main()
