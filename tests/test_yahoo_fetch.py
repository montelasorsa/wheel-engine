"""Offline tests for the MCP data boundary: pacing, retries, and policy.

No network is touched -- every provider call is a fake passed in through
`ticker_factory`, and sleeps are captured rather than performed.
"""

from __future__ import annotations

import unittest

import pandas as pd

from wheel_mcp.yahoo import (
    RequestThrottle,
    YFinanceFetchPolicy,
    fetch_ticker_snapshot,
    yfinance_policy_from_config,
)


class YahooFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        dates = pd.DatetimeIndex(
            ["2026-07-22 16:00:00", "2026-07-23 16:00:00"],
            tz="America/New_York",
            name="Date",
        )
        self.history = pd.DataFrame(
            {
                "Open": [70.0, 71.0],
                "High": [72.0, 72.5],
                "Low": [69.5, 70.5],
                "Close": [71.0, 72.0],
                "Adj Close": [70.8, 71.8],
                "Volume": [10_000, 11_000],
                "Dividends": [0.0, 0.51],
                "Stock Splits": [0.0, 0.0],
            },
            index=dates,
        )

    def test_fetch_retries_whole_ticker_with_backoff(self) -> None:
        recommendations = pd.DataFrame(
            {
                "period": ["0m"],
                "strongBuy": [2],
                "buy": [3],
                "hold": [1],
                "sell": [0],
                "strongSell": [0],
            }
        )

        class FakeTicker:
            def __init__(self, fail_info: bool) -> None:
                self.fail_info = fail_info

            def get_info(self):
                if self.fail_info:
                    raise RuntimeError("temporary provider failure")
                return {
                    "currentPrice": 20.0,
                    "netIncomeToCommon": 1.0,
                    "operatingCashflow": 2.0,
                    "recommendationMean": 2.0,
                }

            def history(self, **_kwargs):
                return self_history

            def get_dividends(self, **_kwargs):
                return pd.Series(dtype=float)

            def get_recommendations_summary(self):
                return recommendations

            @property
            def options(self):
                return ("2026-08-21",)

        self_history = self.history
        factory_calls = []

        def factory(_symbol):
            factory_calls.append(_symbol)
            return FakeTicker(fail_info=len(factory_calls) == 1)

        class RecordingThrottle:
            def __init__(self) -> None:
                self.calls = []

            def wait(self, interval):
                self.calls.append(interval)

        throttle = RecordingThrottle()
        sleeps = []
        policy = YFinanceFetchPolicy(
            min_request_interval_seconds=0.25,
            max_attempts=2,
            initial_backoff_seconds=2.0,
            backoff_multiplier=2.0,
        )

        snapshot = fetch_ticker_snapshot(
            "TEST",
            ticker_factory=factory,
            policy=policy,
            throttle=throttle,
            retry_sleeper=sleeps.append,
        )

        self.assertEqual(snapshot.symbol, "TEST")
        self.assertEqual(factory_calls, ["TEST", "TEST"])
        self.assertEqual(sleeps, [2.0])
        self.assertEqual(throttle.calls, [0.25] * 6)

    def test_request_throttle_serializes_provider_slots(self) -> None:
        now = [10.0]
        sleeps = []

        def sleeper(delay):
            sleeps.append(delay)
            now[0] += delay

        throttle = RequestThrottle(
            clock=lambda: now[0],
            sleeper=sleeper,
        )

        throttle.wait(0.5)
        throttle.wait(0.5)
        throttle.wait(0.5)

        self.assertEqual(sleeps, [0.5, 0.5])

    def test_policy_is_loaded_from_config(self) -> None:
        config = {
            "data_sources": {
                "yfinance": {
                    "min_request_interval_seconds": 0.15,
                    "max_attempts": 3,
                    "initial_backoff_seconds": 2.0,
                    "backoff_multiplier": 2.0,
                }
            }
        }

        policy = yfinance_policy_from_config(config)

        self.assertEqual(policy.min_request_interval_seconds, 0.15)
        self.assertEqual(policy.max_attempts, 3)
        self.assertEqual(policy.initial_backoff_seconds, 2.0)
        self.assertEqual(policy.backoff_multiplier, 2.0)


if __name__ == "__main__":
    unittest.main()
