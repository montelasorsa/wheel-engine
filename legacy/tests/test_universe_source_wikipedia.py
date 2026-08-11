"""Quarantined: tests for the superseded Wikipedia S&P constituent scraper.

`legacy/universe_source_wikipedia.py` enumerated the universe from index
membership. It was replaced on 2026-08-11 by the CBOE options symbol directory,
which answers the question that actually matters -- what has listed options --
rather than a correlate of it. These tests move with the code they cover; the
live equivalents are `tests/test_universe_source.py`.

Not collected by the main suite (`tests/` only). Kept, not deleted, so the
superseded path stays readable next to its replacement.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date

import pandas as pd

from universe_source_wikipedia import (
    UniverseSourceError,
    fetch_constituents,
    load_universe,
    merge_constituents,
    newest_cache,
    normalize_constituent_table,
    read_cache,
    write_cache,
)


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
