"""Normalized underlying data and the pure functions that shape it.

This module holds no network code and imports no data provider. Everything
here is a pure function of data handed to it, so the whole scoring chain
downstream stays testable offline against hand-built fixtures. The fetch that
produces these inputs lives at the MCP boundary in `wheel_mcp.yahoo`, which
calls `build_ticker_snapshot` with whatever the provider returned.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping, Sequence

import pandas as pd


class DataUnavailableError(RuntimeError):
    """Raised when a provider returns no usable price history for a ticker."""


@dataclass(frozen=True)
class TickerSnapshot:
    """Normalized free-data inputs for one underlying."""

    symbol: str
    fundamentals: dict[str, float | int | str | None]
    price_history: pd.DataFrame
    dividends: pd.DataFrame
    analyst: dict[str, float | int | str | None]
    recommendation_summary: pd.DataFrame
    option_expirations: tuple[str, ...] | None


def normalize_symbol(symbol: str) -> str:
    """Return a canonical ticker symbol or reject an empty value."""

    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("Ticker symbol must not be empty.")
    return normalized


def _finite_number(value: Any) -> float | int | None:
    """Normalize numeric provider values while treating NaN as missing."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    return None


_DESCRIPTION_MAX_CHARS = 120
# A sentence boundary this early is almost always a corporate suffix
# ("... Holdings, Inc. engages in ..."), not the end of the first sentence.
_DESCRIPTION_MIN_SENTENCE_CHARS = 30


def truncate_description(
    text: object,
    max_chars: int = _DESCRIPTION_MAX_CHARS,
) -> str | None:
    """Reduce a business summary to its first sentence, capped for table rows."""

    if not isinstance(text, str) or not text.strip():
        return None
    cleaned = " ".join(text.split())

    sentence_end = len(cleaned)
    position = _DESCRIPTION_MIN_SENTENCE_CHARS
    while True:
        found = cleaned.find(". ", position)
        if found == -1:
            break
        if cleaned[found + 2 : found + 3].isupper():
            sentence_end = found + 1
            break
        position = found + 1

    sentence = cleaned[:sentence_end]
    if len(sentence) <= max_chars:
        return sentence
    return sentence[: max_chars - 1].rstrip() + "…"


def normalize_fundamentals(
    info: Mapping[str, Any],
) -> dict[str, float | int | str | None]:
    """Select stable fundamental fields from the provider's quote metadata."""

    return {
        "company_name": info.get("longName") or info.get("shortName"),
        "business_description": truncate_description(
            info.get("longBusinessSummary")
        ),
        # ST-SEL-08: the scorers must be able to tell an ETF from an equity.
        "quote_type": info.get("quoteType"),
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "current_price": _finite_number(
            info.get("currentPrice", info.get("regularMarketPrice"))
        ),
        "market_cap": _finite_number(info.get("marketCap")),
        "net_income_ttm": _finite_number(info.get("netIncomeToCommon")),
        "operating_cash_flow_ttm": _finite_number(info.get("operatingCashflow")),
        "revenue_ttm": _finite_number(info.get("totalRevenue")),
        "dividend_yield_percent": _finite_number(info.get("dividendYield")),
    }


def normalize_price_history(history: pd.DataFrame) -> pd.DataFrame:
    """Return chronological daily OHLCV/action data with stable column names."""

    if history is None or history.empty:
        raise DataUnavailableError("Provider returned no price history.")

    normalized = history.copy().reset_index()
    date_column = normalized.columns[0]
    normalized = normalized.rename(columns={date_column: "date"})
    normalized["date"] = pd.to_datetime(normalized["date"], utc=True)
    normalized = normalized.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adjusted_close",
            "Volume": "volume",
            "Dividends": "dividends",
            "Stock Splits": "stock_splits",
            "Capital Gains": "capital_gains",
        }
    )
    return normalized.sort_values("date", kind="stable").reset_index(drop=True)


def normalize_dividends(dividends: pd.Series | pd.DataFrame | None) -> pd.DataFrame:
    """Return a chronological ``date, dividend`` table."""

    columns = ["date", "dividend"]
    if dividends is None or dividends.empty:
        return pd.DataFrame(columns=columns)

    if isinstance(dividends, pd.DataFrame):
        if dividends.shape[1] != 1:
            raise ValueError("Expected a single dividend value column.")
        series = dividends.iloc[:, 0]
    else:
        series = dividends

    normalized = series.rename("dividend").rename_axis("date").reset_index()
    normalized["date"] = pd.to_datetime(normalized["date"], utc=True)
    return normalized.loc[:, columns].sort_values("date", kind="stable").reset_index(
        drop=True
    )


def _snake_case(value: object) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def normalize_recommendation_summary(
    recommendations: pd.DataFrame | None,
) -> pd.DataFrame:
    """Normalize the provider's aggregate analyst recommendation counts."""

    expected = ["period", "strong_buy", "buy", "hold", "sell", "strong_sell"]
    if recommendations is None or recommendations.empty:
        return pd.DataFrame(columns=expected)

    normalized = recommendations.copy().reset_index(drop=True)
    normalized.columns = [_snake_case(column) for column in normalized.columns]
    ordered = [column for column in expected if column in normalized.columns]
    extras = [column for column in normalized.columns if column not in ordered]
    return normalized.loc[:, ordered + extras]


def normalize_option_expirations(
    expirations: Sequence[str] | None,
) -> tuple[str, ...] | None:
    """Normalize basic option availability metadata without fetching a chain."""

    if expirations is None:
        return None
    return tuple(sorted({str(expiration) for expiration in expirations}))


def normalize_analyst_data(
    info: Mapping[str, Any],
) -> dict[str, float | int | str | None]:
    """Select summary analyst fields used by later rule-mapped screening."""

    return {
        "recommendation_mean": _finite_number(info.get("recommendationMean")),
        "recommendation_key": info.get("recommendationKey"),
        "analyst_opinions": _finite_number(info.get("numberOfAnalystOpinions")),
        "target_low_price": _finite_number(info.get("targetLowPrice")),
        "target_mean_price": _finite_number(info.get("targetMeanPrice")),
        "target_high_price": _finite_number(info.get("targetHighPrice")),
    }


def build_ticker_snapshot(
    symbol: str,
    *,
    info: Mapping[str, Any],
    history: pd.DataFrame,
    dividends: pd.Series | pd.DataFrame | None,
    recommendations: pd.DataFrame | None,
    option_expirations: Sequence[str] | None = None,
) -> TickerSnapshot:
    """Purely transform raw provider responses into one normalized snapshot."""

    return TickerSnapshot(
        symbol=normalize_symbol(symbol),
        fundamentals=normalize_fundamentals(info),
        price_history=normalize_price_history(history),
        dividends=normalize_dividends(dividends),
        analyst=normalize_analyst_data(info),
        recommendation_summary=normalize_recommendation_summary(recommendations),
        option_expirations=normalize_option_expirations(option_expirations),
    )
