"""Layer 0 acquisition: two-stage universe scan, then deep snapshots.

Stage 1 is a light scan of the whole universe -- price, market cap, sector --
filtered by the two cheapest rules. Stage 2 fetches the full snapshot only for
Stage 1 survivors. The split exists because a deep snapshot costs five provider
calls: running it on 5,000 names to reject most of them on price alone would
spend hours learning nothing.

Fetch and write only (AGENTS.md §4). The filtering rules live in
`wheel.universe`, which is pure and provider-free; this module supplies it with
scanned rows and acts on the answer.

    PYTHONPATH=src python -m wheel_mcp.acquire
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from dataclasses import replace as dataclass_replace

from wheel.config_io import load_config, wheelops_dir
from wheel.snapshot import normalize_fundamentals
from wheel.snapshot_schema import snapshot_filename
from wheel.universe import (
    Stage1Result,
    Stage1Survivor,
    filter_stage1,
    should_reuse_snapshot,
    universe_filters_from_config,
)

from .snapshot_writer import build_snapshot_document, write_snapshot_document
from .universe_source import load_universe
from .yahoo import (
    DEFAULT_REQUEST_THROTTLE,
    fetch_earnings_calendar,
    fetch_ticker_info,
    fetch_ticker_snapshot,
    yfinance_policy_from_config,
)

SCAN_PROGRESS_EVERY = 50
SNAPSHOT_PROGRESS_EVERY = 10


def announce(message: str) -> None:
    """Progress that survives redirection.

    Python block-buffers stdout when it is not a tty, so an unflushed print
    leaves a 30-minute run looking hung. Progress the operator cannot see is
    not progress.
    """

    print(message, flush=True)


def thesis_note_status(wheelops: Path, symbol: str) -> tuple[bool, str | None]:
    """AL-SEL-04 input: does WheelOps/notes/<TICKER>.md exist?"""

    relative = f"notes/{symbol}.md"
    return (wheelops / relative).is_file(), relative


def scan_universe(
    tickers: Sequence[str],
    *,
    policy: Any,
    fetch_info: Callable[..., Any] = fetch_ticker_info,
    say: Callable[[str], None] = announce,
) -> list[dict[str, Any]]:
    """Stage 1 light scan: price, market cap and sector per name.

    Exactly ONE provider call per ticker -- `info` carries all three fields.
    The deep five-call snapshot is Stage 2's job, and spending it here would
    make the scan cost the same as the thing it exists to avoid.

    Retries are disabled for the scan: across 1,500 names the dominant failure
    is a delisted or renamed ticker, which is permanent, and three attempts
    with backoff turns each one into six wasted seconds. Stage 2 keeps the
    retry policy, where a transient failure actually costs a candidate.
    """

    scan_policy = dataclass_replace(policy, max_attempts=1)
    rows: list[dict[str, Any]] = []
    errors = 0
    for index, ticker in enumerate(tickers, 1):
        try:
            info = fetch_info(
                ticker, policy=scan_policy, throttle=DEFAULT_REQUEST_THROTTLE
            )
            fundamentals = normalize_fundamentals(info or {})
            rows.append(
                {
                    "ticker": ticker,
                    "price": fundamentals.get("current_price"),
                    "market_cap": fundamentals.get("market_cap"),
                    "sector": fundamentals.get("sector"),
                }
            )
        except Exception:
            errors += 1
            rows.append({"ticker": ticker, "price": None, "market_cap": None})
        if index % SCAN_PROGRESS_EVERY == 0 or index == len(tickers):
            say(f"  SCAN {index}/{len(tickers)} ok={len(rows) - errors} errors={errors}")
    return rows


def deep_snapshot(
    survivors: Sequence[Stage1Survivor],
    *,
    wheelops: Path,
    run_date: date,
    fetched_at: datetime,
    policy: Any,
    fetch_snapshot: Callable[..., Any],
    fetch_calendar: Callable[..., Any],
    say: Callable[[str], None],
) -> dict[str, Any]:
    """Stage 2: full snapshot per survivor, reusing same-week stable ones."""

    snapshots_dir = wheelops / "snapshots"
    written: list[Path] = []
    reused: list[str] = []
    errors: list[tuple[str, str]] = []

    for index, survivor in enumerate(survivors, 1):
        ticker = survivor.ticker
        existing_path = snapshots_dir / snapshot_filename(run_date.isoformat(), ticker)
        existing: Mapping[str, Any] | None = None

        # Look at the newest snapshot for this ticker, whatever its date.
        candidates = sorted(snapshots_dir.glob(f"*_{ticker}.json"))
        if candidates:
            try:
                existing = json.loads(candidates[-1].read_text())
            except (OSError, json.JSONDecodeError):
                existing = None

        if should_reuse_snapshot(
            existing, run_date=run_date.isoformat(), stage1_price=survivor.price
        ):
            reused.append(ticker)
        else:
            try:
                snapshot = fetch_snapshot(
                    ticker, policy=policy, throttle=DEFAULT_REQUEST_THROTTLE
                )
                try:
                    calendar = fetch_calendar(
                        ticker, policy=policy, throttle=DEFAULT_REQUEST_THROTTLE
                    )
                except Exception:
                    calendar = None  # scorers degrade; the run continues
                exists, path = thesis_note_status(wheelops, ticker)
                document = build_snapshot_document(
                    snapshot,
                    calendar=calendar,
                    run_date=run_date,
                    fetched_at=fetched_at,
                    thesis_note_exists=exists,
                    thesis_note_path=path if exists else None,
                )
                written.append(write_snapshot_document(document, snapshots_dir))
            except Exception as error:
                errors.append((ticker, f"{type(error).__name__}: {error}"))

        if index % SNAPSHOT_PROGRESS_EVERY == 0 or index == len(survivors):
            say(
                f"  SNAPSHOT {index}/{len(survivors)} "
                f"fetched={len(written)} reused={len(reused)} errors={len(errors)}"
            )
    return {"written": written, "reused": reused, "errors": errors}


def acquire_universe(
    config: Mapping[str, Any],
    *,
    run_date: date,
    fetched_at: datetime,
    fetch_snapshot: Callable[..., Any] = fetch_ticker_snapshot,
    fetch_calendar: Callable[..., Any] = fetch_earnings_calendar,
    fetch_info: Callable[..., Any] = fetch_ticker_info,
    say: Callable[[str], None] = announce,
) -> dict[str, Any]:
    """Run both stages; return the counts the screen header reports."""

    wheelops = wheelops_dir(config)
    policy = yfinance_policy_from_config(config)
    filters = universe_filters_from_config(config)

    say("STAGE 0 loading the CBOE options symbol directory")
    constituents, staleness = load_universe(
        wheelops / "universe",
        on=run_date,
        include=filters.include,
        exclude=filters.exclude,
    )
    if staleness:
        say(f"  WARNING {staleness}")
    tickers = [str(row["ticker"]) for row in constituents]
    say(f"  UNIVERSE {len(tickers)} names with listed options")

    say(f"STAGE 1 scanning {len(tickers)} names")
    rows = scan_universe(tickers, policy=policy, fetch_info=fetch_info, say=say)
    stage1: Stage1Result = filter_stage1(rows, filters)
    say(
        f"  SURVIVORS {len(stage1.survivors)} of {stage1.scanned} "
        f"(rejected {stage1.rejected_count})"
    )
    for reason, names in stage1.rejected.items():
        say(f"    {reason}: {len(names)}")

    say(f"STAGE 2 deep snapshot for {len(stage1.survivors)} survivors")
    stage2 = deep_snapshot(
        stage1.survivors,
        wheelops=wheelops,
        run_date=run_date,
        fetched_at=fetched_at,
        policy=policy,
        fetch_snapshot=fetch_snapshot,
        fetch_calendar=fetch_calendar,
        say=say,
    )
    for ticker, reason in stage2["errors"]:
        say(f"  FETCH-ERROR {ticker}: {reason}")

    return {
        "universe_size": len(tickers),
        "universe_stale_warning": staleness,
        "stage1_survivors": len(stage1.survivors),
        "stage1_rejected": stage1.rejected,
        "snapshots_written": len(stage2["written"]),
        "snapshots_reused": len(stage2["reused"]),
        "fetch_errors": stage2["errors"],
        "survivor_tickers": tuple(s.ticker for s in stage1.survivors),
    }


def write_run_manifest(
    wheelops: Path, run_date: date, summary: Mapping[str, Any]
) -> Path:
    """Persist Stage 1/2 counts so the Layer 1 screen can report them.

    The screen reads snapshots, not the acquisition run, so without this it
    could not know how large the universe was or how many names never made it
    to Stage 2.
    """

    directory = wheelops / "universe"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"run-{run_date.isoformat()}.json"
    payload = {
        key: value
        for key, value in summary.items()
        if key not in ("survivor_tickers",)
    }
    payload["stage1_rejected"] = {
        reason: len(names) for reason, names in summary["stage1_rejected"].items()
    }
    payload["fetch_errors"] = len(summary["fetch_errors"])
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def main() -> int:
    config = load_config("config.yaml")
    now = datetime.now().astimezone()
    summary = acquire_universe(config, run_date=now.date(), fetched_at=now)
    write_run_manifest(wheelops_dir(config), now.date(), summary)
    print(
        f"ACQUIRED universe={summary['universe_size']} "
        f"stage1={summary['stage1_survivors']} "
        f"written={summary['snapshots_written']} "
        f"reused={summary['snapshots_reused']} "
        f"errors={len(summary['fetch_errors'])}",
        flush=True,
    )
    return 0 if summary["snapshots_written"] or summary["snapshots_reused"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
