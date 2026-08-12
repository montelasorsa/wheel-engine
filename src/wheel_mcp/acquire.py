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
import shutil
from typing import Any, Callable, Mapping, Sequence

from dataclasses import replace as dataclass_replace

from wheel.config_io import load_config, wheelops_dir
from wheel.snapshot import normalize_fundamentals
from wheel.snapshot_schema import snapshot_filename
from wheel.universe import (
    Stage1Result,
    Stage1Survivor,
    filter_stage1,
    is_info_fresh,
    should_reuse_snapshot,
    universe_filters_from_config,
)

from .fmp import FmpConfigurationError, fill_document, load_fmp_api_key
from .info_cache import (
    entry_from_row,
    has_current_fields,
    prune,
    read_info_cache,
    row_from_entry,
    write_info_cache,
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


class FallbackFiller:
    """Applies the FMP null-fill, degrading rather than failing the run.

    A two-hour acquisition must not die because a key is absent or a fallback
    request timed out -- but it must not hide it either. The first failure is
    announced with its reason, subsequent ones are counted, and the run reports
    the total. The snapshot is written either way, with its null intact, and
    §4.4's `data_incomplete` flag still reaches the operator through Layer 1.
    """

    def __init__(self, *, say: Callable[[str], None], load_key=load_fmp_api_key):
        self.say = say
        self.filled_fields = 0
        self.filled_names: list[str] = []
        self.failures = 0
        try:
            self._api_key: str | None = load_key()
        except FmpConfigurationError as error:
            self._api_key = None
            say(f"  FMP DISABLED {error}")

    @property
    def enabled(self) -> bool:
        return self._api_key is not None

    def apply(self, document: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._api_key is None:
            return document
        try:
            filled, fields = fill_document(document, self._api_key)
        except Exception as error:
            self.failures += 1
            if self.failures == 1:
                self.say(f"  FMP ERROR (first of run) {type(error).__name__}: {error}")
            return document
        if fields:
            self.filled_fields += len(fields)
            self.filled_names.append(str(document.get("ticker", "?")))
            self.say(
                f"  FMP FILLED {document.get('ticker')}: {', '.join(fields)}"
            )
        return filled

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "names_filled": len(self.filled_names),
            "fields_filled": self.filled_fields,
            "request_failures": self.failures,
        }


def scan_universe(
    tickers: Sequence[str],
    *,
    policy: Any,
    fetch_info: Callable[..., Any] = fetch_ticker_info,
    say: Callable[[str], None] = announce,
    cached: Mapping[str, Any] | None = None,
    on: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Stage 1 light scan: price, market cap and sector per name.

    Exactly ONE provider call per ticker -- `info` carries all three fields --
    and none at all for a name still fresh in the cache. The deep five-call
    snapshot is Stage 2's job, and spending it here would make the scan cost
    the same as the thing it exists to avoid.

    Retries are disabled for the scan: across 5,000 names the dominant failure
    is a delisted or renamed ticker, which is permanent, and three attempts
    with backoff turns each one into six wasted seconds. Stage 2 keeps the
    retry policy, where a transient failure actually costs a candidate.

    Returns `(rows, fresh_entries)` -- the scan rows, and just the entries
    actually fetched this run, for the caller to write back to the cache.
    """

    scan_policy = dataclass_replace(policy, max_attempts=1)
    cache = cached or {}
    run_date = on or date.today()
    stamp = run_date.isoformat()

    rows: list[dict[str, Any]] = []
    fetched_entries: dict[str, dict[str, Any]] = {}
    errors = 0
    hits = 0

    for index, ticker in enumerate(tickers, 1):
        entry = cache.get(ticker)
        if is_info_fresh(entry, on=stamp) and has_current_fields(entry):
            rows.append(row_from_entry(ticker, entry))
            hits += 1
        else:
            try:
                info = fetch_info(
                    ticker, policy=scan_policy, throttle=DEFAULT_REQUEST_THROTTLE
                )
                fundamentals = normalize_fundamentals(info or {})
                row = {
                    "ticker": ticker,
                    "price": fundamentals.get("current_price"),
                    "market_cap": fundamentals.get("market_cap"),
                    "sector": fundamentals.get("sector"),
                    "quote_type": fundamentals.get("quote_type"),
                    "name": fundamentals.get("company_name"),
                }
                rows.append(row)
                fetched_entries[ticker] = entry_from_row(row, run_date)
            except Exception:
                # Not cached: a failed lookup is usually a delisted ticker, and
                # caching that would keep it out of the universe for a week
                # without anyone noticing it had gone.
                errors += 1
                rows.append({"ticker": ticker, "price": None, "market_cap": None})
        if index % SCAN_PROGRESS_EVERY == 0 or index == len(tickers):
            say(
                f"  SCAN {index}/{len(tickers)} cached={hits} "
                f"fetched={len(fetched_entries)} errors={errors}"
            )
    return rows, fetched_entries


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
    filler: "FallbackFiller | None" = None,
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
        existing_source: Path | None = None

        # Look at the newest snapshot for this ticker, whatever its date.
        candidates = sorted(snapshots_dir.glob(f"*_{ticker}.json"))
        if candidates:
            try:
                existing_source = candidates[-1]
                existing = json.loads(existing_source.read_text())
            except (OSError, json.JSONDecodeError):
                existing = None

        reuse = should_reuse_snapshot(
            existing,
            run_date=run_date.isoformat(),
            stage1_price=survivor.price,
            stage1_price_is_cached=survivor.price_is_cached,
        )
        if reuse and existing_source is not None:
            try:
                # Layer 1 enumerates only this run date. Keep the immutable
                # source snapshot and materialize a dated copy for this run.
                if existing_source != existing_path:
                    shutil.copy2(existing_source, existing_path)
                reused.append(ticker)
            except OSError:
                # A copy failure must not silently omit a Stage 1 survivor.
                # Fall through to a fresh provider fetch for this name.
                reuse = False

        if not reuse:
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
                # yfinance first, always. The fallback sees only what it left
                # null, and only the four allowlisted fields.
                if filler is not None:
                    document = filler.apply(document)
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

    cache_dir = wheelops / "cache"
    cached = read_info_cache(cache_dir, run_date)
    say(f"STAGE 1 scanning {len(tickers)} names ({len(cached)} cached)")
    rows, fetched_entries = scan_universe(
        tickers,
        policy=policy,
        fetch_info=fetch_info,
        say=say,
        cached=cached,
        on=run_date,
    )
    if fetched_entries:
        write_info_cache(cache_dir, prune(fetched_entries, tickers), run_date)
    cache_hits = sum(1 for row in rows if row.get("price_is_cached"))

    stage1: Stage1Result = filter_stage1(rows, filters)
    say(
        f"  SURVIVORS {len(stage1.survivors)} of {stage1.scanned} "
        f"(rejected {stage1.rejected_count})"
    )
    for reason, names in stage1.rejected.items():
        say(f"    {reason}: {len(names)}")

    say(f"STAGE 2 deep snapshot for {len(stage1.survivors)} survivors")
    filler = FallbackFiller(say=say)
    stage2 = deep_snapshot(
        stage1.survivors,
        wheelops=wheelops,
        run_date=run_date,
        fetched_at=fetched_at,
        policy=policy,
        fetch_snapshot=fetch_snapshot,
        fetch_calendar=fetch_calendar,
        say=say,
        filler=filler,
    )
    for ticker, reason in stage2["errors"]:
        say(f"  FETCH-ERROR {ticker}: {reason}")
    fallback = filler.summary()
    say(
        f"  FALLBACK enabled={fallback['enabled']} "
        f"names={fallback['names_filled']} fields={fallback['fields_filled']} "
        f"failures={fallback['request_failures']}"
    )

    return {
        "universe_size": len(tickers),
        "universe_stale_warning": staleness,
        "stage1_survivors": len(stage1.survivors),
        "stage1_rejected": stage1.rejected,
        "stage1_cache_hits": cache_hits,
        "stage1_fetched": len(fetched_entries),
        "snapshots_written": len(stage2["written"]),
        "snapshots_reused": len(stage2["reused"]),
        "fetch_errors": stage2["errors"],
        "fallback": fallback,
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
