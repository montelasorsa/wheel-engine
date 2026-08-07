"""QUARANTINED -- HTML render tests, cut with the UI layer.

Kept beside legacy/html_render.py so the operator can confirm nothing needed
was lost before deleting. Not collected by the core suite in tests/.
"""

from __future__ import annotations

import unittest

from legacy.html_render import render_html

from legacy.tests.test_csv_output import (
    FIRST_RUN_DIFF,
    SECOND_RUN_DIFF,
    build_fixture,
)


class RenderHtmlTests(unittest.TestCase):
    """Section order, change-log branches, and provenance rendering."""

    def test_sections_render_in_specified_order(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        anchors = [
            'id="header"',
            'id="changelog"',
            'id="ranked"',
            'id="missing-data"',
            'id="fetch-errors"',
            'id="fitness-fail"',
        ]
        positions = [html.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions))

    def test_header_reports_every_bucket_total(self) -> None:
        html = render_html(build_fixture(FIRST_RUN_DIFF))
        self.assertIn("Universe", html)
        self.assertIn("<b>6</b>", html)  # universe size
        self.assertIn("30.72%", html)  # F5 volatility benchmark
        self.assertIn(IV_PROXY_APPROXIMATION, html)

    def test_first_run_shows_notice_not_empty_tables(self) -> None:
        html = render_html(build_fixture(FIRST_RUN_DIFF))
        self.assertIn("First run — no comparison available yet", html)
        self.assertNotIn("Newly qualified", html)
        self.assertNotIn("Newly dropped", html)

    def test_second_run_shows_both_change_lists_with_reason(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("Newly qualified (1)", html)
        self.assertIn("Newly dropped (1)", html)
        self.assertIn("PFE", html)
        self.assertIn("Mean analyst rating 2.61", html)
        self.assertIn("2 names still qualify", html)

    def test_f10_renders_dated_chip_per_proximity_band(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("f10-warning", html)  # ORCL at 10 days
        self.assertIn("(10d)", html)
        self.assertIn("f10-far", html)  # WY at 52 days
        self.assertIn("f10-unknown", html)  # GEN has no calendar
        self.assertIn("no calendar data", html)

    def test_composite_bar_width_tracks_score(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("width: 94.5%", html)
        self.assertIn("width: 71.0%", html)

    def test_missing_data_shows_blocking_gate_and_source_label(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("HBAN", html)
        self.assertIn("Cannot evaluate: missing operating_cash_flow_ttm.", html)
        self.assertIn("operating_cash_flow_ttm via fmp", html)
        # Plain yfinance provenance must not render as a rescue chip.
        self.assertNotIn("via yfinance", html)

    def test_ranked_cell_stacks_business_identity(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("ORCL Incorporated", html)
        self.assertIn("Industrials — Specialty Widgets", html)
        self.assertIn("$45.71B", html)

    def test_filter_cells_show_score_and_raw_metric(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("100 · 4.12% / 22.33%", html)  # F5 max move / realized vol
        self.assertIn("100 · 2.31%", html)  # F6 dividend yield
        self.assertIn("88 · 31.55%", html)  # F7 realized vol proxy
        self.assertIn("100 · 18.42%", html)  # F8 pct below 2y high
        self.assertIn("66 · 2.00", html)  # F2 margin · recommendation mean

    def test_missing_data_shows_expected_vs_actual(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("net_income_ttm = $1,400M present", html)
        self.assertIn("operating_cash_flow_ttm = null", html)

    def test_change_log_rows_carry_company_names(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        # GEN newly qualified: has a snapshot this run, so its name joins.
        self.assertIn("GEN Incorporated", html)
        # PFE newly dropped with no snapshot in this run's buckets: ticker alone.
        self.assertNotIn("PFE Incorporated", html)

    def test_fetch_errors_are_listed_explicitly(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("Fetch errors (1)", html)
        self.assertIn("ANSS", html)

    def test_fitness_fail_is_a_count_not_a_list(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        self.assertIn("1 names failed fitness gates — see CSV for details.", html)

    def test_report_is_self_contained(self) -> None:
        html = render_html(build_fixture(SECOND_RUN_DIFF))
        for external in ("http://", "https://", "<script"):
            self.assertNotIn(external, html)


