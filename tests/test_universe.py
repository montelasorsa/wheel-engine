"""Offline tests for universe enumeration and Stage 1 filtering.

`wheel.universe` is pure, so its tests take mock rows directly.
`wheel_mcp.universe_source` is exercised with an injected `read_html`, so no
network is touched and no Wikipedia change can break the suite.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from wheel.universe import (
    Stage1Survivor,
    UniverseFilters,
    filter_stage1,
    normalize_symbols,
    same_iso_week,
    should_reuse_snapshot,
    universe_filters_from_config,
)
from wheel_mcp.universe_source import (
    UniverseSourceError,
    fetch_constituents,
    load_universe,
    merge_constituents,
    newest_cache,
    normalize_constituent_table,
    read_cache,
    write_cache,
)

# Plain floors: no forced includes, so a result contains exactly what the
# rows justify. The include/exclude behavior gets its own fixture below.
FILTERS = UniverseFilters(
    price_floor=10.0,
    market_cap_floor=2_000_000_000.0,
    exclude=("BADCO",),
)
FORCED = UniverseFilters(
    price_floor=10.0,
    market_cap_floor=2_000_000_000.0,
    include=("SPY",),
    exclude=("BADCO",),
)


def row(ticker, price=50.0, market_cap=5e9, sector="Industrials"):
    return {
        "ticker": ticker,
        "price": price,
        "market_cap": market_cap,
        "sector": sector,
    }


class ConfigTests(unittest.TestCase):
    def test_filters_load_from_the_universe_block(self) -> None:
        config = {
            "universe": {
                "source": "us_equities_with_options",
                "price_floor": 10,
                "market_cap_floor": 2_000_000_000,
                "include": ["SPY", "QQQ"],
                "exclude": [],
            }
        }
        filters = universe_filters_from_config(config)
        self.assertEqual(filters.price_floor, 10.0)
        self.assertEqual(filters.market_cap_floor, 2e9)
        self.assertEqual(filters.include, ("SPY", "QQQ"))
        self.assertEqual(filters.exclude, ())

    def test_symbols_are_uppercased_and_deduplicated(self) -> None:
        self.assertEqual(normalize_symbols([" spy ", "QQQ", "spy", ""]), ("SPY", "QQQ"))


class Stage1FilterTests(unittest.TestCase):
    def test_clean_row_survives(self) -> None:
        result = filter_stage1([row("AAPL")], FILTERS)
        self.assertEqual([s.ticker for s in result.survivors], ["AAPL"])
        self.assertEqual(result.rejected_count, 0)

    def test_price_below_floor_is_rejected(self) -> None:
        result = filter_stage1([row("PENNY", price=4.20)], FILTERS)
        self.assertEqual(result.survivors, ())
        self.assertIn("PENNY", result.rejected["price below floor (ST-SEL-04)"])

    def test_price_exactly_at_floor_survives(self) -> None:
        result = filter_stage1([row("EDGE", price=10.0)], FILTERS)
        self.assertEqual([s.ticker for s in result.survivors], ["EDGE"])

    def test_market_cap_below_floor_is_rejected(self) -> None:
        result = filter_stage1([row("SMALL", market_cap=1.5e9)], FILTERS)
        self.assertIn("SMALL", result.rejected["market cap below floor (AL-SEL-06)"])

    def test_price_and_market_cap_are_independent_filters(self) -> None:
        """AL-SEL-06's whole point: a sound $15 large-cap must survive."""

        result = filter_stage1(
            [row("BIGCHEAP", price=15.0, market_cap=8e10)], FILTERS
        )
        self.assertEqual([s.ticker for s in result.survivors], ["BIGCHEAP"])

    def test_missing_data_is_rejected_not_passed(self) -> None:
        result = filter_stage1(
            [row("NOPRICE", price=None), row("NOCAP", market_cap=None)], FILTERS
        )
        self.assertEqual(result.survivors, ())
        self.assertIn("NOPRICE", result.rejected["no price"])
        self.assertIn("NOCAP", result.rejected["no market cap"])

    def test_exclude_wins_over_everything(self) -> None:
        result = filter_stage1([row("BADCO")], FILTERS)
        self.assertEqual(result.survivors, ())
        self.assertIn("BADCO", result.rejected["excluded by config"])

    def test_include_bypasses_the_floors(self) -> None:
        # SPY is $769 and has no issuer market cap; it must survive anyway.
        result = filter_stage1([row("SPY", price=769.0, market_cap=None)], FORCED)
        self.assertEqual([s.ticker for s in result.survivors], ["SPY"])
        self.assertTrue(result.survivors[0].forced)

    def test_include_name_absent_from_the_scan_is_still_carried(self) -> None:
        result = filter_stage1([row("AAPL")], FORCED)
        self.assertEqual(sorted(s.ticker for s in result.survivors), ["AAPL", "SPY"])

    def test_exclude_beats_include(self) -> None:
        filters = UniverseFilters(10.0, 2e9, include=("BADCO",), exclude=("BADCO",))
        self.assertEqual(filter_stage1([row("BADCO")], filters).survivors, ())

    def test_duplicates_are_collapsed(self) -> None:
        result = filter_stage1([row("AAPL"), row("AAPL")], FILTERS)
        self.assertEqual(len(result.survivors), 1)

    def test_survivors_carry_stage1_measurements(self) -> None:
        survivor = filter_stage1([row("KO", price=86.85, market_cap=3.7e11,
                                      sector="Consumer Defensive")], FILTERS).survivors[0]
        self.assertEqual(survivor.price, 86.85)
        self.assertEqual(survivor.sector, "Consumer Defensive")

    def test_survivors_are_sorted_for_a_stable_run_order(self) -> None:
        result = filter_stage1([row("ZTS"), row("AAPL"), row("MMM")], FORCED)
        self.assertEqual(
            [s.ticker for s in result.survivors], ["AAPL", "MMM", "SPY", "ZTS"]
        )

    def test_scale_shape(self) -> None:
        rows = [row(f"T{i:04d}", price=5.0 if i % 2 else 50.0) for i in range(1000)]
        result = filter_stage1(rows, FORCED)
        self.assertEqual(len(result.survivors), 501)  # 500 + forced SPY
        self.assertEqual(
            len(result.rejected["price below floor (ST-SEL-04)"]), 500
        )


class SnapshotReuseTests(unittest.TestCase):
    SNAPSHOT = {"snapshot_date": "2026-08-10", "price": {"current": 100.0}}

    def test_same_week_and_stable_price_reuses(self) -> None:
        self.assertTrue(
            should_reuse_snapshot(
                self.SNAPSHOT, run_date="2026-08-12", stage1_price=103.0
            )
        )

    def test_price_moved_more_than_five_percent_refetches(self) -> None:
        self.assertFalse(
            should_reuse_snapshot(
                self.SNAPSHOT, run_date="2026-08-12", stage1_price=106.0
            )
        )

    def test_exactly_five_percent_still_reuses(self) -> None:
        self.assertTrue(
            should_reuse_snapshot(
                self.SNAPSHOT, run_date="2026-08-12", stage1_price=105.0
            )
        )

    def test_different_week_always_refetches(self) -> None:
        self.assertFalse(
            should_reuse_snapshot(
                self.SNAPSHOT, run_date="2026-08-19", stage1_price=100.0
            )
        )

    def test_missing_snapshot_or_price_refetches(self) -> None:
        self.assertFalse(
            should_reuse_snapshot(None, run_date="2026-08-12", stage1_price=100.0)
        )
        self.assertFalse(
            should_reuse_snapshot(
                self.SNAPSHOT, run_date="2026-08-12", stage1_price=None
            )
        )

    def test_iso_week_boundary(self) -> None:
        # Sunday 2026-08-16 and Monday 2026-08-17 are different ISO weeks.
        self.assertFalse(same_iso_week("2026-08-16", "2026-08-17"))
        self.assertTrue(same_iso_week("2026-08-10", "2026-08-16"))


SP500_TABLE = pd.DataFrame(
    {
        "Symbol": ["AAPL", "BRK.B", "KO"],
        "Security": ["Apple Inc.", "Berkshire Hathaway", "Coca-Cola"],
        "GICS Sector": ["Information Technology", "Financials", "Consumer Staples"],
    }
)
UNRELATED_TABLE = pd.DataFrame({"Date": ["2026-01-01"], "Added": ["X"]})


class ConstituentSourceTests(unittest.TestCase):
    def test_normalizes_share_class_separator_for_yahoo(self) -> None:
        rows = normalize_constituent_table(
            SP500_TABLE,
            index_name="sp500",
            ticker_columns=("Symbol",),
            name_columns=("Security",),
            sector_columns=("GICS Sector",),
        )
        self.assertEqual([r["ticker"] for r in rows], ["AAPL", "BRK-B", "KO"])
        self.assertEqual(rows[0]["sector"], "Information Technology")
        self.assertEqual(rows[0]["index"], "sp500")

    def test_missing_ticker_column_raises(self) -> None:
        with self.assertRaises(UniverseSourceError):
            normalize_constituent_table(
                UNRELATED_TABLE, index_name="sp500", ticker_columns=("Symbol",)
            )

    def test_merge_unions_and_dedupes_across_indices(self) -> None:
        merged = merge_constituents(
            [
                [{"ticker": "KO", "index": "sp500"}],
                [{"ticker": "KO", "index": "sp400"}, {"ticker": "AAL", "index": "sp400"}],
            ]
        )
        self.assertEqual([r["ticker"] for r in merged], ["AAL", "KO"])
        self.assertEqual(merged[1]["index"], "sp500")  # first wins

    def test_fetch_skips_unrelated_tables_on_the_page(self) -> None:
        rows = fetch_constituents(
            read_html=lambda url: [UNRELATED_TABLE, SP500_TABLE],
            sources=({"index": "sp500", "url": "x", "ticker_columns": ("Symbol",),
                      "name_columns": ("Security",), "sector_columns": ("GICS Sector",)},),
        )
        self.assertEqual(len(rows), 3)

    def test_fetch_raises_when_every_source_fails(self) -> None:
        def boom(url):
            raise RuntimeError("403")

        with self.assertRaises(UniverseSourceError):
            fetch_constituents(
                read_html=boom,
                sources=({"index": "sp500", "url": "x", "ticker_columns": ("Symbol",)},),
            )


class CacheTests(unittest.TestCase):
    SOURCES = (
        {"index": "sp500", "url": "x", "ticker_columns": ("Symbol",),
         "name_columns": ("Security",), "sector_columns": ("GICS Sector",)},
    )

    def test_successful_fetch_writes_a_cache_and_no_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rows, warning = load_universe(
                directory,
                on=date(2026, 8, 11),
                read_html=lambda url: [SP500_TABLE],
                sources=self.SOURCES,
            )
            self.assertEqual(len(rows), 3)
            self.assertIsNone(warning)
            cached = newest_cache(directory)
            self.assertEqual(cached.name, "constituents-2026-08-11.json")
            self.assertEqual(len(read_cache(cached)), 3)

    def test_failed_fetch_reuses_the_newest_cache_and_warns_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            write_cache(directory, [{"ticker": "KO"}], date(2026, 8, 4))

            def boom(url):
                raise RuntimeError("Wikipedia changed")

            rows, warning = load_universe(
                directory,
                on=date(2026, 8, 11),
                read_html=boom,
                sources=self.SOURCES,
            )
            self.assertEqual([r["ticker"] for r in rows], ["KO"])
            self.assertIn("STALE UNIVERSE", warning)
            self.assertIn("constituents-2026-08-04.json", warning)

    def test_failed_fetch_with_no_cache_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            def boom(url):
                raise RuntimeError("no network")

            with self.assertRaises(UniverseSourceError):
                load_universe(
                    directory, on=date(2026, 8, 11), read_html=boom, sources=self.SOURCES
                )

    def test_newest_cache_wins_by_iso_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            write_cache(directory, [{"ticker": "A"}], date(2026, 7, 28))
            write_cache(directory, [{"ticker": "B"}], date(2026, 8, 4))
            self.assertEqual(newest_cache(directory).name, "constituents-2026-08-04.json")


if __name__ == "__main__":
    unittest.main()
