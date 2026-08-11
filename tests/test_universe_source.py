"""Layer 0 universe enumeration from the CBOE options symbol directory.

The fixture is a trimmed slice of the real published file, kept verbatim: the
leading spaces in its header and the two dotted share-class symbols are the
actual quirks that broke naive parsing, and a hand-typed fixture would tidy them
away and stop testing anything.

No network. `download` is injected everywhere.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from wheel_mcp.universe_source import (
    MINIMUM_PLAUSIBLE_SYMBOLS,
    UniverseSourceError,
    apply_operator_overrides,
    cache_path,
    directory_url,
    fetch_constituents,
    load_universe,
    normalize_symbol_directory,
    read_cache,
    write_cache,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cboe_symbol_directory.csv"
RUN_DATE = date(2026, 8, 11)


def fixture_csv() -> str:
    return FIXTURE.read_text()


def plausible_csv() -> str:
    """The fixture padded past the sanity floor, for whole-path tests."""

    filler = "\n".join(
        f'"Filler Corp {index}","FILL{index}","Some DPM","1/1","-"'
        for index in range(MINIMUM_PLAUSIBLE_SYMBOLS)
    )
    return fixture_csv().rstrip("\n") + "\n" + filler + "\n"


class NormalizationTests(unittest.TestCase):
    def test_header_with_leading_spaces_is_matched(self) -> None:
        # The published header is "Company Name, Stock Symbol, ..." -- every
        # column but the first arrives with a leading space.
        self.assertTrue(fixture_csv().splitlines()[0].startswith("Company Name, Stock"))
        rows = normalize_symbol_directory(fixture_csv())
        self.assertEqual(len(rows), 11)

    def test_dotted_share_classes_become_yahoo_symbols(self) -> None:
        tickers = {row["ticker"] for row in normalize_symbol_directory(fixture_csv())}
        self.assertIn("BRK-B", tickers)
        self.assertIn("BF-B", tickers)
        self.assertNotIn("BRK.B", tickers)

    def test_company_name_is_carried(self) -> None:
        rows = {r["ticker"]: r["name"] for r in normalize_symbol_directory(fixture_csv())}
        self.assertEqual(rows["F"], "FORD MTR CO COM")

    def test_index_products_are_not_filtered_out(self) -> None:
        """AGENTS.md §4: Layer 0 enumerates, it does not judge.

        SPX and VIX are cash-settled index options that no Wheel position can
        use, but no column in the published file separates them from ETFs --
        SPY shares a Post/Station with several of them. Dropping them here would
        be interpretation at Layer 0. They cost one Stage 1 call each and land
        in the existing "no market cap" rejection line.
        """

        tickers = {row["ticker"] for row in normalize_symbol_directory(fixture_csv())}
        self.assertIn("SPX", tickers)
        self.assertIn("VIX", tickers)

    def test_duplicates_keep_their_first_occurrence(self) -> None:
        doubled = fixture_csv() + '"FORD MTR CO AGAIN","F","x","1/1","-"\n'
        rows = normalize_symbol_directory(doubled)
        self.assertEqual([r["ticker"] for r in rows].count("F"), 1)
        self.assertEqual(
            next(r["name"] for r in rows if r["ticker"] == "F"), "FORD MTR CO COM"
        )

    def test_missing_symbol_column_is_an_error_not_an_empty_universe(self) -> None:
        with self.assertRaises(UniverseSourceError):
            normalize_symbol_directory("Company Name, DPM Name\n" '"x","y"\n')

    def test_empty_input_is_an_error(self) -> None:
        with self.assertRaises(UniverseSourceError):
            normalize_symbol_directory("")


class OperatorOverrideTests(unittest.TestCase):
    def test_include_is_unioned_even_when_already_present(self) -> None:
        rows = apply_operator_overrides(
            normalize_symbol_directory(fixture_csv()), include=("SPY", "IWM")
        )
        tickers = [row["ticker"] for row in rows]
        self.assertEqual(tickers.count("SPY"), 1)
        self.assertIn("IWM", tickers)

    def test_exclude_wins_over_include(self) -> None:
        rows = apply_operator_overrides(
            normalize_symbol_directory(fixture_csv()),
            include=("SPY",),
            exclude=("SPY",),
        )
        self.assertNotIn("SPY", [row["ticker"] for row in rows])

    def test_output_is_sorted_by_ticker(self) -> None:
        rows = apply_operator_overrides(normalize_symbol_directory(fixture_csv()))
        tickers = [row["ticker"] for row in rows]
        self.assertEqual(tickers, sorted(tickers))


class SanityFloorTests(unittest.TestCase):
    def test_a_truncated_response_is_treated_as_a_failed_fetch(self) -> None:
        """A short file parses fine and would silently shrink the universe."""

        with self.assertRaises(UniverseSourceError) as caught:
            fetch_constituents(on=RUN_DATE, download=lambda _on: fixture_csv())
        self.assertIn("plausibility floor", str(caught.exception))

    def test_a_full_response_passes(self) -> None:
        rows = fetch_constituents(on=RUN_DATE, download=lambda _on: plausible_csv())
        self.assertGreaterEqual(len(rows), MINIMUM_PLAUSIBLE_SYMBOLS)


class LoadUniverseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.addCleanup(self._temporary.cleanup)
        self.downloads: list[date] = []

    def download(self, on: date) -> str:
        self.downloads.append(on)
        return plausible_csv()

    def test_first_run_fetches_and_caches(self) -> None:
        rows, staleness = load_universe(
            self.directory, on=RUN_DATE, download=self.download
        )
        self.assertIsNone(staleness)
        self.assertTrue(cache_path(self.directory, RUN_DATE).is_file())
        self.assertIn("SPY", {row["ticker"] for row in rows})

    def test_it_asks_for_yesterdays_file(self) -> None:
        """Today's file may still be mid-publication; yesterday's is final."""

        load_universe(self.directory, on=RUN_DATE, download=self.download)
        self.assertEqual(self.downloads, [date(2026, 8, 10)])

    def test_same_day_rerun_uses_the_cache_without_fetching(self) -> None:
        load_universe(self.directory, on=RUN_DATE, download=self.download)
        load_universe(self.directory, on=RUN_DATE, download=self.download)
        self.assertEqual(len(self.downloads), 1)

    def test_overrides_apply_to_a_cache_hit_without_a_refetch(self) -> None:
        """Editing universe.include must take effect on the next run."""

        load_universe(self.directory, on=RUN_DATE, download=self.download)
        rows, _ = load_universe(
            self.directory,
            on=RUN_DATE,
            include=("NEWNAME",),
            exclude=("SPY",),
            download=self.download,
        )
        tickers = {row["ticker"] for row in rows}
        self.assertIn("NEWNAME", tickers)
        self.assertNotIn("SPY", tickers)
        self.assertEqual(len(self.downloads), 1)

    def test_fetch_failure_reuses_the_newest_cache_and_says_so(self) -> None:
        write_cache(self.directory, [{"ticker": "OLD", "name": None}], date(2026, 7, 1))

        def failing(_on: date) -> str:
            raise RuntimeError("CBOE is down")

        rows, staleness = load_universe(
            self.directory, on=RUN_DATE, download=failing
        )
        self.assertEqual([row["ticker"] for row in rows], ["OLD"])
        self.assertIsNotNone(staleness)
        self.assertIn("STALE UNIVERSE", staleness)
        self.assertIn("CBOE is down", staleness)

    def test_fetch_failure_with_no_cache_raises_rather_than_screening_nothing(
        self,
    ) -> None:
        def failing(_on: date) -> str:
            raise RuntimeError("CBOE is down")

        with self.assertRaises(UniverseSourceError):
            load_universe(self.directory, on=RUN_DATE, download=failing)

    def test_a_truncated_fetch_falls_through_to_the_cache(self) -> None:
        write_cache(self.directory, [{"ticker": "OLD", "name": None}], date(2026, 7, 1))
        rows, staleness = load_universe(
            self.directory, on=RUN_DATE, download=lambda _on: fixture_csv()
        )
        self.assertEqual([row["ticker"] for row in rows], ["OLD"])
        self.assertIn("plausibility floor", staleness)

    def test_cache_round_trips(self) -> None:
        path = write_cache(
            self.directory, [{"ticker": "AAPL", "name": "APPLE INC COM"}], RUN_DATE
        )
        self.assertEqual(read_cache(path), [{"ticker": "AAPL", "name": "APPLE INC COM"}])
        payload = json.loads(path.read_text())
        self.assertEqual(payload["source"], "cboe_equity_options")

    def test_a_cache_without_a_constituents_array_is_an_error(self) -> None:
        path = cache_path(self.directory, RUN_DATE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"count": 0}')
        with self.assertRaises(UniverseSourceError):
            read_cache(path)


class UrlTests(unittest.TestCase):
    def test_the_date_is_in_the_query_string(self) -> None:
        self.assertEqual(
            directory_url(date(2026, 8, 10)),
            "https://www.cboe.com/us/options/symboldir/equity-index-options"
            "/download/?dt=2026-08-10",
        )


if __name__ == "__main__":
    unittest.main()
