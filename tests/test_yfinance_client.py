"""Offline tests for the pure yfinance response transformations."""

from __future__ import annotations

import unittest

import pandas as pd

from wheel_screener.data.yfinance_client import (
    DataUnavailableError,
    RequestThrottle,
    YFinanceFetchPolicy,
    build_ticker_snapshot,
    fetch_ticker_snapshot,
    normalize_fundamentals,
    normalize_price_history,
    truncate_description,
    yfinance_policy_from_config,
)


class TruncateDescriptionTests(unittest.TestCase):
    def test_takes_first_sentence_when_shorter_than_cap(self) -> None:
        text = (
            "Devon Energy Corporation operates as an oil and gas producer. "
            "It was founded in 1971 and is headquartered in Oklahoma City."
        )
        self.assertEqual(
            truncate_description(text),
            "Devon Energy Corporation operates as an oil and gas producer.",
        )

    def test_corporate_suffix_is_not_a_sentence_boundary(self) -> None:
        text = "Lamb Weston Holdings, Inc. engages in frozen potato products."
        self.assertEqual(truncate_description(text), text)

    def test_long_first_sentence_hard_cuts_with_ellipsis(self) -> None:
        text = ("word " * 60).strip() + "."
        result = truncate_description(text)
        self.assertLessEqual(len(result), 120)
        self.assertTrue(result.endswith("…"))

    def test_none_and_empty_fail_open(self) -> None:
        self.assertIsNone(truncate_description(None))
        self.assertIsNone(truncate_description(""))
        self.assertIsNone(truncate_description("   "))

    def test_whitespace_is_collapsed(self) -> None:
        self.assertEqual(
            truncate_description("Makes  widgets\nand gadgets worldwide."),
            "Makes widgets and gadgets worldwide.",
        )


class NormalizeFundamentalsBusinessFieldsTests(unittest.TestCase):
    def test_captures_business_description(self) -> None:
        fundamentals = normalize_fundamentals(
            {
                "longName": "Devon Energy Corporation",
                "longBusinessSummary": (
                    "Devon Energy Corporation operates as an oil and gas "
                    "producer. It was founded in 1971."
                ),
                "sector": "Energy",
                "industry": "Oil & Gas E&P",
                "marketCap": 29_000_000_000,
            }
        )
        self.assertEqual(
            fundamentals["business_description"],
            "Devon Energy Corporation operates as an oil and gas producer.",
        )
        self.assertEqual(fundamentals["company_name"], "Devon Energy Corporation")
        self.assertEqual(fundamentals["sector"], "Energy")
        self.assertEqual(fundamentals["market_cap"], 29_000_000_000)

    def test_completely_empty_info_fails_open_to_none(self) -> None:
        fundamentals = normalize_fundamentals({})
        for field_name in (
            "company_name",
            "business_description",
            "sector",
            "industry",
            "market_cap",
        ):
            self.assertIsNone(fundamentals[field_name])


class BuildTickerSnapshotTests(unittest.TestCase):
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

    def test_builds_normalized_snapshot_from_supplied_provider_data(self) -> None:
        info = {
            "longName": "The Coca-Cola Company",
            "currency": "USD",
            "currentPrice": 72.0,
            "marketCap": 310_000_000_000,
            "netIncomeToCommon": 10_500_000_000,
            "operatingCashflow": 12_000_000_000,
            "dividendYield": 2.8,
            "recommendationMean": 2.1,
            "recommendationKey": "buy",
            "numberOfAnalystOpinions": 20,
        }
        dividends = pd.Series(
            [0.51],
            index=pd.DatetimeIndex(
                ["2026-07-23 16:00:00"],
                tz="America/New_York",
                name="Date",
            ),
            name="Dividends",
        )
        recommendations = pd.DataFrame(
            {
                "period": ["0m"],
                "strongBuy": [5],
                "buy": [10],
                "hold": [5],
                "sell": [0],
                "strongSell": [0],
            }
        )

        snapshot = build_ticker_snapshot(
            " ko ",
            info=info,
            history=self.history,
            dividends=dividends,
            recommendations=recommendations,
        )

        self.assertEqual(snapshot.symbol, "KO")
        self.assertEqual(snapshot.fundamentals["net_income_ttm"], 10_500_000_000)
        self.assertEqual(snapshot.fundamentals["dividend_yield_percent"], 2.8)
        self.assertEqual(snapshot.price_history.columns[0], "date")
        self.assertEqual(len(snapshot.price_history), 2)
        self.assertEqual(snapshot.dividends.iloc[0]["dividend"], 0.51)
        self.assertEqual(snapshot.analyst["recommendation_mean"], 2.1)
        self.assertIn("strong_buy", snapshot.recommendation_summary.columns)
        self.assertEqual(
            snapshot.field_sources["operating_cash_flow_ttm"],
            "yfinance",
        )

    def test_rejects_empty_price_history(self) -> None:
        with self.assertRaises(DataUnavailableError):
            normalize_price_history(pd.DataFrame())

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
