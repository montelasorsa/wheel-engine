"""Layer 0: the Stage 1 quote-metadata cache.

Stage 1 asks one `info` call per name for price, market cap and sector. Across
the CBOE universe that is 5,300 calls and roughly forty minutes -- the dominant
cost of a run, spent re-learning that a $40B company is still worth more than
$2B.

None of those three answers turns over daily for a name large enough to pass
the floors, so they are cached for a week. On a repeat run inside that week
Stage 1 makes no provider calls at all.

Files are named by ISO week (`ticker_info_2026-W33.json`) so a run's writes
land together and old ones are obvious at a glance, but the *decision* is made
per entry against its own `fetched_on` date -- see `wheel.universe.is_info_fresh`.
Those are different things: a Monday run must still see the previous Tuesday's
entries, which live in the previous week's file. Reading the current and prior
week's files covers any seven-day window.

Files only. The freshness rule is pure and lives at Layer 1, in the same split
as the Stage 2 snapshot-reuse decision.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

CACHE_FIELDS = ("price", "market_cap", "sector")


def iso_week_label(on: date) -> str:
    year, week, _ = on.isocalendar()
    return f"{year}-W{week:02d}"


def cache_path(cache_dir: str | Path, on: date) -> Path:
    return Path(cache_dir) / f"ticker_info_{iso_week_label(on)}.json"


def _read_one(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("entries")
    return entries if isinstance(entries, dict) else {}


def read_info_cache(cache_dir: str | Path, on: date) -> dict[str, Any]:
    """Every entry from this ISO week and the previous one.

    Both are needed because the reuse window is seven days, not one calendar
    week: a Monday run is three days from the previous Friday's fetch, and that
    fetch is in last week's file. The current week wins on conflict, being the
    newer observation.
    """

    merged: dict[str, Any] = {}
    for day in (on - timedelta(days=7), on):
        merged.update(_read_one(cache_path(cache_dir, day)))
    return merged


def write_info_cache(
    cache_dir: str | Path,
    entries: Mapping[str, Mapping[str, Any]],
    on: date,
) -> Path:
    """Merge `entries` into this week's file and write it atomically.

    Merges rather than replaces so a partial run -- interrupted, or scanning a
    narrowed universe -- adds to the cache instead of discarding what an earlier
    run in the same week already paid for.
    """

    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = cache_path(directory, on)

    existing = _read_one(path)
    existing.update({ticker: dict(row) for ticker, row in entries.items()})

    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {
                "iso_week": iso_week_label(on),
                "written_on": on.isoformat(),
                "count": len(existing),
                "entries": existing,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def entry_from_row(row: Mapping[str, Any], on: date) -> dict[str, Any]:
    """The cacheable part of one scanned row, stamped with its fetch date."""

    entry = {field: row.get(field) for field in CACHE_FIELDS}
    entry["fetched_on"] = on.isoformat()
    return entry


def row_from_entry(ticker: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    """One cache entry as a Stage 1 scan row, marked as a cached price.

    `price_is_cached` is what stops a week-old price being read as evidence
    that a name has not moved. `wheel.universe.should_reuse_snapshot` refuses
    the price-tolerance test when it is set.
    """

    row: dict[str, Any] = {"ticker": ticker, "price_is_cached": True}
    for field in CACHE_FIELDS:
        row[field] = entry.get(field)
    return row


def prune(entries: Mapping[str, Any], keep: Sequence[str]) -> dict[str, Any]:
    """Drop entries for tickers no longer in the universe."""

    wanted = set(keep)
    return {
        ticker: value for ticker, value in entries.items() if ticker in wanted
    }
