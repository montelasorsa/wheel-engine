"""Offline tests for Stage 1 filtering and the Stage 2 reuse decision.

`wheel.universe` is pure, so its tests take mock rows directly -- no network, no
provider, no fixtures. Enumeration itself is Layer 0 and is tested in
`tests/test_universe_source.py`.
"""

from __future__ import annotations

import unittest

from wheel.universe import (
    DEFAULT_ETF_EXCLUDE_PATTERNS,
    ETF_YIELD_CEILING,
    Stage1Survivor,
    UniverseFilters,
    filter_stage1,
    normalize_symbols,
    same_iso_week,
    should_reuse_snapshot,
    universe_filters_from_config,
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
        self.assertEqual(filters.etf_exclude_patterns, DEFAULT_ETF_EXCLUDE_PATTERNS)

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

    def test_etf_without_market_cap_is_admitted(self) -> None:
        result = filter_stage1(
            [
                {
                    **row("VTI", market_cap=None),
                    "quote_type": "ETF",
                    "name": "Vanguard Total Stock Market ETF",
                }
            ],
            FILTERS,
        )
        self.assertEqual([survivor.ticker for survivor in result.survivors], ["VTI"])

    def test_leveraged_etf_is_rejected_by_name_pattern(self) -> None:
        result = filter_stage1(
            [
                {
                    **row("TQQQ", market_cap=None),
                    "quote_type": "ETF",
                    "name": "ProShares UltraPro QQQ 3x Shares",
                }
            ],
            FILTERS,
        )
        self.assertEqual(result.survivors, ())
        self.assertIn(
            "TQQQ",
            result.rejected["excluded leveraged/inverse/derivative-income ETF (AL-SEL-07)"],
        )

    # -- AL-SEL-07: ETF structural screen -----------------------------------
    # Passive ownership of an index, sector or asset class is admissible;
    # a fund whose distribution is written option premium is not. All three
    # tests run at Stage 1 so a structured product never costs a deep snapshot.

    def test_derivative_income_etf_is_rejected_by_issuer_pattern(self) -> None:
        result = filter_stage1(
            [
                {
                    **row("COYY", market_cap=None, sector=None),
                    "quote_type": "ETF",
                    "name": "YieldMax COIN Option Income Strategy ETF",
                    "dividend_yield": 200.0,
                }
            ],
            FILTERS,
        )
        self.assertEqual(result.survivors, ())
        self.assertIn(
            "COYY",
            result.rejected["excluded leveraged/inverse/derivative-income ETF (AL-SEL-07)"],
        )

    def test_unrecognized_issuer_is_still_caught_by_the_yield_ceiling(self) -> None:
        """A new product nobody has name-patterned yet still cannot pass."""

        result = filter_stage1(
            [
                {
                    **row("NEWX", market_cap=None),
                    "quote_type": "ETF",
                    "name": "Ascendant Enhanced Distribution Fund",
                    "dividend_yield": 35.0,
                }
            ],
            FILTERS,
        )
        self.assertEqual(result.survivors, ())
        reason = next(iter(result.rejected))
        self.assertIn("AL-SEL-07: derivative-income ETF", reason)
        self.assertIn("35.0%", reason)
        self.assertIn("20% ceiling", reason)

    def test_yield_exactly_at_the_ceiling_is_admitted(self) -> None:
        """The rule says *above* 20%, so the boundary itself survives."""

        result = filter_stage1(
            [
                {
                    **row("EDGE", market_cap=None),
                    "quote_type": "ETF",
                    "name": "High Dividend Asset Class Fund",
                    "dividend_yield": ETF_YIELD_CEILING * 100.0,
                }
            ],
            FILTERS,
        )
        self.assertEqual([survivor.ticker for survivor in result.survivors], ["EDGE"])

    def test_unclassified_etf_is_rejected_as_a_structured_product(self) -> None:
        result = filter_stage1(
            [
                {
                    **row("BAGY", market_cap=None, sector=None),
                    "quote_type": "ETF",
                    "name": "Ascendant Bitcoin Advantage Fund",
                    "dividend_yield": 5.0,
                }
            ],
            FILTERS,
        )
        self.assertEqual(result.survivors, ())
        self.assertIn(
            "BAGY",
            result.rejected["AL-SEL-07: unclassified ETF, likely structured product"],
        )

    def test_conventional_sector_etf_is_admitted(self) -> None:
        result = filter_stage1(
            [
                {
                    **row("XLK", market_cap=None, sector="Technology"),
                    "quote_type": "ETF",
                    "name": "Technology Select Sector SPDR Fund",
                    "dividend_yield": 2.0,
                }
            ],
            FILTERS,
        )
        self.assertEqual([survivor.ticker for survivor in result.survivors], ["XLK"])
        self.assertEqual(result.survivors[0].dividend_yield, 2.0)

    def test_included_etf_bypasses_every_al_sel_07_filter(self) -> None:
        """SPY and QQQ are themselves unclassified ETFs; include outranks the rule."""

        result = filter_stage1(
            [
                {
                    **row("SPY", market_cap=None, sector=None),
                    "quote_type": "ETF",
                    "name": "SPDR S&P 500 Covered Call Lookalike 3x",
                    "dividend_yield": 400.0,
                }
            ],
            FORCED,
        )
        self.assertEqual([survivor.ticker for survivor in result.survivors], ["SPY"])
        self.assertTrue(result.survivors[0].forced)

    def test_an_equity_is_untouched_by_the_etf_screen(self) -> None:
        """A high-yielding equity is a question for the scorers, not Stage 1."""

        result = filter_stage1(
            [{**row("HIYLD"), "quote_type": "EQUITY", "dividend_yield": 40.0}],
            FILTERS,
        )
        self.assertEqual([survivor.ticker for survivor in result.survivors], ["HIYLD"])

    def test_equity_without_market_cap_remains_rejected(self) -> None:
        result = filter_stage1(
            [
                {
                    **row("NOCAP", market_cap=None),
                    "quote_type": "EQUITY",
                    "name": "No Cap Incorporated",
                }
            ],
            FILTERS,
        )
        self.assertEqual(result.survivors, ())
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


if __name__ == "__main__":
    unittest.main()
