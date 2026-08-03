"""Fetch and normalize free underlying data from yfinance.

The network-facing adapter is intentionally thin. All shaping is handled by
pure functions so later screening rules can be tested without network access.
This module fetches no options-chain or brokerage data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence

import pandas as pd
import yfinance as yf


class DataUnavailableError(RuntimeError):
    """Raised when yfinance returns no usable price history for a ticker."""


@dataclass(frozen=True)
class YFinanceFetchPolicy:
    """Config-driven pacing and retry policy for Yahoo requests."""

    min_request_interval_seconds: float
    max_attempts: int
    initial_backoff_seconds: float
    backoff_multiplier: float


class RequestThrottle:
    """Process-wide request gate that prevents concurrent Yahoo bursts."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._next_request_at = 0.0

    def wait(self, minimum_interval_seconds: float) -> None:
        """Wait until the next globally permitted provider-call slot."""

        with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_request_at - now)
            if delay:
                self._sleeper(delay)
                now = self._clock()
            self._next_request_at = now + minimum_interval_seconds


DEFAULT_YFINANCE_POLICY = YFinanceFetchPolicy(
    min_request_interval_seconds=0.15,
    max_attempts=3,
    initial_backoff_seconds=2.0,
    backoff_multiplier=2.0,
)
DEFAULT_REQUEST_THROTTLE = RequestThrottle()


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
    field_sources: dict[str, str] = field(default_factory=dict)


def yfinance_policy_from_config(
    config: Mapping[str, Any],
) -> YFinanceFetchPolicy:
    """Purely extract and validate Yahoo pacing settings from parsed YAML."""

    values = config["data_sources"]["yfinance"]
    policy = YFinanceFetchPolicy(
        min_request_interval_seconds=float(
            values["min_request_interval_seconds"]
        ),
        max_attempts=int(values["max_attempts"]),
        initial_backoff_seconds=float(values["initial_backoff_seconds"]),
        backoff_multiplier=float(values["backoff_multiplier"]),
    )
    if policy.min_request_interval_seconds < 0:
        raise ValueError("Yahoo request interval must not be negative.")
    if policy.max_attempts < 1:
        raise ValueError("Yahoo max_attempts must be at least 1.")
    if policy.initial_backoff_seconds < 0:
        raise ValueError("Yahoo initial backoff must not be negative.")
    if policy.backoff_multiplier < 1:
        raise ValueError("Yahoo backoff multiplier must be at least 1.")
    return policy


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
        raise DataUnavailableError("yfinance returned no price history.")

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
    """Normalize yfinance's aggregate analyst recommendation counts."""

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

    fundamentals = normalize_fundamentals(info)
    return TickerSnapshot(
        symbol=normalize_symbol(symbol),
        fundamentals=fundamentals,
        price_history=normalize_price_history(history),
        dividends=normalize_dividends(dividends),
        analyst=normalize_analyst_data(info),
        recommendation_summary=normalize_recommendation_summary(recommendations),
        option_expirations=normalize_option_expirations(option_expirations),
        field_sources={
            field_name: "yfinance"
            for field_name, value in fundamentals.items()
            if value is not None
        },
    )


def fetch_ticker_snapshot(
    symbol: str,
    *,
    period: str = "2y",
    ticker_factory: Callable[[str], Any] = yf.Ticker,
    policy: YFinanceFetchPolicy = DEFAULT_YFINANCE_POLICY,
    throttle: RequestThrottle = DEFAULT_REQUEST_THROTTLE,
    retry_sleeper: Callable[[float], None] = time.sleep,
) -> TickerSnapshot:
    """Fetch one underlying with global pacing and bounded backoff retries."""

    normalized_symbol = normalize_symbol(symbol)
    backoff_seconds = policy.initial_backoff_seconds
    last_error: Exception | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            ticker = ticker_factory(normalized_symbol)

            throttle.wait(policy.min_request_interval_seconds)
            info = ticker.get_info()

            throttle.wait(policy.min_request_interval_seconds)
            history = ticker.history(
                period=period,
                interval="1d",
                auto_adjust=False,
                actions=True,
            )

            throttle.wait(policy.min_request_interval_seconds)
            dividends = ticker.get_dividends(period=period)

            throttle.wait(policy.min_request_interval_seconds)
            recommendations = ticker.get_recommendations_summary()

            throttle.wait(policy.min_request_interval_seconds)
            # F9 checks listed-expiration existence; no chain is fetched.
            option_expirations = ticker.options

            return build_ticker_snapshot(
                normalized_symbol,
                info=info,
                history=history,
                dividends=dividends,
                recommendations=recommendations,
                option_expirations=option_expirations,
            )
        except Exception as exc:
            last_error = exc
            if attempt == policy.max_attempts:
                raise
            retry_sleeper(backoff_seconds)
            backoff_seconds *= policy.backoff_multiplier

    raise RuntimeError(
        f"Unreachable retry state for {normalized_symbol}: {last_error}"
    )


def fetch_earnings_calendar(
    symbol: str,
    *,
    ticker_factory: Callable[[str], Any] = yf.Ticker,
    policy: YFinanceFetchPolicy = DEFAULT_YFINANCE_POLICY,
    throttle: RequestThrottle = DEFAULT_REQUEST_THROTTLE,
    retry_sleeper: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any] | None:
    """Fetch yfinance calendar data through the shared throttle and retries."""

    normalized_symbol = normalize_symbol(symbol)
    backoff_seconds = policy.initial_backoff_seconds

    for attempt in range(1, policy.max_attempts + 1):
        try:
            ticker = ticker_factory(normalized_symbol)
            throttle.wait(policy.min_request_interval_seconds)
            return ticker.get_calendar()
        except Exception:
            if attempt == policy.max_attempts:
                raise
            retry_sleeper(backoff_seconds)
            backoff_seconds *= policy.backoff_multiplier
    return None
