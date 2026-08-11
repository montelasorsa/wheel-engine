"""The fallback degrades the run; it never ends it.

Acquisition takes hours at universe scale. An absent key or a timed-out
fallback request must leave the null in place and keep going -- but it must say
so once, loudly, and count the rest. Silence and abort are both wrong.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from wheel_mcp.acquire import FallbackFiller
from wheel_mcp.fmp import FmpConfigurationError

LIVE_GOLDEN = Path(__file__).parent / "golden" / "live"


def document_with_null_income():
    base = json.loads((LIVE_GOLDEN / "2026-08-06_F.json").read_text())
    base["fundamentals"]["net_income_ttm"] = None
    return base


class Say:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        self.lines.append(message)

    def joined(self) -> str:
        return "\n".join(self.lines)


class MissingKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.say = Say()
        self.filler = FallbackFiller(
            say=self.say,
            load_key=self._raise,
        )

    @staticmethod
    def _raise():
        raise FmpConfigurationError("FMP_API_KEY is not configured; see .env.example.")

    def test_a_missing_key_disables_the_fallback_without_raising(self) -> None:
        self.assertFalse(self.filler.enabled)
        self.assertIn("FMP DISABLED", self.say.joined())

    def test_it_is_announced_once_at_construction_not_per_name(self) -> None:
        for _ in range(5):
            self.filler.apply(document_with_null_income())
        self.assertEqual(self.say.joined().count("FMP DISABLED"), 1)

    def test_the_document_passes_through_with_its_null_intact(self) -> None:
        result = self.filler.apply(document_with_null_income())
        self.assertIsNone(result["fundamentals"]["net_income_ttm"])
        self.assertEqual(result["source"]["provider"], "yfinance")

    def test_the_summary_reports_it_disabled(self) -> None:
        self.assertEqual(
            self.filler.summary(),
            {
                "enabled": False,
                "names_filled": 0,
                "fields_filled": 0,
                "request_failures": 0,
            },
        )


class RequestFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.say = Say()
        self.filler = FallbackFiller(say=self.say, load_key=lambda: "a-key")

    def test_a_failing_fallback_does_not_escape_into_the_run(self) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("network gone")

        import wheel_mcp.acquire as acquire

        original = acquire.fill_document
        acquire.fill_document = boom
        self.addCleanup(setattr, acquire, "fill_document", original)

        for _ in range(3):
            result = self.filler.apply(document_with_null_income())
            self.assertIsNone(result["fundamentals"]["net_income_ttm"])

        self.assertEqual(self.filler.summary()["request_failures"], 3)
        # Announced once, counted three times: a per-name line would bury the
        # run's real progress output under thousands of duplicates.
        self.assertEqual(self.say.joined().count("FMP ERROR"), 1)

    def test_a_successful_fill_is_counted_and_announced(self) -> None:
        import wheel_mcp.acquire as acquire

        def fake_fill(doc, _key):
            filled = json.loads(json.dumps(doc))
            filled["fundamentals"]["net_income_ttm"] = 42.0
            filled["source"]["provider"] = "yfinance+fmp"
            filled["source"]["partial"] = True
            return filled, ("fundamentals.net_income_ttm",)

        original = acquire.fill_document
        acquire.fill_document = fake_fill
        self.addCleanup(setattr, acquire, "fill_document", original)

        result = self.filler.apply(document_with_null_income())
        self.assertEqual(result["fundamentals"]["net_income_ttm"], 42.0)
        self.assertEqual(
            self.filler.summary(),
            {
                "enabled": True,
                "names_filled": 1,
                "fields_filled": 1,
                "request_failures": 0,
            },
        )
        self.assertIn("FMP FILLED F", self.say.joined())


if __name__ == "__main__":
    unittest.main()
