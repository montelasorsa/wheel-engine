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

from wheel.monitored import MonitoredConfig
from wheel.scorers import (
    SelectionThresholds,
    Verdict,
    evaluate_single_ticker_rules,
)
from wheel.week_report import (
    COMPOSITE_WEIGHT_KEYS,
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
    "volatility": 0.20,
    "chart_position": 0.20,
    "cash_flow_strength": 0.20,
    "dividend": 0.20,
    "analyst_strength": 0.20,
}
RUN_DATE = date(2026, 8, 15)


def load(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text())


def scored(document: dict) -> ScoredName:
    return ScoredName(
        document=document,
        results=evaluate_single_ticker_rules(document, THRESHOLDS),
    )


def render(scored_names, position_rows=(), missing=(), **kwargs):
    markdown, _ = render_full(scored_names, position_rows, missing, **kwargs)
    return markdown


def render_full(scored_names, position_rows=(), missing=(), **kwargs):
    return render_week_report(
        run_date=RUN_DATE,
        net_liq=12_000.0,
        per_name_cap=0.25,
        scored=scored_names,
        cross_results=(),
        position_rows=list(position_rows),
        missing=list(missing),
        weights=WEIGHTS,
        **kwargs,
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
    def test_it_is_the_weighted_mean_of_the_component_scores(self) -> None:
        """No bucketing anywhere: the composite is arithmetic on the curves."""

        name = scored(load("2026-08-15_F.json"))
        by_rule = {r.rule_id: r for r in name.results}
        expected = sum(
            by_rule[rule].score * WEIGHTS[key]
            for rule, key in COMPOSITE_WEIGHT_KEYS.items()
        ) / sum(WEIGHTS.values())
        self.assertAlmostEqual(composite_score(name.results, WEIGHTS), expected)
        self.assertAlmostEqual(expected, 61.464, places=3)

    def test_a_better_name_on_one_component_scores_higher(self) -> None:
        """The property that matters: the composite orders names."""

        base = load("2026-08-15_F.json")
        worse = load("2026-08-15_F.json")
        worse["volatility"]["realized_vol_30d"] = 0.65
        self.assertGreater(
            composite_score(scored(base).results, WEIGHTS),
            composite_score(scored(worse).results, WEIGHTS),
        )

    def test_not_applicable_weight_is_renormalized_not_zeroed(self) -> None:
        # SPY is an ETF: ST-SEL-01 and ST-SEL-02 do not govern it, so it is
        # ranked on the three components that do rather than punished for the
        # two that cannot apply (§4.4).
        name = scored(load("2026-08-15_SPY-minimal.json"))
        by_rule = {r.rule_id: r for r in name.results}
        self.assertIsNone(by_rule["ST-SEL-01"].score)
        self.assertIsNone(by_rule["ST-SEL-02"].score)
        applicable = ["ST-SEL-10", "ST-SEL-12", "ST-SEL-06"]
        expected = sum(
            by_rule[rule].score * WEIGHTS[COMPOSITE_WEIGHT_KEYS[rule]]
            for rule in applicable
        ) / sum(WEIGHTS[COMPOSITE_WEIGHT_KEYS[rule]] for rule in applicable)
        self.assertAlmostEqual(composite_score(name.results, WEIGHTS), expected)

    def test_a_name_with_nothing_scorable_returns_none_not_zero(self) -> None:
        self.assertIsNone(composite_score([], WEIGHTS))

    def test_stability_is_deliberately_outside_the_composite(self) -> None:
        """ST-SEL-05 has no continuous form; a bucket would re-add a step."""

        self.assertNotIn("ST-SEL-05", COMPOSITE_WEIGHT_KEYS)
        name = scored(load("2026-08-15_F.json"))
        self.assertIn("ST-SEL-05", {r.rule_id for r in name.results})


class ScoreDistinctnessTests(unittest.TestCase):
    """The defect this change exists to close, asserted directly.

    The 2026-08-11 run produced ~30 distinct composites across 1,285 names --
    255 tied at exactly 100 -- so the monitored tier's "top 5" was the
    alphabetically-first five of 111 equals. Verdict buckets cannot do better
    than a few dozen values however many rules feed them.
    """

    def test_similar_names_no_longer_collapse_onto_one_score(self) -> None:
        composites = []
        for index in range(60):
            document = load("2026-08-15_F.json")
            document["volatility"]["realized_vol_30d"] = 0.20 + index * 0.005
            composites.append(
                round(composite_score(scored(document).results, WEIGHTS), 9)
            )
        self.assertEqual(len(set(composites)), 60)
        # Strictly ordered, so a "top 5" is a top 5 rather than five names
        # that happened to sort first.
        self.assertEqual(composites, sorted(composites, reverse=True))

    def test_the_old_scheme_would_have_tied_all_sixty(self) -> None:
        """Same inputs under verdict buckets: every name lands on one value."""

        buckets = {Verdict.PASS: 100.0, Verdict.FLAG: 50.0, Verdict.FAIL: 0.0}
        collapsed = set()
        for index in range(60):
            document = load("2026-08-15_F.json")
            document["volatility"]["realized_vol_30d"] = 0.20 + index * 0.005
            document["chart_position"]["pct_below_two_year_high"] = (
                0.05 + index * 0.004
            )
            by_rule = {r.rule_id: r for r in scored(document).results}
            collapsed.add(
                tuple(
                    buckets.get(by_rule[rule].verdict)
                    for rule in COMPOSITE_WEIGHT_KEYS
                )
            )
        self.assertEqual(len(collapsed), 1)


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
            self.markdown.index("## Monitored"),
            self.markdown.index("## Ranked candidates"),
            self.markdown.index("## Portfolio context"),
            self.markdown.index("## Flagged / rejected"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_header_shows_derived_zone_ceiling(self) -> None:
        self.assertIn("zone ceiling $30.00", self.markdown)

    def test_header_shows_the_funnel(self) -> None:
        self.assertIn("Funnel:", self.markdown)
        self.assertIn("cleared gates", self.markdown)

    def test_ranked_in_zone_order_is_composite_descending(self) -> None:
        self.assertLess(
            self.markdown.index("| 1 | F |"), self.markdown.index("| 2 | MARA |")
        )

    def test_out_of_zone_is_below_the_separator_with_unlock(self) -> None:
        separator = self.markdown.index("Out of zone — displayed but locked")
        self.assertGreater(self.markdown.index("| · | SPY |"), separator)
        self.assertIn("unlocks at ~$247,368", self.markdown)
        self.assertIn("if assigned 515% of net liq", self.markdown)

    def test_rejections_are_grouped_by_gate_not_listed_by_name(self) -> None:
        section = self.markdown[self.markdown.index("## Flagged / rejected"):]
        self.assertIn("ST-SEL-01: 1 name", section)
        self.assertIn("ST-SEL-10: 1 name", section)
        # APLD is counted, not named -- at scale the names are noise.
        self.assertNotIn("**APLD**", section)

    def test_flagged_names_are_still_listed_individually(self) -> None:
        section = self.markdown[self.markdown.index("## Flagged / rejected"):]
        self.assertIn("cleared the gates, but read these", section)
        self.assertIn("**MARA**", section)

    def test_monitored_row_carries_only_the_surviving_flag_labels(self) -> None:
        """Elevated vol and near-high became scores; earnings stayed a flag."""

        markdown = render(
            self.names, monitored_settings=MonitoredConfig(0.0, 5, 25)
        )
        row = next(
            line for line in markdown.splitlines() if "MARA" in line and line.startswith("|")
        )
        self.assertIn("earnings soon", row)
        self.assertNotIn("elevated vol", row)
        self.assertNotIn("near high", row)

    def test_monitored_lists_fitness_cleared_names_without_a_thesis(self) -> None:
        document = load("2026-08-15_F.json")
        document["operator_gates"]["thesis_note_exists"] = False
        document["operator_gates"]["thesis_note_path"] = None
        markdown = render([scored(document)])
        section = markdown[markdown.index("## Monitored"):]
        self.assertIn("| F |", section)
        self.assertIn("worth writing one for", section)

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




class MonitoredTierTests(unittest.TestCase):
    """Top-N per zone, caps, thesis-first ordering, and week-over-week."""

    def make(self, ticker, score, price, thesis=False):
        """A minimal entry; the tier logic never reads the snapshot."""

        from wheel.monitored import MonitoredEntry, zone_for

        return MonitoredEntry(
            ticker=ticker,
            score=score,
            price=price,
            zone=zone_for(price, 30.0),
            sector="Industrials",
            dividend_yield=2.0,
            volatility=0.3,
            pct_below_high=0.2,
            earnings_date="2026-10-08",
            thesis_backed=thesis,
            flags=(),
        )

    def test_floor_excludes_low_scores(self) -> None:
        from wheel.monitored import select_monitored

        entries = [self.make("LOW", 40.0, 20.0), self.make("HIGH", 80.0, 20.0)]
        kept, _ = select_monitored(entries, MonitoredConfig(60.0, 5, 25))
        self.assertEqual([e.ticker for e in kept["Zone 1"]], ["HIGH"])

    def test_top_five_per_zone_with_overflow_count(self) -> None:
        from wheel.monitored import select_monitored

        entries = [self.make(f"T{i}", 90.0 - i, 20.0) for i in range(8)]
        kept, overflow = select_monitored(entries, MonitoredConfig(60.0, 5, 25))
        self.assertEqual(len(kept["Zone 1"]), 5)
        self.assertEqual(overflow["Zone 1"], 3)
        self.assertEqual([e.ticker for e in kept["Zone 1"]], ["T0", "T1", "T2", "T3", "T4"])

    def test_total_cap_binds_across_zones(self) -> None:
        from wheel.monitored import select_monitored

        entries = [self.make(f"A{i}", 90.0, 20.0) for i in range(5)] + [
            self.make(f"B{i}", 90.0, 50.0) for i in range(5)
        ]
        kept, _ = select_monitored(entries, MonitoredConfig(60.0, 5, 7))
        self.assertEqual(sum(len(v) for v in kept.values()), 7)

    def test_thesis_backed_sorts_above_a_higher_score(self) -> None:
        from wheel.monitored import select_monitored

        entries = [
            self.make("NOTHESIS", 95.0, 20.0),
            self.make("BACKED", 70.0, 20.0, thesis=True),
        ]
        kept, _ = select_monitored(entries, MonitoredConfig(60.0, 5, 25))
        self.assertEqual([e.ticker for e in kept["Zone 1"]], ["BACKED", "NOTHESIS"])

    def test_zones_are_assigned_by_multiples_of_the_ceiling(self) -> None:
        from wheel.monitored import zone_for

        self.assertEqual(zone_for(25.0, 30.0), "Zone 1")
        self.assertEqual(zone_for(45.0, 30.0), "Zone 2")
        self.assertEqual(zone_for(100.0, 30.0), "Zone 3")
        self.assertEqual(zone_for(618.0, 30.0), "Beyond zones")

    def test_movement_marks_new_entries_and_deltas(self) -> None:
        from wheel.monitored import apply_movement

        prior = {"entries": {"OLD": {"score": 70.0}}}
        moved = apply_movement(
            [self.make("OLD", 75.0, 20.0), self.make("FRESH", 80.0, 20.0)], prior
        )
        by_ticker = {e.ticker: e for e in moved}
        self.assertEqual(by_ticker["OLD"].delta, 5.0)
        self.assertFalse(by_ticker["OLD"].is_new)
        self.assertTrue(by_ticker["FRESH"].is_new)

    def test_first_run_has_no_deltas_and_no_new_labels(self) -> None:
        from wheel.monitored import apply_movement

        moved = apply_movement([self.make("A", 80.0, 20.0)], None)
        self.assertIsNone(moved[0].delta)
        self.assertFalse(moved[0].is_new)

    def test_exits_report_why_each_name_left(self) -> None:
        from wheel.monitored import find_exits

        prior = {"entries": {"DROPPED": {"score": 80.0}, "FAILED": {"score": 75.0},
                             "GONE": {"score": 70.0}}}
        exits = find_exits(
            [self.make("STAYED", 80.0, 20.0)],
            prior,
            scored_now={"DROPPED": 45.0},
            rejected_now={"FAILED": "ST-SEL-10"},
        )
        reasons = {e["ticker"]: e["reason"] for e in exits}
        self.assertIn("below the score floor", reasons["DROPPED"])
        self.assertIn("ST-SEL-10", reasons["FAILED"])
        self.assertIn("no longer in the screened universe", reasons["GONE"])


class UniverseScaleRenderTests(unittest.TestCase):
    """Thirty synthetic names: the shape a real run produces."""

    def setUp(self) -> None:
        base = load("2026-08-15_F.json")
        self.names = []
        for index in range(30):
            document = json.loads(json.dumps(base))
            document["ticker"] = f"T{index:02d}"
            # Spread across zones: 10 in zone 1, 10 in zone 2, 10 beyond.
            document["price"]["current"] = [20.0, 45.0, 500.0][index % 3]
            # Vary the composite continuously, the way a real run does: every
            # name gets its own volatility and entry point, so no two land on
            # the same score and the per-zone caps actually have to choose.
            document["volatility"]["realized_vol_30d"] = 0.15 + index * 0.004
            document["chart_position"]["pct_below_two_year_high"] = (
                0.30 - index * 0.002
            )
            document["operator_gates"]["thesis_note_exists"] = index == 0
            self.names.append(scored(document))
        self.markdown = render(self.names)

    def test_no_zone_lists_more_than_five(self) -> None:
        section = self.markdown[
            self.markdown.index("## Monitored"):self.markdown.index("## Ranked")
        ]
        # Bound each zone block at the next heading, or the counts run on
        # into the following zone.
        blocks = section.split("### ")[1:]
        self.assertTrue(blocks, "no zone blocks rendered")
        for block in blocks:
            zone_heading = block.splitlines()[0]
            rows = [
                line for line in block.splitlines()
                if line.startswith("|") and "Ticker" not in line and "---" not in line
            ]
            self.assertLessEqual(len(rows), 5, zone_heading)

    def test_overflow_line_reports_the_remainder(self) -> None:
        self.assertIn("more in this zone", self.markdown)

    def test_total_cap_is_respected_across_the_whole_section(self) -> None:
        _, kept = render_full(self.names)
        self.assertLessEqual(sum(len(v) for v in kept.values()), 25)

    def test_thesis_backed_name_renders_bold_and_first(self) -> None:
        section = self.markdown[self.markdown.index("### Zone 1"):]
        self.assertIn("**T00**", section)


if __name__ == "__main__":
    unittest.main()
