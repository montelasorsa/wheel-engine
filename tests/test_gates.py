"""Unit tests for the pure, rule-mapped Step 3 hard gates."""

from __future__ import annotations

import unittest

import pandas as pd

from wheel_screener.data import TickerSnapshot
from wheel_screener.screening import (
    GateFailureKind,
    HardGateThresholds,
    evaluate_hard_gates,
)


THRESHOLDS = HardGateThresholds(
    min_ttm_net_income=0.0,
    min_operating_cash_flow=0.0,
    max_mean_rating=2.5,
    min_price=10.0,
    max_price=50.0,
    pilot_bias_max_price=30.0,
)


def make_snapshot(
    *,
    net_income: float | None = 1.0,
    cash_flow: float | None = 1.0,
    recommendation_mean: float | None = 2.0,
    price: float | None = 20.0,
    option_expirations: tuple[str, ...] | None = ("2026-08-21",),
) -> TickerSnapshot:
    return TickerSnapshot(
        symbol="TEST",
        fundamentals={
            "net_income_ttm": net_income,
            "operating_cash_flow_ttm": cash_flow,
            "current_price": price,
        },
        price_history=pd.DataFrame(),
        dividends=pd.DataFrame(),
        analyst={"recommendation_mean": recommendation_mean},
        recommendation_summary=pd.DataFrame(),
        option_expirations=option_expirations,
    )


class HardGateTests(unittest.TestCase):
    def test_all_gates_pass_for_qualifying_snapshot(self) -> None:
        results = evaluate_hard_gates(make_snapshot(), THRESHOLDS)

        self.assertTrue(all(result.passed for result in results))
        self.assertTrue(results[2].flags[0].active)
        self.assertEqual(
            [result.gate_id for result in results],
            ["F1", "F2", "F3", "F4", "F9"],
        )

    def test_gate_metrics_record_observed_inputs_on_pass(self) -> None:
        f1, f2, f3, f4, f9 = evaluate_hard_gates(make_snapshot(), THRESHOLDS)

        self.assertEqual(
            f1.metrics,
            {"net_income_ttm": 1.0, "operating_cash_flow_ttm": 1.0},
        )
        self.assertEqual(f2.metrics, {"recommendation_mean": 2.0})
        self.assertEqual(f3.metrics, {"price": 20.0})
        self.assertEqual(f4.metrics, {"price": 20.0})
        self.assertEqual(f9.metrics, {"options_available": True})

    def test_gate_metrics_record_observed_inputs_on_fitness_fail(self) -> None:
        f1, _, f3, f4, f9 = evaluate_hard_gates(
            make_snapshot(net_income=-5.0, price=7.0, option_expirations=()),
            THRESHOLDS,
        )

        self.assertFalse(f1.passed)
        self.assertEqual(f1.metrics["net_income_ttm"], -5.0)
        self.assertEqual(f3.metrics, {"price": 7.0})
        self.assertEqual(f4.metrics, {"price": 7.0})
        self.assertEqual(f9.metrics, {"options_available": False})

    def test_gate_metrics_record_none_for_missing_fields(self) -> None:
        # F1's missing branch must still record the field that WAS present:
        # that pairing is the report's expected-vs-actual display.
        f1, f2, f3, f4, f9 = evaluate_hard_gates(
            make_snapshot(
                cash_flow=None,
                recommendation_mean=None,
                price=None,
                option_expirations=None,
            ),
            THRESHOLDS,
        )

        self.assertIs(f1.failure_kind, GateFailureKind.MISSING_DATA)
        self.assertEqual(
            f1.metrics,
            {"net_income_ttm": 1.0, "operating_cash_flow_ttm": None},
        )
        self.assertEqual(f2.metrics, {"recommendation_mean": None})
        self.assertEqual(f3.metrics, {"price": None})
        self.assertEqual(f4.metrics, {"price": None})
        self.assertEqual(f9.metrics, {"options_available": None})

    def test_threshold_boundaries_are_inclusive_except_profitability(self) -> None:
        results = evaluate_hard_gates(
            make_snapshot(
                net_income=0.0,
                cash_flow=0.0,
                recommendation_mean=2.5,
                price=10.0,
            ),
            THRESHOLDS,
        )

        self.assertFalse(results[0].passed)
        self.assertTrue(results[1].passed)
        self.assertTrue(results[2].passed)
        self.assertTrue(results[2].flags[0].active)
        self.assertTrue(results[3].passed)

    def test_each_missing_field_fails_with_an_explicit_reason(self) -> None:
        results = evaluate_hard_gates(
            make_snapshot(
                net_income=None,
                cash_flow=None,
                recommendation_mean=None,
                price=None,
                option_expirations=None,
            ),
            THRESHOLDS,
        )

        self.assertTrue(all(not result.passed for result in results))
        self.assertTrue(
            all(result.reason.startswith("Cannot evaluate:") for result in results)
        )
        self.assertTrue(
            all(
                result.failure_kind is GateFailureKind.MISSING_DATA
                for result in results
            )
        )

    def test_empty_options_metadata_fails(self) -> None:
        result = evaluate_hard_gates(
            make_snapshot(option_expirations=()),
            THRESHOLDS,
        )[-1]

        self.assertFalse(result.passed)
        self.assertIn("No listed option expirations", result.reason)


if __name__ == "__main__":
    unittest.main()
