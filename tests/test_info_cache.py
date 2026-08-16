"""The Stage 1 cache: 5,300 provider calls, or none.

Stage 1 costs one `info` call per universe name -- roughly forty minutes across
the CBOE directory -- to ask three questions whose answers do not change inside
a week. These tests hold the two halves apart: `wheel.universe.is_info_fresh`
decides (pure), `wheel_mcp.info_cache` stores (files only), and `scan_universe`
must make **zero** calls on a hit. That last one is the whole point, so it is
asserted by counting calls on the injected fetcher rather than by timing.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from wheel.universe import (
    INFO_CACHE_MAX_AGE_DAYS,
    UniverseFilters,
    filter_stage1,
    is_info_fresh,
    should_reuse_snapshot,
)
from wheel_mcp.acquire import scan_universe
from wheel_mcp.info_cache import (
    cache_path,
    entry_from_row,
    iso_week_label,
    prune,
    read_info_cache,
    row_from_entry,
    write_info_cache,
)
from wheel_mcp.yahoo import YFinanceFetchPolicy

RUN_DATE = date(2026, 8, 12)  # a Wednesday, ISO week 2026-W33
POLICY = YFinanceFetchPolicy(
    min_request_interval_seconds=0.0,
    max_attempts=3,
    initial_backoff_seconds=0.0,
    backoff_multiplier=1.0,
)


def entry(fetched_on: str, price: float = 50.0, market_cap: float = 5e9) -> dict:
    """A complete cache row. Must carry every CACHE_FIELDS key or it is a miss."""

    return {
        "price": price,
        "market_cap": market_cap,
        "sector": "Industrials",
        "quote_type": "EQUITY",
        "name": "Example Corporation",
        "dividend_yield": 1.8,
        "fetched_on": fetched_on,
    }


class Fetcher:
    """A stand-in for yfinance that counts how often it was actually asked."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, ticker, *, policy, throttle):
        self.calls.append(ticker)
        return {
            "regularMarketPrice": 42.0,
            "marketCap": 9e9,
            "sector": "Technology",
            "quoteType": "EQUITY",
            "longName": "Example Technology Corporation",
        }


class FailingFetcher(Fetcher):
    """A provider that refuses every request, as a rate-limited one does."""

    def __call__(self, ticker, *, policy, throttle):
        self.calls.append(ticker)
        raise RuntimeError("Too Many Requests. Rate limited.")


class Sleeper:
    """Records pacing without spending any wall-clock time."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def quiet(_message: str) -> None:
    return None


class FreshnessTests(unittest.TestCase):
    def test_today_is_fresh(self) -> None:
        self.assertTrue(is_info_fresh(entry("2026-08-12"), on="2026-08-12"))

    def test_six_days_old_is_still_fresh(self) -> None:
        self.assertTrue(is_info_fresh(entry("2026-08-06"), on="2026-08-12"))

    def test_seven_days_old_has_expired(self) -> None:
        self.assertFalse(is_info_fresh(entry("2026-08-05"), on="2026-08-12"))
        self.assertEqual(INFO_CACHE_MAX_AGE_DAYS, 7)

    def test_a_future_stamp_is_refused_rather_than_trusted(self) -> None:
        """A clock skew must not grant a cache entry indefinite life."""

        self.assertFalse(is_info_fresh(entry("2026-09-01"), on="2026-08-12"))

    def test_undateable_entries_fail_closed(self) -> None:
        for bad in (None, {}, {"fetched_on": None}, {"fetched_on": "not-a-date"}):
            self.assertFalse(is_info_fresh(bad, on="2026-08-12"))


class CacheFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.addCleanup(self._temporary.cleanup)

    def test_files_are_named_by_iso_week(self) -> None:
        self.assertEqual(iso_week_label(RUN_DATE), "2026-W33")
        self.assertEqual(
            cache_path(self.directory, RUN_DATE).name, "ticker_info_2026-W33.json"
        )

    def test_round_trip(self) -> None:
        write_info_cache(self.directory, {"AAPL": entry("2026-08-12")}, RUN_DATE)
        self.assertEqual(
            read_info_cache(self.directory, RUN_DATE)["AAPL"]["market_cap"], 5e9
        )

    def test_the_previous_week_is_read_too(self) -> None:
        """Seven days is not one calendar week.

        A Monday run is three days from the previous Friday's fetch, and that
        entry lives in last week's file. Reading only the current week would
        silently refetch everything every Monday.
        """

        write_info_cache(
            self.directory, {"OLD": entry("2026-08-07")}, date(2026, 8, 7)
        )
        merged = read_info_cache(self.directory, RUN_DATE)
        self.assertIn("OLD", merged)

    def test_the_current_week_wins_on_conflict(self) -> None:
        write_info_cache(
            self.directory, {"X": entry("2026-08-07", price=10.0)}, date(2026, 8, 7)
        )
        write_info_cache(
            self.directory, {"X": entry("2026-08-12", price=99.0)}, RUN_DATE
        )
        self.assertEqual(read_info_cache(self.directory, RUN_DATE)["X"]["price"], 99.0)

    def test_writing_merges_rather_than_replacing(self) -> None:
        """An interrupted run must add to the cache, not discard it."""

        write_info_cache(self.directory, {"A": entry("2026-08-12")}, RUN_DATE)
        write_info_cache(self.directory, {"B": entry("2026-08-12")}, RUN_DATE)
        entries = read_info_cache(self.directory, RUN_DATE)
        self.assertEqual(sorted(entries), ["A", "B"])

    def test_a_corrupt_cache_reads_as_empty_rather_than_raising(self) -> None:
        path = cache_path(self.directory, RUN_DATE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not json")
        self.assertEqual(read_info_cache(self.directory, RUN_DATE), {})

    def test_missing_directory_reads_as_empty(self) -> None:
        self.assertEqual(read_info_cache(self.directory / "nope", RUN_DATE), {})

    def test_prune_drops_names_that_left_the_universe(self) -> None:
        entries = {"KEEP": entry("2026-08-12"), "GONE": entry("2026-08-12")}
        self.assertEqual(list(prune(entries, ["KEEP"])), ["KEEP"])

    def test_entry_and_row_round_trip_with_the_cached_marker(self) -> None:
        row = {"ticker": "F", "price": 13.79, "market_cap": 5e10, "sector": "X"}
        restored = row_from_entry("F", entry_from_row(row, RUN_DATE))
        self.assertEqual(restored["price"], 13.79)
        self.assertEqual(restored["sector"], "X")
        self.assertTrue(restored["price_is_cached"])


class ScanCacheTests(unittest.TestCase):
    def test_a_cache_hit_makes_no_provider_call(self) -> None:
        fetcher = Fetcher()
        rows, fetched = scan_universe(
            ["AAPL"],
            policy=POLICY,
            fetch_info=fetcher,
            say=quiet,
            cached={"AAPL": entry("2026-08-12", price=50.0)},
            on=RUN_DATE,
        )
        self.assertEqual(fetcher.calls, [])
        self.assertEqual(fetched, {})
        self.assertEqual(rows[0]["price"], 50.0)
        self.assertTrue(rows[0]["price_is_cached"])

    def test_an_expired_entry_is_refetched(self) -> None:
        fetcher = Fetcher()
        rows, fetched = scan_universe(
            ["AAPL"],
            policy=POLICY,
            fetch_info=fetcher,
            say=quiet,
            cached={"AAPL": entry("2026-08-01")},
            on=RUN_DATE,
        )
        self.assertEqual(fetcher.calls, ["AAPL"])
        self.assertEqual(rows[0]["price"], 42.0)
        self.assertNotIn("price_is_cached", rows[0])
        self.assertEqual(fetched["AAPL"]["fetched_on"], "2026-08-12")

    def test_legacy_entry_without_etf_metadata_is_refetched(self) -> None:
        fetcher = Fetcher()
        legacy = {
            "price": 50.0,
            "market_cap": 5e9,
            "sector": "Industrials",
            "fetched_on": "2026-08-12",
        }
        rows, fetched = scan_universe(
            ["AAPL"],
            policy=POLICY,
            fetch_info=fetcher,
            say=quiet,
            cached={"AAPL": legacy},
            on=RUN_DATE,
        )
        self.assertEqual(fetcher.calls, ["AAPL"])
        self.assertEqual(rows[0]["quote_type"], "EQUITY")
        self.assertEqual(fetched["AAPL"]["name"], "Example Technology Corporation")

    def test_a_ticker_absent_from_the_cache_is_fetched(self) -> None:
        fetcher = Fetcher()
        _rows, fetched = scan_universe(
            ["NEW"],
            policy=POLICY,
            fetch_info=fetcher,
            say=quiet,
            cached={"AAPL": entry("2026-08-12")},
            on=RUN_DATE,
        )
        self.assertEqual(fetcher.calls, ["NEW"])
        self.assertIn("NEW", fetched)

    def test_a_mixed_universe_only_pays_for_the_misses(self) -> None:
        fetcher = Fetcher()
        rows, fetched = scan_universe(
            ["HIT", "MISS", "STALE"],
            policy=POLICY,
            fetch_info=fetcher,
            say=quiet,
            cached={
                "HIT": entry("2026-08-12"),
                "STALE": entry("2026-07-01"),
            },
            on=RUN_DATE,
        )
        self.assertEqual(sorted(fetcher.calls), ["MISS", "STALE"])
        self.assertEqual(sorted(fetched), ["MISS", "STALE"])
        self.assertEqual(len(rows), 3)

    def test_each_fetch_is_paced_by_the_configured_delay(self) -> None:
        sleeper = Sleeper()
        scan_universe(
            ["A", "B", "C"],
            policy=POLICY,
            fetch_info=Fetcher(),
            say=quiet,
            on=RUN_DATE,
            fetch_delay_seconds=0.75,
            sleeper=sleeper,
        )
        self.assertEqual(sleeper.waits, [0.75, 0.75, 0.75])

    def test_cache_hits_are_not_paced(self) -> None:
        """Pacing a request that was never made would add an hour for nothing."""

        sleeper = Sleeper()
        scan_universe(
            ["HIT", "MISS"],
            policy=POLICY,
            fetch_info=Fetcher(),
            say=quiet,
            cached={"HIT": entry("2026-08-12")},
            on=RUN_DATE,
            fetch_delay_seconds=0.75,
            sleeper=sleeper,
        )
        self.assertEqual(sleeper.waits, [0.75])

    def test_refused_requests_are_paced_too(self) -> None:
        """A rate-limited run is all failures; unpaced retries dig deeper in."""

        sleeper = Sleeper()
        scan_universe(
            ["A", "B"],
            policy=POLICY,
            fetch_info=FailingFetcher(),
            say=quiet,
            on=RUN_DATE,
            fetch_delay_seconds=0.75,
            sleeper=sleeper,
        )
        self.assertEqual(sleeper.waits, [0.75, 0.75])

    def test_no_delay_configured_means_no_sleeping(self) -> None:
        sleeper = Sleeper()
        scan_universe(
            ["A"],
            policy=POLICY,
            fetch_info=Fetcher(),
            say=quiet,
            on=RUN_DATE,
            sleeper=sleeper,
        )
        self.assertEqual(sleeper.waits, [])

    def test_a_failed_lookup_is_not_cached(self) -> None:
        """Caching a delisting would hide it from the universe for a week."""

        def boom(ticker, *, policy, throttle):
            raise RuntimeError("delisted")

        rows, fetched = scan_universe(
            ["DEAD"], policy=POLICY, fetch_info=boom, say=quiet, on=RUN_DATE
        )
        self.assertEqual(fetched, {})
        self.assertIsNone(rows[0]["price"])


class CachedPriceReuseTests(unittest.TestCase):
    """The trap the cache would otherwise set for Stage 2.

    A cached Stage 1 price is by construction close to the price in a same-week
    snapshot -- they can be the same original quote -- so the 5% tolerance test
    would pass every time and every snapshot would be reused forever. The cache
    would read as a speedup while quietly freezing the screen.
    """

    SNAPSHOT = {"snapshot_date": "2026-08-10", "price": {"current": 100.0}}

    def test_a_fresh_price_still_drives_the_tolerance_test(self) -> None:
        self.assertTrue(
            should_reuse_snapshot(
                self.SNAPSHOT, run_date="2026-08-12", stage1_price=101.0
            )
        )

    def test_a_cached_price_refuses_to_authorize_reuse(self) -> None:
        self.assertFalse(
            should_reuse_snapshot(
                self.SNAPSHOT,
                run_date="2026-08-12",
                stage1_price=101.0,
                stage1_price_is_cached=True,
            )
        )

    def test_the_marker_survives_stage_1_filtering(self) -> None:
        result = filter_stage1(
            [
                {"ticker": "C", "price": 50.0, "market_cap": 5e9, "price_is_cached": True},
                {"ticker": "F", "price": 50.0, "market_cap": 5e9},
            ],
            UniverseFilters(price_floor=10.0, market_cap_floor=2e9),
        )
        by_ticker = {s.ticker: s for s in result.survivors}
        self.assertTrue(by_ticker["C"].price_is_cached)
        self.assertFalse(by_ticker["F"].price_is_cached)

    def test_it_survives_the_include_bypass_too(self) -> None:
        result = filter_stage1(
            [{"ticker": "SPY", "price": 700.0, "market_cap": None,
              "price_is_cached": True}],
            UniverseFilters(price_floor=10.0, market_cap_floor=2e9, include=("SPY",)),
        )
        self.assertTrue(result.survivors[0].price_is_cached)


if __name__ == "__main__":
    unittest.main()
