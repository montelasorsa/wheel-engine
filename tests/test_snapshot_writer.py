"""Offline tests for the Layer 0 contract emitter.

Provider data is faked at the same boundary the yahoo tests fake it; no
network. The one non-negotiable property: everything the emitter writes
satisfies the Layer 0 contract, byte-for-byte JSON-serializable.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from wheel.snapshot import build_ticker_snapshot
from wheel.snapshot_schema import validate_snapshot
from wheel_mcp.snapshot_writer import (
    build_snapshot_document,
    write_snapshot_document,
)

RUN_DATE = date(2026, 8, 15)
FETCHED_AT = datetime(2026, 8, 15, 10, 42, tzinfo=timezone.utc)


def make_provider_snapshot(**info_overrides):
    dates = pd.date_range(
        "2024-08-15", periods=503, freq="B", tz="America/New_York"
    )
    closes = [20.0 + 0.01 * i for i in range(len(dates))]
    history = pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 0.5 for c in closes],
            "Low": [c - 0.5 for c in closes],
            "Close": closes,
            "Adj Close": closes,
            "Volume": [1_000_000] * len(dates),
            "Dividends": [0.0] * len(dates),
            "Stock Splits": [0.0] * len(dates),
        },
        index=dates.rename("Date"),
    )
    info = {
        "longName": "Fixture Corp",
        "quoteType": "EQUITY",
        "sector": "Industrials",
        "industry": "Widgets",
        "marketCap": 5_000_000_000,
        "currency": "USD",
        "exchange": "NYQ",
        "currentPrice": closes[-1],
        "netIncomeToCommon": 1_000_000_000,
        "operatingCashflow": 2_000_000_000,
        "totalRevenue": 9_000_000_000,
        "dividendYield": 2.5,
        "recommendationMean": 2.0,
        "recommendationKey": "buy",
        "numberOfAnalystOpinions": 11,
    }
    info.update(info_overrides)
    dividends = pd.Series(
        [0.25],
        index=pd.DatetimeIndex(["2026-06-10"], tz="America/New_York", name="Date"),
        name="Dividends",
    )
    return build_ticker_snapshot(
        "FIX",
        info=info,
        history=history,
        dividends=dividends,
        recommendations=pd.DataFrame({"period": ["0m"], "strongBuy": [5]}),
        option_expirations=("2026-09-18", "2026-10-16"),
    )


CALENDAR = {"Earnings Date": ["2026-10-08"]}


def build_document(**kwargs):
    defaults = dict(
        calendar=CALENDAR,
        run_date=RUN_DATE,
        fetched_at=FETCHED_AT,
        thesis_note_exists=True,
        thesis_note_path="notes/FIX.md",
    )
    defaults.update(kwargs)
    return build_snapshot_document(make_provider_snapshot(), **defaults)


class BuildDocumentTests(unittest.TestCase):
    def test_document_satisfies_the_contract(self) -> None:
        self.assertEqual(validate_snapshot(build_document()), ())

    def test_document_is_json_serializable_with_native_types(self) -> None:
        # numpy scalars leak through pandas; the emitter must coerce them.
        text = json.dumps(build_document())
        self.assertIn('"ticker": "FIX"', text)

    def test_identity_carries_quote_type(self) -> None:
        self.assertEqual(build_document()["identity"]["quote_type"], "EQUITY")

    def test_derived_metrics_are_computed(self) -> None:
        document = build_document()
        self.assertIsNotNone(document["stability"]["max_single_day_move_1y"])
        self.assertIsNotNone(document["stability"]["realized_vol_1y"])
        self.assertIsNotNone(document["volatility"]["realized_vol_30d"])
        self.assertAlmostEqual(
            document["chart_position"]["two_year_high"],
            document["price"]["current"],
            places=6,
        )
        self.assertAlmostEqual(
            document["chart_position"]["pct_below_two_year_high"], 0.0
        )

    def test_iv_is_null_and_declared_a_proxy(self) -> None:
        document = build_document()
        self.assertIsNone(document["volatility"]["implied_volatility"])
        self.assertTrue(document["volatility"]["is_proxy"])

    def test_earnings_section_from_calendar(self) -> None:
        earnings = build_document()["earnings"]
        self.assertEqual(earnings["next_earnings_date"], "2026-10-08")
        self.assertEqual(earnings["days_to_earnings"], 54)
        self.assertEqual(earnings["earnings_week"], "2026-W41")

    def test_no_calendar_degrades_to_nulls(self) -> None:
        earnings = build_document(calendar=None)["earnings"]
        self.assertIsNone(earnings["next_earnings_date"])
        self.assertIsNone(earnings["days_to_earnings"])
        self.assertIsNone(earnings["earnings_week"])

    def test_dividend_derived_from_history(self) -> None:
        dividend = build_document()["dividend"]
        self.assertTrue(dividend["pays_dividend"])
        self.assertEqual(dividend["last_ex_date"], "2026-06-10")
        self.assertEqual(dividend["yield_percent"], 2.5)

    def test_operator_gates_carry_thesis_but_never_answer_willingness(self) -> None:
        gates = build_document()["operator_gates"]
        self.assertTrue(gates["thesis_note_exists"])
        self.assertEqual(gates["thesis_note_path"], "notes/FIX.md")
        # Unasked is not declined; the emitter must never invent an answer.
        self.assertIsNone(gates["willing_to_own_12mo"])

    def test_missing_info_fields_fail_open_to_null(self) -> None:
        document = build_snapshot_document(
            make_provider_snapshot(
                netIncomeToCommon=None, sector=None, marketCap=None
            ),
            calendar=CALENDAR,
            run_date=RUN_DATE,
            fetched_at=FETCHED_AT,
            thesis_note_exists=False,
            thesis_note_path=None,
        )
        self.assertEqual(validate_snapshot(document), ())
        self.assertIsNone(document["fundamentals"]["net_income_ttm"])
        self.assertIsNone(document["identity"]["sector"])
        self.assertIsNone(document["identity"]["market_cap"])


class WriteDocumentTests(unittest.TestCase):
    def test_writes_contract_filename_atomically(self) -> None:
        document = build_document()
        with tempfile.TemporaryDirectory() as directory:
            path = write_snapshot_document(document, directory)
            self.assertEqual(path.name, "2026-08-15_FIX.json")
            reloaded = json.loads(path.read_text())
            self.assertEqual(validate_snapshot(reloaded), ())
            self.assertEqual(reloaded, document)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
