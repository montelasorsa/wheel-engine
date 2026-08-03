"""Offline tests for the pure provider-response transformations."""

from __future__ import annotations

import unittest

import pandas as pd

from wheel.snapshot import (
    DataUnavailableError,
    build_ticker_snapshot,
    normalize_fundamentals,
    normalize_price_history,
    truncate_description,
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

    def test_rejects_empty_price_history(self) -> None:
        with self.assertRaises(DataUnavailableError):
            normalize_price_history(pd.DataFrame())
