"""The network edge: paced, retrying Yahoo fetches feeding the pure core.

This is the only module in the project that talks to a data provider. It owns
pacing, retries and provider imports; it owns no screening rule. Every fetch
hands its raw response straight to `wheel.snapshot.build_ticker_snapshot`, so
the shaping stays pure and offline-testable on the other side of this boundary.

The MCP protocol wrapper that exposes these as tools is not written yet -- this
reorg moves the existing fetch code to the boundary where that wrapper will sit.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Callable, Mapping

import yfinance as yf

from wheel.snapshot import TickerSnapshot, build_ticker_snapshot, normalize_symbol


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


def fetch_ticker_info(
    symbol: str,
    *,
    ticker_factory: Callable[[str], Any] = yf.Ticker,
    policy: YFinanceFetchPolicy = DEFAULT_YFINANCE_POLICY,
    throttle: RequestThrottle = DEFAULT_REQUEST_THROTTLE,
    retry_sleeper: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any]:
    """Fetch quote metadata only -- ONE provider call.

    This is what a Stage 1 light scan needs: price, market cap and sector all
    live in `info`. `fetch_ticker_snapshot` makes five calls, which is correct
    for a deep snapshot and ruinous across a 1,500-name universe.
    """

    normalized_symbol = normalize_symbol(symbol)
    backoff_seconds = policy.initial_backoff_seconds

    for attempt in range(1, policy.max_attempts + 1):
        try:
            throttle.wait(policy.min_request_interval_seconds)
            return ticker_factory(normalized_symbol).get_info()
        except Exception:
            if attempt == policy.max_attempts:
                raise
            retry_sleeper(backoff_seconds)
            backoff_seconds *= policy.backoff_multiplier
    return {}


def fetch_earnings_calendar(
    symbol: str,
    *,
    ticker_factory: Callable[[str], Any] = yf.Ticker,
    policy: YFinanceFetchPolicy = DEFAULT_YFINANCE_POLICY,
    throttle: RequestThrottle = DEFAULT_REQUEST_THROTTLE,
    retry_sleeper: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any] | None:
    """Fetch calendar data through the shared throttle and retries."""

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
