"""Layer 0 output: build and write the contract snapshot Layer 1 reads.

`build_snapshot_document` is a pure function from one fetched `TickerSnapshot`
(plus calendar data and operator-gate facts) to the JSON contract defined in
`wheel.snapshot_schema`. It computes the derived metrics the contract carries
(stability, volatility proxy, chart position) because they are functions of the
full price history, which the snapshot deliberately does not carry verbatim.

Every document is validated against the contract before it is written --
fail closed: a document that does not satisfy the schema is a bug at this
boundary, never something to hand to the scorers.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any, Mapping

from wheel.flags import extract_next_earnings_date
from wheel.snapshot import TickerSnapshot

# Private on purpose: the snapshot must carry F5/F7's exact return arithmetic,
# or the golden files would freeze a different computation than the legacy
# pipeline ran. Same justification as scripts/audit_f5_vs_earnings.py had.
from wheel.scoring import (
    _daily_returns,
    _price_series,
    annualized_realized_volatility,
)
from wheel.snapshot_schema import (
    SCHEMA_VERSION,
    assert_valid_snapshot,
    snapshot_filename,
)

PROVIDER = "yfinance"

IV_PROXY_NOTE = (
    "APPROXIMATION: 30-day annualized realized volatility stands in for "
    "implied volatility; no live IV feed exists at Layer 0."
)

STABILITY_WINDOW_CALENDAR_DAYS = 365
CHART_WINDOW_CALENDAR_DAYS = 730
IV_PROXY_LOOKBACK_TRADING_DAYS = 30
ANNUALIZATION_TRADING_DAYS = 252


def _f(value: Any) -> float | None:
    """Coerce to a native finite float (JSON-safe), else None."""

    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _i(value: Any) -> int | None:
    number = _f(value)
    return None if number is None else int(number)


def _s(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _iso_week(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def build_snapshot_document(
    snapshot: TickerSnapshot,
    *,
    calendar: Mapping[str, Any] | None,
    run_date: date,
    fetched_at: datetime,
    thesis_note_exists: bool,
    thesis_note_path: str | None,
) -> dict[str, Any]:
    """Purely assemble one contract document from fetched provider data."""

    fundamentals = snapshot.fundamentals
    prices_2y = _price_series(
        snapshot.price_history, calendar_days=CHART_WINDOW_CALENDAR_DAYS
    )
    returns_1y = _daily_returns(
        snapshot.price_history, calendar_days=STABILITY_WINDOW_CALENDAR_DAYS
    )

    current_price = _f(fundamentals.get("current_price"))
    if current_price is None and len(prices_2y):
        current_price = _f(prices_2y.iloc[-1])

    max_move_1y = _f(returns_1y.abs().max()) if len(returns_1y) else None
    vol_1y = (
        _f(returns_1y.std(ddof=1) * math.sqrt(ANNUALIZATION_TRADING_DAYS))
        if len(returns_1y) >= 2
        else None
    )
    vol_30d = _f(
        annualized_realized_volatility(
            snapshot,
            lookback_trading_days=IV_PROXY_LOOKBACK_TRADING_DAYS,
            annualization_trading_days=ANNUALIZATION_TRADING_DAYS,
        )
    )

    two_year_high = _f(prices_2y.max()) if len(prices_2y) else None
    pct_below_high = (
        (two_year_high - current_price) / two_year_high
        if two_year_high is not None
        and two_year_high > 0
        and current_price is not None
        else None
    )

    dividend_values = (
        snapshot.dividends["dividend"]
        if "dividend" in snapshot.dividends.columns
        else None
    )
    pays_dividend = (
        bool((dividend_values.fillna(0) > 0).any())
        if dividend_values is not None and len(dividend_values)
        else False
    )
    last_ex_date = None
    if pays_dividend and "date" in snapshot.dividends.columns:
        last_ex_date = snapshot.dividends["date"].max().date().isoformat()

    next_earnings = extract_next_earnings_date(calendar, run_date)
    days_to_earnings = (
        (next_earnings - run_date).days if next_earnings is not None else None
    )

    expirations = snapshot.option_expirations

    document = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_date": run_date.isoformat(),
        "ticker": snapshot.symbol,
        "source": {
            "provider": PROVIDER,
            "fetched_at": fetched_at.isoformat(timespec="seconds"),
            "partial": False,
        },
        "identity": {
            "company_name": _s(fundamentals.get("company_name")),
            "quote_type": _s(fundamentals.get("quote_type")),
            "sector": _s(fundamentals.get("sector")),
            "industry": _s(fundamentals.get("industry")),
            "market_cap": _f(fundamentals.get("market_cap")),
            "currency": _s(fundamentals.get("currency")),
            "exchange": _s(fundamentals.get("exchange")),
        },
        "price": {
            "current": current_price,
            "history_start": (
                prices_2y.index.min().date().isoformat() if len(prices_2y) else None
            ),
            "history_end": (
                prices_2y.index.max().date().isoformat() if len(prices_2y) else None
            ),
            "trading_days": int(len(prices_2y)) if len(prices_2y) else None,
        },
        "fundamentals": {
            "net_income_ttm": _f(fundamentals.get("net_income_ttm")),
            "operating_cash_flow_ttm": _f(
                fundamentals.get("operating_cash_flow_ttm")
            ),
            "revenue_ttm": _f(fundamentals.get("revenue_ttm")),
        },
        "analyst": {
            "recommendation_mean": _f(snapshot.analyst.get("recommendation_mean")),
            "recommendation_key": _s(snapshot.analyst.get("recommendation_key")),
            "analyst_opinions": _i(snapshot.analyst.get("analyst_opinions")),
        },
        "dividend": {
            "pays_dividend": pays_dividend,
            "yield_percent": _f(fundamentals.get("dividend_yield_percent")),
            "last_ex_date": last_ex_date,
        },
        "stability": {
            "max_single_day_move_1y": max_move_1y,
            "realized_vol_1y": vol_1y,
        },
        "volatility": {
            "implied_volatility": None,
            "realized_vol_30d": vol_30d,
            "is_proxy": True,
            "proxy_note": IV_PROXY_NOTE,
        },
        "chart_position": {
            "two_year_high": two_year_high,
            "pct_below_two_year_high": _f(pct_below_high),
        },
        "options": {
            "has_options": (
                None if expirations is None else bool(len(expirations) > 0)
            ),
            "expirations_listed": (
                None if expirations is None else int(len(expirations))
            ),
            "chain_available": False,
            "bid_ask_spread_at_target": None,
            "open_interest_at_target": None,
            "premium_pct_of_collateral": None,
        },
        "earnings": {
            "next_earnings_date": (
                next_earnings.isoformat() if next_earnings is not None else None
            ),
            "days_to_earnings": days_to_earnings,
            "earnings_week": (
                _iso_week(next_earnings) if next_earnings is not None else None
            ),
        },
        "operator_gates": {
            "thesis_note_exists": bool(thesis_note_exists),
            "thesis_note_path": thesis_note_path,
            # An attestation the operator has not answered. Null is
            # "unasked", which is not "declined" -- see the contract doc.
            "willing_to_own_12mo": None,
        },
    }
    assert_valid_snapshot(document)
    return document


def write_snapshot_document(
    document: Mapping[str, Any],
    snapshots_dir: str | Path,
) -> Path:
    """Atomically write one validated document as YYYY-MM-DD_TICKER.json."""

    assert_valid_snapshot(document)
    directory = Path(snapshots_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / snapshot_filename(
        document["snapshot_date"], document["ticker"]
    )
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path
