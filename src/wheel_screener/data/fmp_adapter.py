"""Narrow Financial Modeling Prep fallback for operating cash flow TTM.

FMP is never a primary source here. The network fetch is separated from the
pure response mapping, and this module intentionally exposes no other field.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Callable, Mapping

import requests
from dotenv import load_dotenv

from .yfinance_client import normalize_symbol


FMP_CASH_FLOW_TTM_URL = (
    "https://financialmodelingprep.com/stable/cash-flow-statement-ttm"
)


class FmpConfigurationError(RuntimeError):
    """Raised when the fallback is invoked without an API key."""


class FmpRequestError(RuntimeError):
    """Raised when FMP cannot return a usable HTTP response."""


def load_fmp_api_key(dotenv_path: str | Path = ".env") -> str:
    """Load the secret without logging or returning it in an error message."""

    load_dotenv(dotenv_path=dotenv_path, override=False)
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        raise FmpConfigurationError("FMP_API_KEY is not configured.")
    return api_key


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_fmp_operating_cash_flow_ttm(payload: object) -> float | None:
    """Purely map one FMP TTM cash-flow response to the approved field."""

    row: Mapping[str, Any] | None = None
    if isinstance(payload, list) and payload and isinstance(payload[0], Mapping):
        row = payload[0]
    elif isinstance(payload, Mapping):
        row = payload
    if row is None:
        return None
    return _finite_number(row.get("netCashProvidedByOperatingActivities"))


def fetch_fmp_cash_flow_ttm_payload(
    symbol: str,
    api_key: str,
    *,
    http_get: Callable[..., Any] = requests.get,
    timeout_seconds: float = 20.0,
) -> object:
    """Fetch the single approved FMP statement without exposing the key."""

    if not api_key.strip():
        raise FmpConfigurationError("FMP_API_KEY is not configured.")
    try:
        response = http_get(
            FMP_CASH_FLOW_TTM_URL,
            params={"symbol": normalize_symbol(symbol)},
            headers={"apikey": api_key},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
    except FmpConfigurationError:
        raise
    except Exception:
        # Do not include request details: authorization headers are secret.
        raise FmpRequestError(
            f"FMP cash-flow request failed for {normalize_symbol(symbol)}."
        ) from None


def fetch_fmp_operating_cash_flow_ttm(
    symbol: str,
    api_key: str,
    *,
    http_get: Callable[..., Any] = requests.get,
) -> float | None:
    """Fetch and normalize only ``operating_cash_flow_ttm``."""

    payload = fetch_fmp_cash_flow_ttm_payload(
        symbol,
        api_key,
        http_get=http_get,
    )
    return normalize_fmp_operating_cash_flow_ttm(payload)
