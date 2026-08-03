"""Offline fixture tests for the pure F10 earnings flag."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import unittest

from wheel_screener.scoring import compute_earnings_proximity_flag


FIXTURE = (
    Path(__file__).parent / "fixtures" / "yfinance_calendar_cases.json"
)
RUN_DATE = date(2026, 7, 25)


class EarningsFlagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(FIXTURE.read_text())

    def test_near_earnings_triggers(self) -> None:
        result = compute_earnings_proximity_flag(
            self.cases["near"],
            run_date=RUN_DATE,
            threshold_days=45,
        )

        self.assertEqual(result.flag_id, "F10")
        self.assertTrue(result.triggered)
        self.assertEqual(result.days_to_earnings, 16)
        self.assertEqual(result.next_earnings_date, date(2026, 8, 10))

    def test_distant_earnings_does_not_trigger(self) -> None:
        result = compute_earnings_proximity_flag(
            self.cases["distant"],
            run_date=RUN_DATE,
            threshold_days=45,
        )

        self.assertFalse(result.triggered)
        self.assertEqual(result.days_to_earnings, 52)
        self.assertEqual(result.next_earnings_date, date(2026, 9, 15))

    def test_exact_45_day_boundary_does_not_trigger(self) -> None:
        result = compute_earnings_proximity_flag(
            self.cases["boundary"],
            run_date=RUN_DATE,
            threshold_days=45,
        )

        self.assertFalse(result.triggered)
        self.assertEqual(result.days_to_earnings, 45)

    def test_missing_calendar_is_non_triggering_and_non_failing(self) -> None:
        result = compute_earnings_proximity_flag(
            self.cases["missing"],
            run_date=RUN_DATE,
            threshold_days=45,
        )

        self.assertFalse(result.triggered)
        self.assertIsNone(result.days_to_earnings)
        self.assertIsNone(result.next_earnings_date)


if __name__ == "__main__":
    unittest.main()

