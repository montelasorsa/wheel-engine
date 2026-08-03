"""Offline fixture tests for the pure Step 6 report and CSV renderers."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from wheel_screener.data import TickerSnapshot
from wheel_screener.reporting import PipelineResult
from wheel_screener.reporting.render import (
    CSV_COLUMNS,
    build_csv_rows,
    render_csv,
    render_html,
    write_report_and_csv,
)
from wheel_screener.scoring.flags import EarningsProximityFlag, FlaggedScoredTicker
from wheel_screener.scoring.score_filters import (
    IV_PROXY_APPROXIMATION,
    ScoredTicker,
    ScoreResult,
)
from wheel_screener.screening.hard_gates import GateFailureKind, GateResult
from wheel_screener.screening.pipeline import EvaluatedTicker, HardGateBuckets
from wheel_screener.screening.step5_pipeline import Step5PipelineOutput


RUN_TIMESTAMP = datetime(2026, 7, 25, 19, 28, 22)
RUN_DATE = RUN_TIMESTAMP.date()

# ORCL scored and earnings-imminent, WY scored and far out, GEN scored with no
# calendar, ABT fitness fail, HBAN missing data (FMP-rescued field), ANSS fetch
# error. Six names, one per rendering branch.
UNIVERSE = ("ORCL", "WY", "GEN", "ABT", "HBAN", "ANSS")


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame({"date": [], "close": [], "adjusted_close": []})


def make_snapshot(symbol: str, *, field_sources: dict | None = None) -> TickerSnapshot:
    # Every real snapshot's field_sources is a full provenance map -- every
    # populated fundamental tagged "yfinance", not just rescued ones (see
    # build_ticker_snapshot). Baking that in here catches renderers that treat
    # key presence, rather than the "fmp" value, as the rescue signal.
    sources = {"company_name": "yfinance", "current_price": "yfinance"}
    sources.update(field_sources or {})
    return TickerSnapshot(
        symbol=symbol,
        fundamentals={
            "company_name": f"{symbol} Incorporated",
            "business_description": f"{symbol} makes widgets for industry.",
            "sector": "Industrials",
            "industry": "Specialty Widgets",
            "market_cap": 45_710_000_000,
        },
        price_history=empty_frame(),
        dividends=pd.DataFrame({"dividend": []}),
        analyst={"recommendation_mean": 2.0},
        recommendation_summary=pd.DataFrame(),
        option_expirations=("2026-08-21",),
        field_sources=sources,
    )


GATE_METRICS = {
    "F1": {"net_income_ttm": 2_000_000_000.0, "operating_cash_flow_ttm": 3_000_000_000.0},
    "F2": {"recommendation_mean": 2.0},
    "F3": {"price": 42.50},
    "F4": {"price": 42.50},
    "F9": {"options_available": True},
}


def passing_gates() -> tuple[GateResult, ...]:
    return tuple(
        GateResult(
            gate_id=gate_id,
            rule_ids=("ST-SEL-01",),
            passed=True,
            reason="ok",
            metrics=GATE_METRICS[gate_id],
        )
        for gate_id in ("F1", "F2", "F3", "F4", "F9")
    )


def make_scored(symbol: str, composite: float) -> ScoredTicker:
    return ScoredTicker(
        symbol=symbol,
        filter_results=(
            ScoreResult(
                filter_id="F5",
                rule_ids=("ST-SEL-05",),
                score=100.0,
                reason="stable",
                metrics={"max_daily_move": 0.0412, "realized_vol": 0.2233},
            ),
            ScoreResult(
                filter_id="F6",
                rule_ids=("ST-SEL-06",),
                score=100.0,
                reason="pays",
                metrics={"dividend_yield": 2.31},
            ),
            ScoreResult(
                filter_id="F7",
                rule_ids=("ST-SEL-10", "ST-SEL-11"),
                score=88.0,
                reason=IV_PROXY_APPROXIMATION,
                is_approximation=True,
                approximation_note=IV_PROXY_APPROXIMATION,
                metrics={"realized_vol_30d": 0.3155},
            ),
            ScoreResult(
                filter_id="F8",
                rule_ids=("ST-SEL-12",),
                score=100.0,
                reason="off the high",
                metrics={"pct_below_2y_high": 0.1842},
            ),
        ),
        analyst_strength_score=66.0,
        analyst_strength_reason="margin",
        composite_score=composite,
        contains_approximation=True,
        approximation_notes=(IV_PROXY_APPROXIMATION,),
    )


def make_flagged(
    symbol: str,
    composite: float,
    *,
    days: int | None,
    triggered: bool,
) -> FlaggedScoredTicker:
    next_date = None if days is None else date.fromordinal(RUN_DATE.toordinal() + days)
    return FlaggedScoredTicker(
        symbol=symbol,
        scored=make_scored(symbol, composite),
        f10=EarningsProximityFlag(
            flag_id="F10",
            triggered=triggered,
            days_to_earnings=days,
            next_earnings_date=next_date,
        ),
    )


def build_fixture(diff: dict) -> PipelineResult:
    passed = tuple(
        EvaluatedTicker(snapshot=make_snapshot(symbol), gate_results=passing_gates())
        for symbol in ("ORCL", "WY", "GEN")
    )
    fitness_fail = (
        EvaluatedTicker(
            snapshot=make_snapshot("ABT"),
            gate_results=(
                GateResult(
                    gate_id="F3",
                    rule_ids=("ST-SEL-03",),
                    passed=False,
                    reason="F3: Price $103.06 is outside the $10.00-$50.00 band.",
                    failure_kind=GateFailureKind.FITNESS,
                ),
            ),
        ),
    )
    missing_data = (
        EvaluatedTicker(
            # Provenance carried through even while the rescue is dormant.
            snapshot=make_snapshot(
                "HBAN",
                field_sources={"operating_cash_flow_ttm": "fmp"},
            ),
            gate_results=(
                GateResult(
                    gate_id="F1",
                    rule_ids=("ST-SEL-01",),
                    passed=False,
                    reason="Cannot evaluate: missing operating_cash_flow_ttm.",
                    failure_kind=GateFailureKind.MISSING_DATA,
                    metrics={
                        "net_income_ttm": 1_400_000_000.0,
                        "operating_cash_flow_ttm": None,
                    },
                ),
            ),
        ),
    )

    flagged = (
        make_flagged("ORCL", 94.5, days=10, triggered=True),
        make_flagged("WY", 88.25, days=52, triggered=False),
        make_flagged("GEN", 71.0, days=None, triggered=False),
    )

    current_state = {
        "ORCL": {"verdict": "scored", "reason": None, "composite": 94.5},
        "WY": {"verdict": "scored", "reason": None, "composite": 88.25},
        "GEN": {"verdict": "scored", "reason": None, "composite": 71.0},
        "ABT": {
            "verdict": "fitness_fail",
            "reason": "F3: Price $103.06 is outside the $10.00-$50.00 band.",
            "composite": None,
        },
        "HBAN": {
            "verdict": "missing_data",
            "reason": "F1: Cannot evaluate: missing operating_cash_flow_ttm.",
            "composite": None,
        },
        "ANSS": {"verdict": "fetch_error", "reason": "fetch error", "composite": None},
    }

    return PipelineResult(
        run_timestamp=RUN_TIMESTAMP,
        run_date=RUN_DATE,
        universe_symbols=UNIVERSE,
        fetch_error_symbols=("ANSS",),
        buckets=HardGateBuckets(
            passed=passed,
            failed_fitness=fitness_fail,
            failed_missing_data=missing_data,
        ),
        step5=Step5PipelineOutput(
            flagged_scored=flagged,
            diff=diff,
            current_state=current_state,
            state_path=Path("/tmp/run_state_2026-07-25-192822.json"),
            prior_state_path=None,
        ),
        universe_volatility_percentile=0.3072,
    )


FIRST_RUN_DIFF = {
    "first_run": True,
    "newly_qualified": [],
    "newly_dropped": [],
    "unchanged": [],
}

SECOND_RUN_DIFF = {
    "first_run": False,
    "newly_qualified": [{"ticker": "GEN", "prior_verdict": "fitness_fail"}],
    "newly_dropped": [
        {
            "ticker": "PFE",
            "current_verdict": "fitness_fail",
            "reason": "F2: Mean analyst rating 2.61 is above the 2.50 maximum.",
        }
    ],
    "unchanged": ["ORCL", "WY"],
}


class RenderHtmlTests(unittest.TestCase):
    """Section order, change-log branches, and provenance rendering."""

    def test_sections_render_in_specified_order(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        anchors = [
            'id="header"',
            'id="changelog"',
            'id="ranked"',
            'id="missing-data"',
            'id="fetch-errors"',
            'id="fitness-fail"',
        ]
        positions = [html.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions))

    def test_header_reports_every_bucket_total(self) -> None:
        html = render_html(build_fixture(FIRST_RUN_DIFF))
        self.assertIn("Universe", html)
        self.assertIn("<b>6</b>", html)  # universe size
        self.assertIn("30.72%", html)  # F5 volatility benchmark
        self.assertIn(IV_PROXY_APPROXIMATION, html)

    def test_first_run_shows_notice_not_empty_tables(self) -> None:
        html = render_html(build_fixture(FIRST_RUN_DIFF))
        self.assertIn("First run — no comparison available yet", html)
        self.assertNotIn("Newly qualified", html)
        self.assertNotIn("Newly dropped", html)

    def test_second_run_shows_both_change_lists_with_reason(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("Newly qualified (1)", html)
        self.assertIn("Newly dropped (1)", html)
        self.assertIn("PFE", html)
        self.assertIn("Mean analyst rating 2.61", html)
        self.assertIn("2 names still qualify", html)

    def test_f10_renders_dated_chip_per_proximity_band(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("f10-warning", html)  # ORCL at 10 days
        self.assertIn("(10d)", html)
        self.assertIn("f10-far", html)  # WY at 52 days
        self.assertIn("f10-unknown", html)  # GEN has no calendar
        self.assertIn("no calendar data", html)

    def test_composite_bar_width_tracks_score(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("width: 94.5%", html)
        self.assertIn("width: 71.0%", html)

    def test_missing_data_shows_blocking_gate_and_source_label(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("HBAN", html)
        self.assertIn("Cannot evaluate: missing operating_cash_flow_ttm.", html)
        self.assertIn("operating_cash_flow_ttm via fmp", html)
        # Plain yfinance provenance must not render as a rescue chip.
        self.assertNotIn("via yfinance", html)

    def test_ranked_cell_stacks_business_identity(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("ORCL Incorporated", html)
        self.assertIn("Industrials — Specialty Widgets", html)
        self.assertIn("$45.71B", html)

    def test_filter_cells_show_score_and_raw_metric(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("100 · 4.12% / 22.33%", html)  # F5 max move / realized vol
        self.assertIn("100 · 2.31%", html)  # F6 dividend yield
        self.assertIn("88 · 31.55%", html)  # F7 realized vol proxy
        self.assertIn("100 · 18.42%", html)  # F8 pct below 2y high
        self.assertIn("66 · 2.00", html)  # F2 margin · recommendation mean

    def test_missing_data_shows_expected_vs_actual(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("net_income_ttm = $1,400M present", html)
        self.assertIn("operating_cash_flow_ttm = null", html)

    def test_change_log_rows_carry_company_names(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        # GEN newly qualified: has a snapshot this run, so its name joins.
        self.assertIn("GEN Incorporated", html)
        # PFE newly dropped with no snapshot in this run's buckets: ticker alone.
        self.assertNotIn("PFE Incorporated", html)

    def test_fetch_errors_are_listed_explicitly(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("Fetch errors (1)", html)
        self.assertIn("ANSS", html)

    def test_fitness_fail_is_a_count_not_a_list(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("1 names failed fitness gates — see CSV for details.", html)

    def test_report_is_self_contained(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        for external in ("http://", "https://", "<script"):
            self.assertNotIn(external, html)


class RenderCsvTests(unittest.TestCase):
    """Schema shape, null handling, and the metrics recovered from Step 6."""

    def setUp(self) -> None:
        self.text = render_csv(build_fixture(SECOND_RUN_DIFF))
        self.rows = list(csv.reader(io.StringIO(self.text)))

    def test_header_matches_specified_column_order(self) -> None:
        self.assertEqual(tuple(self.rows[0]), CSV_COLUMNS)
        self.assertEqual(len(self.rows[0]), 34)
        # Business context sits immediately after ticker, before verdict.
        self.assertEqual(
            self.rows[0][0:7],
            [
                "ticker",
                "company_name",
                "business_description",
                "industry",
                "sector",
                "market_cap",
                "verdict",
            ],
        )
        # Gate raw metrics sit adjacent to their pass columns.
        self.assertEqual(
            self.rows[0][8:18],
            [
                "f1_pass",
                "f1_net_income_ttm",
                "f1_operating_cash_flow_ttm",
                "f2_pass",
                "f2_recommendation_mean",
                "f3_pass",
                "f3_price",
                "f4_pass",
                "f9_pass",
                "f9_options_available",
            ],
        )

    def test_one_row_per_universe_ticker_in_universe_order(self) -> None:
        self.assertEqual(len(self.rows), len(UNIVERSE) + 1)
        self.assertEqual([row[0] for row in self.rows[1:]], list(UNIVERSE))
        for row in self.rows[1:]:
            self.assertEqual(len(row), 34)

    def test_business_context_and_gate_metrics_in_scored_row(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[1]))
        self.assertEqual(row["ticker"], "ORCL")
        self.assertEqual(row["company_name"], "ORCL Incorporated")
        self.assertEqual(row["business_description"], "ORCL makes widgets for industry.")
        self.assertEqual(row["industry"], "Specialty Widgets")
        self.assertEqual(row["sector"], "Industrials")
        self.assertEqual(row["market_cap"], "45710000000")
        self.assertEqual(row["f1_net_income_ttm"], "2000000000.0")
        self.assertEqual(row["f2_recommendation_mean"], "2.0")
        self.assertEqual(row["f3_price"], "42.5")
        self.assertEqual(row["f9_options_available"], "true")

    def test_fetch_error_row_has_empty_business_and_gate_metrics(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[6]))
        self.assertEqual(row["ticker"], "ANSS")
        for column in (
            "company_name",
            "business_description",
            "market_cap",
            "f1_net_income_ttm",
            "f2_recommendation_mean",
            "f3_price",
            "f9_options_available",
        ):
            self.assertEqual(row[column], "")

    def test_missing_field_recorded_as_empty_alongside_present_one(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[5]))
        self.assertEqual(row["ticker"], "HBAN")
        self.assertEqual(row["f1_net_income_ttm"], "1400000000.0")
        self.assertEqual(row["f1_operating_cash_flow_ttm"], "")

    def test_scored_row_carries_scores_and_recovered_metrics(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[1]))
        self.assertEqual(row["ticker"], "ORCL")
        self.assertEqual(row["verdict"], "scored")
        self.assertEqual(row["composite"], "94.5")
        self.assertEqual(row["f2_margin_score"], "66.0")
        self.assertEqual(row["f5_max_daily_move"], "0.0412")
        self.assertEqual(row["f5_realized_vol"], "0.2233")
        self.assertEqual(row["f6_dividend_yield"], "2.31")
        self.assertEqual(row["f7_realized_vol_30d"], "0.3155")
        self.assertEqual(row["f8_pct_below_2y_high"], "0.1842")
        self.assertEqual(row["f10_triggered"], "true")
        self.assertEqual(row["f10_days_to_earnings"], "10")
        self.assertEqual(row["f10_next_earnings_date"], "2026-08-04")
        self.assertEqual(row["f7_is_approximation"], "true")
        self.assertEqual(row["fail_reason"], "")

    def test_hard_gate_booleans_render_for_evaluated_names(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[4]))
        self.assertEqual(row["ticker"], "ABT")
        self.assertEqual(row["verdict"], "fitness_fail")
        self.assertEqual(row["f3_pass"], "false")
        self.assertEqual(row["composite"], "")
        self.assertIn("outside the $10.00-$50.00 band", row["fail_reason"])

    def test_fetch_error_row_leaves_gate_columns_empty(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[6]))
        self.assertEqual(row["ticker"], "ANSS")
        self.assertEqual(row["verdict"], "fetch_error")
        # No snapshot existed, so nothing was evaluated to fail.
        for column in ("f1_pass", "f2_pass", "f3_pass", "f4_pass", "f9_pass"):
            self.assertEqual(row[column], "")
        self.assertEqual(row["f7_is_approximation"], "true")

    def test_rescued_field_provenance_reaches_the_csv(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[5]))
        self.assertEqual(row["ticker"], "HBAN")
        self.assertEqual(row["verdict"], "missing_data")
        self.assertEqual(row["fmp_rescued_fields"], "operating_cash_flow_ttm")

    def test_dormant_rescue_leaves_provenance_empty(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[1]))
        self.assertEqual(row["fmp_rescued_fields"], "")

    def test_rows_are_built_purely(self) -> None:
        result = build_fixture(SECOND_RUN_DIFF)
        self.assertEqual(build_csv_rows(result), build_csv_rows(result))


class WriteReportAndCsvTests(unittest.TestCase):
    """The single IO edge: paired filenames, atomic write, no leftovers."""

    def test_writes_paired_timestamped_files(self) -> None:
        result = build_fixture(SECOND_RUN_DIFF)
        with tempfile.TemporaryDirectory() as directory:
            report_path, csv_path = write_report_and_csv(
                result,
                directory,
                RUN_TIMESTAMP,
            )
            self.assertEqual(report_path.name, "report_2026-07-25-192822.html")
            self.assertEqual(csv_path.name, "candidates_2026-07-25-192822.csv")
            self.assertTrue(report_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertEqual(report_path.read_text(), render_html(result))
            self.assertEqual(csv_path.read_text(), render_csv(result))
            # Temp siblings must not survive, and must not shadow state files.
            leftovers = sorted(p.name for p in Path(directory).glob("*.tmp"))
            self.assertEqual(leftovers, [])
            self.assertEqual(sorted(Path(directory).glob("run_state_*.json")), [])


if __name__ == "__main__":
    unittest.main()
