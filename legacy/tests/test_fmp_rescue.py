"""Offline tests for fallback-only FMP rescue orchestration."""

from __future__ import annotations

import unittest

import pandas as pd

from wheel_screener.data import TickerSnapshot
from wheel_screener.screening import (
    HardGateThresholds,
    evaluate_hard_gates_for_snapshots,
    partition_evaluated_hard_gates,
    rescue_enabled_from_config,
    rescue_operating_cash_flow_ttm,
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
    symbol: str,
    *,
    operating_cash_flow: float | None,
    recommendation_mean: float = 2.0,
    net_income: float = 1_000_000.0,
) -> TickerSnapshot:
    sources = {
        "current_price": "yfinance",
        "net_income_ttm": "yfinance",
    }
    if operating_cash_flow is not None:
        sources["operating_cash_flow_ttm"] = "yfinance"
    return TickerSnapshot(
        symbol=symbol,
        fundamentals={
            "current_price": 20.0,
            "net_income_ttm": net_income,
            "operating_cash_flow_ttm": operating_cash_flow,
        },
        price_history=pd.DataFrame(),
        dividends=pd.DataFrame(),
        analyst={"recommendation_mean": recommendation_mean},
        recommendation_summary=pd.DataFrame(),
        option_expirations=("2026-08-21",),
        field_sources=sources,
    )


class FmpRescueTests(unittest.TestCase):
    def test_queries_only_missing_field_and_rescues_with_provenance(self) -> None:
        clean_symbols = ("DVN", "T", "VZ", "PFE", "MOS")
        missing_symbols = ("KMI", "HBAN", "KEY")
        snapshots = [
            *(make_snapshot(symbol, operating_cash_flow=2_000_000.0)
              for symbol in clean_symbols),
            *(make_snapshot(symbol, operating_cash_flow=None)
              for symbol in missing_symbols),
        ]
        initial = evaluate_hard_gates_for_snapshots(snapshots, THRESHOLDS)
        calls = []
        fmp_values = {
            "KMI": 5_331_000_000.0,
            "HBAN": 2_400_000_000.0,
            "KEY": 1_700_000_000.0,
        }

        def fake_fetch(symbol: str) -> float:
            calls.append(symbol)
            return fmp_values[symbol]

        batch = rescue_operating_cash_flow_ttm(
            initial,
            THRESHOLDS,
            fake_fetch,
            enabled=True,
        )
        buckets = partition_evaluated_hard_gates(batch.evaluated_tickers)

        self.assertEqual(calls, list(missing_symbols))
        self.assertTrue(set(clean_symbols).isdisjoint(batch.queried_symbols))
        self.assertEqual(len(buckets.passed), 8)
        self.assertEqual(len(buckets.failed_missing_data), 0)
        by_symbol = {
            item.snapshot.symbol: item for item in batch.evaluated_tickers
        }
        for symbol in missing_symbols:
            rescued = by_symbol[symbol]
            self.assertEqual(
                rescued.snapshot.fundamentals["operating_cash_flow_ttm"],
                fmp_values[symbol],
            )
            self.assertEqual(
                rescued.snapshot.field_sources["operating_cash_flow_ttm"],
                "fmp",
            )
            self.assertTrue(rescued.gate_results[0].passed)

    def test_only_f1_is_replaced_after_rescue(self) -> None:
        initial = evaluate_hard_gates_for_snapshots(
            [make_snapshot("KMI", operating_cash_flow=None)],
            THRESHOLDS,
        )

        batch = rescue_operating_cash_flow_ttm(
            initial,
            THRESHOLDS,
            lambda _symbol: 5_331_000_000.0,
            enabled=True,
        )

        before = initial[0].gate_results
        after = batch.evaluated_tickers[0].gate_results
        self.assertIsNot(before[0], after[0])
        for before_gate, after_gate in zip(before[1:], after[1:]):
            self.assertIs(before_gate, after_gate)

    def test_null_fmp_result_stays_fail_closed(self) -> None:
        initial = evaluate_hard_gates_for_snapshots(
            [make_snapshot("KMI", operating_cash_flow=None)],
            THRESHOLDS,
        )

        batch = rescue_operating_cash_flow_ttm(
            initial,
            THRESHOLDS,
            lambda _symbol: None,
            enabled=True,
        )
        buckets = partition_evaluated_hard_gates(batch.evaluated_tickers)

        self.assertEqual(batch.queried_symbols, ("KMI",))
        self.assertEqual(len(buckets.failed_missing_data), 1)
        self.assertEqual(
            buckets.failed_missing_data[0].gate_results[0].reason,
            initial[0].gate_results[0].reason,
        )

    def test_does_not_query_when_another_gate_already_fails(self) -> None:
        initial = evaluate_hard_gates_for_snapshots(
            [
                make_snapshot(
                    "BLOCKED",
                    operating_cash_flow=None,
                    recommendation_mean=3.0,
                )
            ],
            THRESHOLDS,
        )
        calls = []

        batch = rescue_operating_cash_flow_ttm(
            initial,
            THRESHOLDS,
            lambda symbol: calls.append(symbol) or 1.0,
            enabled=True,
        )

        self.assertEqual(calls, [])
        self.assertEqual(batch.queried_symbols, ())

    def test_does_not_replace_existing_yfinance_value(self) -> None:
        initial = evaluate_hard_gates_for_snapshots(
            [make_snapshot("CLEAN", operating_cash_flow=2_000_000.0)],
            THRESHOLDS,
        )
        calls = []

        batch = rescue_operating_cash_flow_ttm(
            initial,
            THRESHOLDS,
            lambda symbol: calls.append(symbol) or 9_000_000.0,
            enabled=True,
        )

        self.assertEqual(calls, [])
        snapshot = batch.evaluated_tickers[0].snapshot
        self.assertEqual(
            snapshot.fundamentals["operating_cash_flow_ttm"],
            2_000_000.0,
        )
        self.assertEqual(
            snapshot.field_sources["operating_cash_flow_ttm"],
            "yfinance",
        )

    def test_rescue_defaults_off_and_makes_zero_calls(self) -> None:
        initial = evaluate_hard_gates_for_snapshots(
            [make_snapshot("KMI", operating_cash_flow=None)],
            THRESHOLDS,
        )
        calls = []

        batch = rescue_operating_cash_flow_ttm(
            initial,
            THRESHOLDS,
            lambda symbol: calls.append(symbol) or 5_331_000_000.0,
        )

        self.assertEqual(calls, [])
        self.assertIs(batch.evaluated_tickers[0], initial[0])
        self.assertFalse(batch.attempts[0].queried_fmp)

    def test_config_flag_defaults_false_and_requires_boolean(self) -> None:
        self.assertFalse(rescue_enabled_from_config({}))
        self.assertFalse(
            rescue_enabled_from_config({"RESCUE_ENABLED": False})
        )
        self.assertTrue(
            rescue_enabled_from_config({"RESCUE_ENABLED": True})
        )
        with self.assertRaises(ValueError):
            rescue_enabled_from_config({"RESCUE_ENABLED": "false"})


if __name__ == "__main__":
    unittest.main()
