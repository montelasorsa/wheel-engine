"""Layer 0 enrichment: the fetch loop, its failure mode, and the sidecar edge.

No network. The provider call is a stub throughout -- what is under test is
that the right names are asked for, that a failure costs exactly one name, and
that the step never takes the pipeline down with it.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from wheel.enrich import enrichment_dir, read_enrichment, read_enrichment_set
from wheel.monitored import SIDECAR_SUFFIX
from wheel_mcp.enrich_fetch import enrich_tickers, latest_sidecar, run_enrichment

RUN_DATE = date(2026, 9, 6)

INFO = {
    "AAA": {"longName": "Alpha Corp", "sector": "Technology", "trailingPE": 21.0},
    "BBB": {"longName": "Beta Inc", "sector": "Healthcare", "dividendRate": 1.2},
    "CCC": {"longName": "Gamma Ltd", "sector": "Industrials"},
}


class Say:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        self.lines.append(message)

    def joined(self) -> str:
        return "\n".join(self.lines)


class Stub:
    """A stand-in for `yahoo.fetch_ticker_info`, recording what it was asked."""

    def __init__(self, *, failing: set[str] | None = None) -> None:
        self.asked: list[str] = []
        self.keywords: list[dict] = []
        self.failing = failing or set()

    def __call__(self, ticker: str, **keywords):
        self.asked.append(ticker)
        self.keywords.append(keywords)
        if ticker in self.failing:
            raise RuntimeError("429 Too Many Requests")
        return INFO.get(ticker, {})


def write_sidecar(weeks: Path, stamp: str, entries: dict) -> Path:
    weeks.mkdir(parents=True, exist_ok=True)
    path = weeks / f"{stamp}{SIDECAR_SUFFIX}"
    path.write_text(
        json.dumps({"run_date": stamp, "entries": entries}), encoding="utf-8"
    )
    return path


def config_for(wheelops: Path, **enrichment) -> dict:
    return {
        "paths": {"wheelops": str(wheelops)},
        "data_sources": {
            "yfinance": {
                "min_request_interval_seconds": 0.0,
                "max_attempts": 1,
                "initial_backoff_seconds": 0.0,
                "backoff_multiplier": 1.0,
            }
        },
        "enrichment": enrichment,
    }


class FetchLoopTests(unittest.TestCase):
    def test_one_record_per_ticker_lands_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stub = Stub()
            result = enrich_tickers(
                ["AAA", "BBB"],
                wheelops=Path(temporary),
                run_date=RUN_DATE,
                fetch_info=stub,
                say=Say(),
            )
            self.assertEqual(stub.asked, ["AAA", "BBB"])
            self.assertEqual(result["written"], ["AAA", "BBB"])
            self.assertEqual(result["errors"], [])
            records = read_enrichment_set(temporary, RUN_DATE)
            self.assertEqual(sorted(records), ["AAA", "BBB"])
            self.assertEqual(records["AAA"]["business"]["long_name"], "Alpha Corp")
            self.assertEqual(records["AAA"]["fetched_on"], "2026-09-06")

    def test_the_shared_throttle_is_passed_to_every_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stub = Stub()
            enrich_tickers(
                ["AAA"],
                wheelops=Path(temporary),
                run_date=RUN_DATE,
                fetch_info=stub,
                say=Say(),
            )
            self.assertIn("throttle", stub.keywords[0])

    def test_a_provider_failure_costs_one_name_and_writes_a_null_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            say = Say()
            stub = Stub(failing={"BBB"})
            result = enrich_tickers(
                ["AAA", "BBB", "CCC"],
                wheelops=Path(temporary),
                run_date=RUN_DATE,
                fetch_info=stub,
                say=say,
            )
            self.assertEqual(stub.asked, ["AAA", "BBB", "CCC"])
            self.assertEqual(result["written"], ["AAA", "BBB", "CCC"])
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["errors"][0][0], "BBB")
            self.assertIn("429", result["errors"][0][1])

            failed = read_enrichment(temporary, RUN_DATE, "BBB")
            self.assertIsNotNone(failed)
            self.assertIsNone(failed["business"]["long_name"])
            # The names on either side are untouched.
            self.assertEqual(
                read_enrichment(temporary, RUN_DATE, "CCC")["business"]["long_name"],
                "Gamma Ltd",
            )

    def test_an_empty_target_list_writes_nothing_and_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = enrich_tickers(
                [],
                wheelops=Path(temporary),
                run_date=RUN_DATE,
                fetch_info=Stub(),
                say=Say(),
            )
            self.assertEqual(result["written"], [])
            self.assertFalse(enrichment_dir(temporary, RUN_DATE).exists())


class SidecarResolutionTests(unittest.TestCase):
    def test_the_newest_sidecar_wins_when_no_date_is_given(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            weeks = Path(temporary) / "weeks"
            write_sidecar(weeks, "2026-08-30", {})
            write_sidecar(weeks, "2026-09-06", {})
            self.assertEqual(latest_sidecar(weeks).name, f"2026-09-06{SIDECAR_SUFFIX}")

    def test_an_explicit_date_is_honoured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            weeks = Path(temporary) / "weeks"
            write_sidecar(weeks, "2026-08-30", {})
            write_sidecar(weeks, "2026-09-06", {})
            self.assertEqual(
                latest_sidecar(weeks, "2026-08-30").name,
                f"2026-08-30{SIDECAR_SUFFIX}",
            )

    def test_a_missing_sidecar_raises_rather_than_enriching_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            weeks = Path(temporary) / "weeks"
            weeks.mkdir()
            with self.assertRaises(FileNotFoundError):
                latest_sidecar(weeks)
            with self.assertRaises(FileNotFoundError):
                latest_sidecar(weeks, "2026-09-06")


class RunEnrichmentTests(unittest.TestCase):
    def test_it_enriches_the_top_n_by_score(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = Path(temporary)
            write_sidecar(
                wheelops / "weeks",
                "2026-09-06",
                {
                    "AAA": {"score": 71.0, "zone": "Zone 1"},
                    "BBB": {"score": 88.5, "zone": "Zone 2"},
                    "CCC": {"score": 64.0, "zone": "Zone 1"},
                },
            )
            stub = Stub()
            result = run_enrichment(
                config_for(wheelops, top_n=2, include_locked_zones=True),
                fetch_info=stub,
                say=Say(),
            )
            self.assertEqual(stub.asked, ["BBB", "AAA"])
            self.assertEqual(result["run_date"], "2026-09-06")
            self.assertEqual(sorted(read_enrichment_set(wheelops, "2026-09-06")), ["AAA", "BBB"])

    def test_locked_zones_can_be_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = Path(temporary)
            write_sidecar(
                wheelops / "weeks",
                "2026-09-06",
                {
                    "AAA": {"score": 71.0, "zone": "Zone 1"},
                    "BBB": {"score": 88.5, "zone": "Zone 2"},
                },
            )
            stub = Stub()
            run_enrichment(
                config_for(wheelops, top_n=50, include_locked_zones=False),
                fetch_info=stub,
                say=Say(),
            )
            self.assertEqual(stub.asked, ["AAA"])

    def test_the_run_date_comes_from_the_sidecar_not_today(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = Path(temporary)
            write_sidecar(
                wheelops / "weeks", "2026-08-30", {"AAA": {"score": 70.0, "zone": "Zone 1"}}
            )
            run_enrichment(config_for(wheelops, top_n=5), fetch_info=Stub(), say=Say())
            self.assertTrue(enrichment_dir(wheelops, "2026-08-30").is_dir())

    def test_an_empty_monitored_tier_is_a_legitimate_week(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = Path(temporary)
            write_sidecar(wheelops / "weeks", "2026-09-06", {})
            say = Say()
            result = run_enrichment(
                config_for(wheelops, top_n=50), fetch_info=Stub(), say=say
            )
            self.assertEqual(result["written"], [])
            self.assertIn("targets=0", say.joined())

    def test_an_unreadable_sidecar_raises_with_the_path_named(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheelops = Path(temporary)
            weeks = wheelops / "weeks"
            weeks.mkdir(parents=True)
            (weeks / f"2026-09-06{SIDECAR_SUFFIX}").write_text("{not json")
            with self.assertRaises(RuntimeError) as raised:
                run_enrichment(config_for(wheelops), fetch_info=Stub(), say=Say())
            self.assertIn("2026-09-06", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
