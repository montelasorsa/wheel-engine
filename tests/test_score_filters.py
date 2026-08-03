"""Offline tests for Step 4 score filters and screen partitioning."""

from __future__ import annotations

import unittest
from dataclasses import replace

import pandas as pd

from wheel_screener.data import TickerSnapshot
from wheel_screener.scoring import (
    CompositeWeights,
    ScoringThresholds,
    score_eligible_snapshot,
)
from wheel_screener.scoring.score_filters import (
    IV_PROXY_APPROXIMATION,
    IneligibleForScoringError,
    score_chart_position,
    score_dividend,
    score_iv_proxy,
    score_stability,
)
from wheel_screener.screening import (
    GateFailureKind,
    HardGateThresholds,
    evaluate_hard_gates,
    partition_hard_gates,
)


HARD_GATE_THRESHOLDS = HardGateThresholds(
    min_ttm_net_income=0.0,
    min_operating_cash_flow=0.0,
    max_mean_rating=2.5,
    min_price=10.0,
    max_price=50.0,
    pilot_bias_max_price=30.0,
)

SCORING_THRESHOLDS = ScoringThresholds(
    stability_history_days=365,
    max_single_day_move=0.15,
    max_realized_vol_universe_percentile=0.75,
    iv_lookback_trading_days=30,
    annualization_trading_days=252,
    iv_quality_zone_min=0.20,
    iv_quality_zone_max=0.40,
    iv_high_vol_penalty_above=0.50,
    chart_history_days=730,
    min_below_two_year_high=0.05,
    max_mean_rating=2.5,
)

WEIGHTS = CompositeWeights(
    stability=0.30,
    iv_proxy_quality=0.25,
    chart_position=0.20,
    dividend=0.15,
    analyst_strength=0.10,
)


def make_history(daily_moves: list[float]) -> pd.DataFrame:
    prices = [20.0]
    for move in daily_moves:
        prices.append(prices[-1] * (1.0 + move))
    dates = pd.bdate_range("2024-01-02", periods=len(prices), tz="UTC")
    return pd.DataFrame(
        {
            "date": dates,
            "close": prices,
            "adjusted_close": prices,
        }
    )


def make_snapshot(
    symbol: str = "TEST",
    *,
    net_income: float | None = 1_000_000.0,
    cash_flow: float | None = 2_000_000.0,
    recommendation_mean: float | None = 2.0,
    price: float | None = 20.0,
    options: tuple[str, ...] | None = ("2026-08-21",),
    daily_moves: list[float] | None = None,
    dividend: float = 0.25,
) -> TickerSnapshot:
    moves = daily_moves or ([0.01, -0.009] * 200)
    dividends = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-01-01", tz="UTC")],
            "dividend": [dividend],
        }
    )
    return TickerSnapshot(
        symbol=symbol,
        fundamentals={
            "net_income_ttm": net_income,
            "operating_cash_flow_ttm": cash_flow,
            "current_price": price,
            "dividend_yield_percent": 2.0 if dividend > 0 else None,
        },
        price_history=make_history(moves),
        dividends=dividends,
        analyst={"recommendation_mean": recommendation_mean},
        recommendation_summary=pd.DataFrame(),
        option_expirations=options,
    )


class ScoreFilterTests(unittest.TestCase):
    def test_high_iv_proxy_scores_lower_and_is_always_labeled(self) -> None:
        quality = make_snapshot(daily_moves=[0.02, -0.02] * 40)
        high = make_snapshot(daily_moves=[0.06, -0.06] * 40)

        quality_result = score_iv_proxy(quality, SCORING_THRESHOLDS)
        high_result = score_iv_proxy(high, SCORING_THRESHOLDS)

        self.assertGreater(quality_result.score, high_result.score)
        self.assertTrue(high_result.is_approximation)
        self.assertEqual(
            high_result.approximation_note,
            IV_PROXY_APPROXIMATION,
        )
        self.assertIn("APPROXIMATION:", high_result.reason)

    def test_metrics_carry_raw_inputs_and_stay_empty_when_unscoreable(
        self,
    ) -> None:
        snapshot = make_snapshot(daily_moves=[0.02, -0.02] * 40)

        stability = score_stability(snapshot, SCORING_THRESHOLDS, 0.50)
        dividend = score_dividend(snapshot)
        iv_proxy = score_iv_proxy(snapshot, SCORING_THRESHOLDS)
        chart = score_chart_position(snapshot, SCORING_THRESHOLDS)

        self.assertEqual(
            sorted(stability.metrics), ["max_daily_move", "realized_vol"]
        )
        self.assertAlmostEqual(stability.metrics["max_daily_move"], 0.02, places=6)
        self.assertEqual(dividend.metrics["dividend_yield"], 2.0)
        self.assertGreater(iv_proxy.metrics["realized_vol_30d"], 0.0)
        self.assertGreaterEqual(chart.metrics["pct_below_2y_high"], 0.0)

        # Fail-closed: a filter that cannot evaluate must not invent a number.
        # A single price row yields no daily returns at all.
        no_history = replace(snapshot, price_history=make_history([]))
        self.assertEqual(
            score_stability(no_history, SCORING_THRESHOLDS, 0.50).metrics, {}
        )
        self.assertEqual(
            score_stability(snapshot, SCORING_THRESHOLDS, None).metrics, {}
        )
        self.assertEqual(
            score_iv_proxy(no_history, SCORING_THRESHOLDS).metrics, {}
        )

    def test_chart_position_penalizes_within_five_percent_of_high(self) -> None:
        near_high = make_snapshot(daily_moves=[0.002] * 400)
        away_from_high = make_snapshot(
            daily_moves=([0.002] * 399) + [-0.10]
        )

        self.assertEqual(
            score_chart_position(near_high, SCORING_THRESHOLDS).score,
            0.0,
        )
        self.assertEqual(
            score_chart_position(away_from_high, SCORING_THRESHOLDS).score,
            100.0,
        )

    def test_composite_is_bounded_and_only_scores_hard_gate_passers(self) -> None:
        snapshot = make_snapshot()
        gates = evaluate_hard_gates(snapshot, HARD_GATE_THRESHOLDS)

        scored = score_eligible_snapshot(
            snapshot,
            gates,
            SCORING_THRESHOLDS,
            WEIGHTS,
            universe_volatility_percentile=0.50,
        )

        self.assertIsNotNone(scored.composite_score)
        self.assertGreaterEqual(scored.composite_score, 0.0)
        self.assertLessEqual(scored.composite_score, 100.0)
        self.assertTrue(scored.contains_approximation)

        failed_snapshot = make_snapshot(price=5.0)
        failed_gates = evaluate_hard_gates(
            failed_snapshot,
            HARD_GATE_THRESHOLDS,
        )
        with self.assertRaises(IneligibleForScoringError):
            score_eligible_snapshot(
                failed_snapshot,
                failed_gates,
                SCORING_THRESHOLDS,
                WEIGHTS,
                universe_volatility_percentile=0.50,
            )

    def test_partitions_fitness_and_missing_data_only_failures(self) -> None:
        passed = make_snapshot("PASS")
        fitness = make_snapshot("FITNESS", price=5.0)
        missing = make_snapshot("MISSING", cash_flow=None)

        buckets = partition_hard_gates(
            [passed, fitness, missing],
            HARD_GATE_THRESHOLDS,
        )

        self.assertEqual(
            [item.snapshot.symbol for item in buckets.passed],
            ["PASS"],
        )
        self.assertEqual(
            [item.snapshot.symbol for item in buckets.failed_fitness],
            ["FITNESS"],
        )
        self.assertEqual(
            [item.snapshot.symbol for item in buckets.failed_missing_data],
            ["MISSING"],
        )
        missing_failures = [
            result
            for result in buckets.failed_missing_data[0].gate_results
            if not result.passed
        ]
        self.assertTrue(
            all(
                result.failure_kind is GateFailureKind.MISSING_DATA
                for result in missing_failures
            )
        )


if __name__ == "__main__":
    unittest.main()

