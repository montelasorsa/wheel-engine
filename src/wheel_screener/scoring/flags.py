"""Pure informational flags attached only to scored survivors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Sequence

import pandas as pd

from .score_filters import ScoredTicker


@dataclass(frozen=True)
class EarningsProximityFlag:
    """Structured F10 warning preserved for the presentation layer."""

    flag_id: str
    triggered: bool
    days_to_earnings: int | None
    next_earnings_date: date | None
    rule_ids: tuple[str, ...] = ("ST-ENT-05",)


@dataclass(frozen=True)
class FlaggedScoredTicker:
    """A scored survivor plus its non-disqualifying F10 flag."""

    symbol: str
    scored: ScoredTicker
    f10: EarningsProximityFlag


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, str):
        try:
            return pd.Timestamp(value).date()
        except (TypeError, ValueError):
            return None
    return None


def extract_next_earnings_date(
    calendar: Mapping[str, Any] | None,
    run_date: date,
) -> date | None:
    """Purely select the earliest non-past date from Yahoo calendar data."""

    if not calendar:
        return None
    raw_dates = calendar.get("Earnings Date", calendar.get("earningsDate"))
    if raw_dates is None:
        return None
    values: Sequence[object]
    if isinstance(raw_dates, (list, tuple, set)):
        values = tuple(raw_dates)
    else:
        values = (raw_dates,)
    candidates = sorted(
        parsed
        for parsed in (_as_date(value) for value in values)
        if parsed is not None and parsed >= run_date
    )
    return candidates[0] if candidates else None


def compute_earnings_proximity_flag(
    calendar: Mapping[str, Any] | None,
    *,
    run_date: date,
    threshold_days: int,
) -> EarningsProximityFlag:
    """Compute F10 without affecting qualification or score."""

    next_date = extract_next_earnings_date(calendar, run_date)
    if next_date is None:
        return EarningsProximityFlag(
            flag_id="F10",
            triggered=False,
            days_to_earnings=None,
            next_earnings_date=None,
        )

    days = (next_date - run_date).days
    # F10 / ST-ENT-05: warn inside 45 days; never disqualify.
    return EarningsProximityFlag(
        flag_id="F10",
        triggered=0 <= days < threshold_days,
        days_to_earnings=days,
        next_earnings_date=next_date,
    )


def attach_earnings_flags(
    scored_tickers: Sequence[ScoredTicker],
    calendars_by_symbol: Mapping[str, Mapping[str, Any] | None],
    *,
    run_date: date,
    threshold_days: int,
) -> tuple[FlaggedScoredTicker, ...]:
    """Attach F10 to scored survivors only."""

    return tuple(
        FlaggedScoredTicker(
            symbol=scored.symbol,
            scored=scored,
            f10=compute_earnings_proximity_flag(
                calendars_by_symbol.get(scored.symbol),
                run_date=run_date,
                threshold_days=threshold_days,
            ),
        )
        for scored in scored_tickers
    )
