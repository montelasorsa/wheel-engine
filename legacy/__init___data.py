"""Free-data adapters and normalization for the Wheel Screener."""

from .fmp_adapter import (
    FmpConfigurationError,
    FmpRequestError,
    fetch_fmp_operating_cash_flow_ttm,
    load_fmp_api_key,
    normalize_fmp_operating_cash_flow_ttm,
)
from .yfinance_client import (
    DEFAULT_REQUEST_THROTTLE,
    DEFAULT_YFINANCE_POLICY,
    DataUnavailableError,
    RequestThrottle,
    TickerSnapshot,
    YFinanceFetchPolicy,
    build_ticker_snapshot,
    fetch_earnings_calendar,
    fetch_ticker_snapshot,
    yfinance_policy_from_config,
)

__all__ = [
    "DataUnavailableError",
    "DEFAULT_REQUEST_THROTTLE",
    "DEFAULT_YFINANCE_POLICY",
    "RequestThrottle",
    "TickerSnapshot",
    "YFinanceFetchPolicy",
    "build_ticker_snapshot",
    "fetch_earnings_calendar",
    "fetch_ticker_snapshot",
    "yfinance_policy_from_config",
    "FmpConfigurationError",
    "FmpRequestError",
    "fetch_fmp_operating_cash_flow_ttm",
    "load_fmp_api_key",
    "normalize_fmp_operating_cash_flow_ttm",
]
