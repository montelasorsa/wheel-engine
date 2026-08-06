"""Layer 0 acquisition run: fetch the watchlist, write contract snapshots.

Fetch and write only -- no scoring, no interpretation (AGENTS.md §4). One bad
ticker never kills the run; it is reported and the screen lists it as missing.
Run from the repo root:

    PYTHONPATH=src python -m wheel_mcp.acquire
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from wheel.config_io import load_config, wheelops_dir

from .snapshot_writer import build_snapshot_document, write_snapshot_document
from .yahoo import (
    DEFAULT_REQUEST_THROTTLE,
    fetch_earnings_calendar,
    fetch_ticker_snapshot,
    yfinance_policy_from_config,
)


def watchlist_from_config(config: Mapping[str, Any]) -> tuple[str, ...]:
    """The operator's watchlist (ST-SEL-07). Never hardcoded."""

    raw = config.get("watchlist")
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(
            "config.yaml needs a non-empty `watchlist:` list (ST-SEL-07)."
        )
    symbols: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        symbol = str(entry).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return tuple(symbols)


def thesis_note_status(
    wheelops: Path, symbol: str
) -> tuple[bool, str | None]:
    """AL-SEL-04 input: does WheelOps/notes/<TICKER>.md exist?"""

    relative = f"notes/{symbol}.md"
    exists = (wheelops / relative).is_file()
    return exists, (relative if exists else None)


def acquire_watchlist(
    config: Mapping[str, Any],
    *,
    run_date: date,
    fetched_at: datetime,
    fetch_snapshot: Callable[..., Any] = fetch_ticker_snapshot,
    fetch_calendar: Callable[..., Any] = fetch_earnings_calendar,
) -> tuple[list[Path], list[tuple[str, str]]]:
    """Fetch every watchlist name; return (written paths, per-ticker errors)."""

    wheelops = wheelops_dir(config)
    snapshots_dir = wheelops / "snapshots"
    policy = yfinance_policy_from_config(config)

    written: list[Path] = []
    errors: list[tuple[str, str]] = []
    for symbol in watchlist_from_config(config):
        try:
            snapshot = fetch_snapshot(
                symbol, policy=policy, throttle=DEFAULT_REQUEST_THROTTLE
            )
            try:
                calendar = fetch_calendar(
                    symbol, policy=policy, throttle=DEFAULT_REQUEST_THROTTLE
                )
            except Exception:
                calendar = None  # earnings absence is survivable; scorers degrade
            thesis_exists, thesis_path = thesis_note_status(wheelops, symbol)
            document = build_snapshot_document(
                snapshot,
                calendar=calendar,
                run_date=run_date,
                fetched_at=fetched_at,
                thesis_note_exists=thesis_exists,
                thesis_note_path=thesis_path,
            )
            written.append(write_snapshot_document(document, snapshots_dir))
        except Exception as error:  # one bad ticker must never kill the run
            errors.append((symbol, f"{type(error).__name__}: {error}"))
    return written, errors


def main() -> int:
    config = load_config("config.yaml")
    now = datetime.now().astimezone()
    written, errors = acquire_watchlist(
        config, run_date=now.date(), fetched_at=now
    )
    for path in written:
        print(f"SNAPSHOT {path}", flush=True)
    for symbol, reason in errors:
        print(f"FETCH-ERROR {symbol}: {reason}", flush=True)
    print(f"ACQUIRED {len(written)} errors={len(errors)}", flush=True)
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
