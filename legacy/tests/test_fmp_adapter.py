"""Offline fixture tests for the narrow FMP field mapper."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from wheel_screener.data import (
    fetch_fmp_operating_cash_flow_ttm,
    normalize_fmp_operating_cash_flow_ttm,
)


FIXTURE = Path(__file__).parent / "fixtures" / "fmp_cash_flow_ttm.json"


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FmpAdapterTests(unittest.TestCase):
    def test_maps_only_operating_cash_flow_from_fixture(self) -> None:
        payload = json.loads(FIXTURE.read_text())

        value = normalize_fmp_operating_cash_flow_ttm(payload)

        self.assertEqual(value, 5_331_000_000.0)

    def test_missing_or_invalid_field_maps_to_none(self) -> None:
        self.assertIsNone(normalize_fmp_operating_cash_flow_ttm([]))
        self.assertIsNone(
            normalize_fmp_operating_cash_flow_ttm(
                [{"netCashProvidedByOperatingActivities": None}]
            )
        )
        self.assertIsNone(
            normalize_fmp_operating_cash_flow_ttm(
                [{"netCashProvidedByOperatingActivities": "not-a-number"}]
            )
        )

    def test_fetch_uses_header_auth_and_only_symbol_parameter(self) -> None:
        calls = []
        payload = json.loads(FIXTURE.read_text())

        def fake_get(url, *, params, headers, timeout):
            calls.append(
                {
                    "url": url,
                    "params": params,
                    "header_names": tuple(headers),
                    "timeout": timeout,
                }
            )
            self.assertEqual(headers["apikey"], "test-secret")
            return FakeResponse(payload)

        value = fetch_fmp_operating_cash_flow_ttm(
            " kmi ",
            "test-secret",
            http_get=fake_get,
        )

        self.assertEqual(value, 5_331_000_000.0)
        self.assertEqual(calls[0]["params"], {"symbol": "KMI"})
        self.assertEqual(calls[0]["header_names"], ("apikey",))
        self.assertNotIn("apikey", calls[0]["params"])


if __name__ == "__main__":
    unittest.main()

