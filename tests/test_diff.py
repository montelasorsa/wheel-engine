"""Synthesized fixture tests for the pure ST-SEL-07 diff."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from wheel_screener.screening import (
    compute_diff,
    load_prior_state,
    save_current_state,
)


FIXTURES = Path(__file__).parent / "fixtures"


class RunDiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prior = json.loads(
            (FIXTURES / "run_state_prior.json").read_text()
        )
        cls.current = json.loads(
            (FIXTURES / "run_state_current.json").read_text()
        )

    def test_first_run_has_empty_change_lists(self) -> None:
        result = compute_diff(None, self.current)

        self.assertTrue(result["first_run"])
        self.assertEqual(result["newly_qualified"], [])
        self.assertEqual(result["newly_dropped"], [])
        self.assertEqual(result["unchanged"], [])

    def test_newly_qualified_includes_prior_verdict(self) -> None:
        result = compute_diff(self.prior, self.current)

        self.assertEqual(
            result["newly_qualified"],
            [{"ticker": "BBB", "prior_verdict": "fitness_fail"}],
        )

    def test_newly_dropped_includes_reason_and_fetch_error(self) -> None:
        result = compute_diff(self.prior, self.current)

        self.assertEqual(
            result["newly_dropped"],
            [
                {
                    "ticker": "CCC",
                    "current_verdict": "fetch_error",
                    "reason": "fetch error",
                },
                {
                    "ticker": "DDD",
                    "current_verdict": "missing_data",
                    "reason": "F1: missing operating_cash_flow_ttm",
                },
            ],
        )

    def test_unchanged_tracks_qualification_not_composite(self) -> None:
        result = compute_diff(self.prior, self.current)

        self.assertEqual(result["unchanged"], ["AAA"])

    def test_state_io_round_trip_and_missing_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run_state_2026-07-25-120000.json"
            self.assertIsNone(load_prior_state(path))

            saved = save_current_state(path, self.current)

            self.assertEqual(saved, path)
            self.assertEqual(load_prior_state(path), self.current)


if __name__ == "__main__":
    unittest.main()

