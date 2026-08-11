"""The FMP null-fill fallback: narrow by construction, offline by test.

Every test injects `http_get`. Nothing here touches the network or reads a real
key, and the tests that matter most are the ones asserting FMP is *not* called:
a fallback that fires on names it was not meant to serve is a second pipeline
wearing a fallback's name.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from wheel.snapshot_schema import validate_snapshot
from wheel_mcp.fmp import (
    FILLABLE_FIELDS,
    FmpConfigurationError,
    FmpRequestError,
    fetch_endpoint,
    fetch_fills,
    fill_document,
    merge_fill,
    missing_fields,
    normalize_payload,
)

LIVE_GOLDEN = Path(__file__).parent / "golden" / "live"
API_KEY = "test-key-not-a-real-one"


def document(**overrides):
    """A real contract document, then dented where the test needs a null."""

    base = json.loads((LIVE_GOLDEN / "2026-08-06_F.json").read_text())
    for dotted, value in overrides.items():
        section, key = dotted.split("__", 1)
        base[section][key] = value
    return base


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class Recorder:
    """An http_get that records calls and replays canned payloads by endpoint."""

    def __init__(self, payloads=None, error=None):
        self.payloads = payloads or {}
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, *, params, headers, timeout):
        self.calls.append((url, params))
        if self.error is not None:
            raise self.error
        endpoint = url.rsplit("/", 1)[-1]
        return FakeResponse(self.payloads.get(endpoint, []))

    @property
    def endpoints(self) -> list[str]:
        return [url.rsplit("/", 1)[-1] for url, _ in self.calls]


class MissingFieldTests(unittest.TestCase):
    def test_a_complete_document_needs_nothing(self) -> None:
        self.assertEqual(missing_fields(document()), ())

    def test_it_reports_only_the_nulls(self) -> None:
        self.assertEqual(
            missing_fields(document(fundamentals__net_income_ttm=None)),
            ("fundamentals.net_income_ttm",),
        )

    def test_etfs_are_skipped_entirely(self) -> None:
        """An ETF has no net income. Asking costs a request to learn ST-SEL-08."""

        etf = json.loads((LIVE_GOLDEN / "2026-08-06_SPY.json").read_text())
        self.assertIsNone(etf["identity"]["market_cap"])
        self.assertEqual(missing_fields(etf), ())

    def test_the_allowlist_is_the_whole_surface(self) -> None:
        blanked = document(
            identity__sector=None,
            analyst__recommendation_mean=None,
            dividend__yield_percent=None,
            price__current=None,
        )
        self.assertEqual(missing_fields(blanked), ())


class NormalizePayloadTests(unittest.TestCase):
    KEYS = {"fundamentals.net_income_ttm": "netIncome"}

    def test_single_element_list_is_the_documented_shape(self) -> None:
        self.assertEqual(
            normalize_payload([{"netIncome": 1234.0}], self.KEYS),
            {"fundamentals.net_income_ttm": 1234.0},
        )

    def test_bare_object_is_accepted_too(self) -> None:
        self.assertEqual(
            normalize_payload({"netIncome": 5.0}, self.KEYS),
            {"fundamentals.net_income_ttm": 5.0},
        )

    def test_unusable_shapes_yield_nothing_rather_than_raising(self) -> None:
        for payload in ([], None, "error", [1, 2]):
            self.assertEqual(normalize_payload(payload, self.KEYS), {})

    def test_non_finite_and_missing_values_are_dropped(self) -> None:
        self.assertEqual(normalize_payload([{"netIncome": None}], self.KEYS), {})
        self.assertEqual(normalize_payload([{"netIncome": "n/a"}], self.KEYS), {})


class MergeFillTests(unittest.TestCase):
    def test_a_fill_lands_and_marks_the_snapshot_mixed_source(self) -> None:
        merged = merge_fill(
            document(fundamentals__net_income_ttm=None),
            {"fundamentals.net_income_ttm": -7_395_999_744.0},
        )
        self.assertEqual(merged["fundamentals"]["net_income_ttm"], -7_395_999_744.0)
        self.assertEqual(merged["source"]["provider"], "yfinance+fmp")
        self.assertTrue(merged["source"]["partial"])

    def test_the_merged_document_still_satisfies_the_contract(self) -> None:
        merged = merge_fill(
            document(fundamentals__operating_cash_flow_ttm=None),
            {"fundamentals.operating_cash_flow_ttm": 1.0},
        )
        self.assertEqual(validate_snapshot(merged), ())

    def test_it_never_overwrites_what_yfinance_answered(self) -> None:
        """The primary source stays primary even when the fallback disagrees."""

        original = document()
        merged = merge_fill(original, {"fundamentals.net_income_ttm": 999.0})
        self.assertEqual(
            merged["fundamentals"]["net_income_ttm"],
            original["fundamentals"]["net_income_ttm"],
        )
        self.assertEqual(merged["source"]["provider"], "yfinance")
        self.assertFalse(merged["source"]["partial"])

    def test_a_field_outside_the_allowlist_is_refused(self) -> None:
        merged = merge_fill(
            document(identity__sector=None), {"identity.sector": "Technology"}
        )
        self.assertIsNone(merged["identity"]["sector"])
        self.assertEqual(merged["source"]["provider"], "yfinance")

    def test_the_input_document_is_not_mutated(self) -> None:
        original = document(fundamentals__net_income_ttm=None)
        merge_fill(original, {"fundamentals.net_income_ttm": 1.0})
        self.assertIsNone(original["fundamentals"]["net_income_ttm"])


class FetchTests(unittest.TestCase):
    def test_related_fields_share_one_request(self) -> None:
        """Net income and revenue both come from the income statement."""

        recorder = Recorder({"income-statement-ttm": [{"netIncome": 1, "revenue": 2}]})
        fills = fetch_fills(
            "F",
            API_KEY,
            ["fundamentals.net_income_ttm", "fundamentals.revenue_ttm"],
            http_get=recorder,
        )
        self.assertEqual(recorder.endpoints, ["income-statement-ttm"])
        self.assertEqual(
            fills,
            {"fundamentals.net_income_ttm": 1.0, "fundamentals.revenue_ttm": 2.0},
        )

    def test_only_endpoints_that_can_serve_the_request_are_called(self) -> None:
        recorder = Recorder({"profile": [{"marketCap": 5e9}]})
        fetch_fills("F", API_KEY, ["identity.market_cap"], http_get=recorder)
        self.assertEqual(recorder.endpoints, ["profile"])

    def test_nothing_needed_means_nothing_requested(self) -> None:
        recorder = Recorder()
        self.assertEqual(fetch_fills("F", API_KEY, [], http_get=recorder), {})
        self.assertEqual(recorder.calls, [])

    def test_one_failing_endpoint_does_not_lose_the_others(self) -> None:
        class Flaky(Recorder):
            def __call__(self, url, **kwargs):
                if url.endswith("profile"):
                    raise RuntimeError("503")
                return super().__call__(url, **kwargs)

        recorder = Flaky({"cash-flow-statement-ttm": [{"netCashProvidedByOperatingActivities": 7.0}]})
        fills = fetch_fills(
            "F",
            API_KEY,
            ["identity.market_cap", "fundamentals.operating_cash_flow_ttm"],
            http_get=recorder,
        )
        self.assertEqual(fills, {"fundamentals.operating_cash_flow_ttm": 7.0})

    def test_a_request_failure_never_leaks_the_key(self) -> None:
        recorder = Recorder(error=RuntimeError(f"boom with {API_KEY}"))
        with self.assertRaises(FmpRequestError) as caught:
            fetch_endpoint("profile", "F", API_KEY, http_get=recorder)
        self.assertNotIn(API_KEY, str(caught.exception))
        self.assertNotIn(API_KEY, repr(caught.exception.__cause__ or ""))

    def test_the_key_travels_in_a_header_not_the_query_string(self) -> None:
        recorder = Recorder({"profile": [{"marketCap": 1.0}]})
        fetch_endpoint("profile", "F", API_KEY, http_get=recorder)
        _url, params = recorder.calls[0]
        self.assertNotIn(API_KEY, json.dumps(params))

    def test_an_empty_key_is_a_configuration_error(self) -> None:
        with self.assertRaises(FmpConfigurationError):
            fetch_endpoint("profile", "F", "   ", http_get=Recorder())


class FillDocumentTests(unittest.TestCase):
    def test_the_documented_case_end_to_end(self) -> None:
        """Null net income in, filled and schema-valid out."""

        recorder = Recorder(
            {"income-statement-ttm": [{"netIncome": -7_395_999_744.0, "revenue": 1.0}]}
        )
        filled, fields = fill_document(
            document(fundamentals__net_income_ttm=None), API_KEY, http_get=recorder
        )
        self.assertEqual(fields, ("fundamentals.net_income_ttm",))
        self.assertEqual(filled["fundamentals"]["net_income_ttm"], -7_395_999_744.0)
        self.assertEqual(filled["source"]["provider"], "yfinance+fmp")
        self.assertTrue(filled["source"]["partial"])
        self.assertEqual(validate_snapshot(filled), ())

    def test_a_complete_document_makes_zero_requests(self) -> None:
        """The common case -- 98.7% of names on the 2026-08-11 run."""

        recorder = Recorder()
        filled, fields = fill_document(document(), API_KEY, http_get=recorder)
        self.assertEqual(recorder.calls, [])
        self.assertEqual(fields, ())
        self.assertEqual(filled["source"]["provider"], "yfinance")

    def test_a_fallback_that_returns_nothing_leaves_the_null_standing(self) -> None:
        recorder = Recorder({"income-statement-ttm": []})
        filled, fields = fill_document(
            document(fundamentals__net_income_ttm=None), API_KEY, http_get=recorder
        )
        self.assertEqual(fields, ())
        self.assertIsNone(filled["fundamentals"]["net_income_ttm"])
        self.assertEqual(filled["source"]["provider"], "yfinance")
        self.assertEqual(validate_snapshot(filled), ())


class AllowlistTests(unittest.TestCase):
    def test_the_allowlist_is_exactly_the_four_agreed_fields(self) -> None:
        """Widening this is a governance decision, so it is pinned here."""

        self.assertEqual(
            FILLABLE_FIELDS,
            (
                "fundamentals.net_income_ttm",
                "fundamentals.operating_cash_flow_ttm",
                "fundamentals.revenue_ttm",
                "identity.market_cap",
            ),
        )

    def test_analyst_and_sector_are_deliberately_absent(self) -> None:
        # Analyst: FMP has no Yahoo-scale recommendationMean, and that field
        # now drives a score. Sector: G-11 makes Yahoo labels authoritative.
        self.assertNotIn("analyst.recommendation_mean", FILLABLE_FIELDS)
        self.assertNotIn("identity.sector", FILLABLE_FIELDS)
        self.assertNotIn("identity.industry", FILLABLE_FIELDS)


if __name__ == "__main__":
    unittest.main()
