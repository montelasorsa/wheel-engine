"""Offline fixture tests for the pure CSV interchange renderer."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from wheel.snapshot import TickerSnapshot
from wheel.result import PipelineResult
from wheel.csv_output import (
    CSV_COLUMNS,
    build_csv_rows,
    render_csv,
    write_csv,
)
from wheel.flags import EarningsProximityFlag, FlaggedScoredTicker
from wheel.scoring import (
    IV_PROXY_APPROXIMATION,
    ScoredTicker,
    ScoreResult,
)
from wheel.gates import GateFailureKind, GateResult
from wheel.partition import EvaluatedTicker, HardGateBuckets
from wheel.run_state import Step5PipelineOutput


RUN_TIMESTAMP = datetime(2026, 7, 25, 19, 28, 22)
RUN_DATE = RUN_TIMESTAMP.date()

# ORCL scored and earnings-imminent, WY scored and far out, GEN scored with no
# calendar, ABT fitness fail, HBAN missing data (FMP-rescued field), ANSS fetch
# error. Six names, one per rendering branch.
UNIVERSE = ("ORCL", "WY", "GEN", "ABT", "HBAN", "ANSS")


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame({"date": [], "close": [], "adjusted_close": []})


def make_snapshot(symbol: str) -> TickerSnapshot:
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
            snapshot=make_snapshot("HBAN"),
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


class RenderCsvTests(unittest.TestCase):
    """Schema shape, null handling, and the metrics recovered from Step 6."""

    def setUp(self) -> None:
        self.text = render_csv(build_fixture(SECOND_RUN_DIFF))
        self.rows = list(csv.reader(io.StringIO(self.text)))

    def test_header_matches_specified_column_order(self) -> None:
        self.assertEqual(tuple(self.rows[0]), CSV_COLUMNS)
        self.assertEqual(len(self.rows[0]), 33)
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
            self.assertEqual(len(row), 33)

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

    def test_missing_data_row_keeps_business_context(self) -> None:
        row = dict(zip(CSV_COLUMNS, self.rows[5]))
        self.assertEqual(row["ticker"], "HBAN")
        self.assertEqual(row["verdict"], "missing_data")
        self.assertEqual(row["company_name"], "HBAN Incorporated")

    def test_rows_are_built_purely(self) -> None:
        result = build_fixture(SECOND_RUN_DIFF)
        self.assertEqual(build_csv_rows(result), build_csv_rows(result))


class WriteCsvTests(unittest.TestCase):
    """The single IO edge: timestamped filename, atomic write, no leftovers."""

    def test_writes_timestamped_csv(self) -> None:
        result = build_fixture(SECOND_RUN_DIFF)
        with tempfile.TemporaryDirectory() as directory:
            csv_path = write_csv(result, directory, RUN_TIMESTAMP)
            self.assertEqual(csv_path.name, "candidates_2026-07-25-192822.csv")
            self.assertTrue(csv_path.exists())
            self.assertEqual(csv_path.read_text(), render_csv(result))
            # Temp siblings must not survive, and must not shadow state files.
            leftovers = sorted(p.name for p in Path(directory).glob("*.tmp"))
            self.assertEqual(leftovers, [])
            self.assertEqual(sorted(Path(directory).glob("run_state_*.json")), [])


if __name__ == "__main__":
    unittest.main()
