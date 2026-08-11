"""Layer 0: enumerate the investable universe from the CBOE options directory.

The screener needs the set of names that actually have listed options, because a
name without options cannot be wheeled at all. Index membership answers a
different question: the S&P 500/400/600 lists this module used to scrape
enumerate *large/mid/small-cap US companies*, which correlates with optionability
but does not decide it. On the 2026-08-11 run that gap was concrete -- 34 names
in the screened universe had no CBOE-listed options, including the top-ranked
name on the monitored list.

CBOE publishes its equity and index options symbol directory daily as CSV. That
is the authoritative statement of what CBOE lists, which is the closest free
approximation of "what is optionable" available. **This is enumeration, not a
quality filter** -- the screener's own rules still run on every name.

One caveat worth carrying: CBOE-listed is not the same as optionable everywhere.
Options listed on other exchanges are fungible through the OCC, so a name absent
from this directory may still trade options elsewhere. In practice the directory
covers nearly everything, and the Stage 2 snapshot's `options.has_options` stays
the per-name cross-check.

This is the project's SECOND external data source (AGENTS.md §6; see the §10
decision-log row). Fetched once a day, cached, and reused stale on failure -- a
CBOE outage should degrade the run, not block the week.

Fetch and normalize only. No interpretation: the floors live in `wheel.universe`,
which stays pure and provider-free.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from io import StringIO
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import requests

# An identifying agent with a contact route, the same courtesy the Wikipedia
# fetch needed. Anonymous scraping is what gets an IP blocked.
USER_AGENT = (
    "wheel-engine/0.1 (personal options screener; "
    "https://github.com/ - contact via repo owner)"
)
REQUEST_TIMEOUT_SECONDS = 30

CBOE_DIRECTORY_URL = (
    "https://www.cboe.com/us/options/symboldir/equity-index-options/download/"
)

# Column headings in the published file carry a leading space (" Stock Symbol"),
# so headers are matched case- and whitespace-insensitively rather than by exact
# key. Several spellings are listed because the heading is CBOE's to change.
SYMBOL_COLUMNS = ("stock symbol", "symbol", "ticker")
NAME_COLUMNS = ("company name", "name", "security")

# A truncated or error response that still parses as CSV would silently shrink
# the universe, and a smaller universe looks like a normal week. The published
# file has carried ~5,000 symbols for years; anything under this is treated as a
# failed fetch and falls through to the cache.
MINIMUM_PLAUSIBLE_SYMBOLS = 1_000

CACHE_GLOB = "constituents-*.json"


class UniverseSourceError(RuntimeError):
    """Raised when no symbol directory could be obtained, cache included."""


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def directory_url(on: date) -> str:
    """The published file for one date.

    Verified to return a valid file for weekends and holidays as well as
    trading days, so no date-walking fallback is needed.
    """

    return f"{CBOE_DIRECTORY_URL}?dt={on.isoformat()}"


def download_symbol_directory(on: date) -> str:
    """Fetch one day's directory as CSV text. Network only, no parsing."""

    response = requests.get(
        directory_url(on),
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Pure normalization
# ---------------------------------------------------------------------------


def _column_index(header: Sequence[str], candidates: Sequence[str]) -> int | None:
    lowered = [cell.strip().lower() for cell in header]
    for candidate in candidates:
        if candidate in lowered:
            return lowered.index(candidate)
    return None


def normalize_symbol_directory(csv_text: str) -> list[dict[str, Any]]:
    """Purely reduce the published CSV to `{ticker, name}` rows.

    Yahoo uses `-` where CBOE uses `.` for share classes (BRK.B is BRK-B);
    normalizing here keeps the difference out of every downstream call. Only two
    symbols in the published file need it, which is exactly why it would be
    missed if it were not done centrally.

    Duplicates keep their first occurrence. The file has none today; relying on
    that would make a future duplicate a silent double-fetch.
    """

    rows = list(csv.reader(StringIO(csv_text)))
    if not rows:
        raise UniverseSourceError("Symbol directory is empty.")

    header = rows[0]
    symbol_index = _column_index(header, SYMBOL_COLUMNS)
    if symbol_index is None:
        raise UniverseSourceError(
            f"No symbol column among {list(SYMBOL_COLUMNS)}; "
            f"header is {[cell.strip() for cell in header][:8]}"
        )
    name_index = _column_index(header, NAME_COLUMNS)

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows[1:]:
        if len(row) <= symbol_index:
            continue
        ticker = row[symbol_index].strip().upper().replace(".", "-")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        name = None
        if name_index is not None and len(row) > name_index:
            name = row[name_index].strip() or None
        normalized.append({"ticker": ticker, "name": name})
    return normalized


def apply_operator_overrides(
    rows: Sequence[Mapping[str, Any]],
    *,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Union `include`, drop `exclude`, sort by ticker.

    `include` names are unioned here rather than left to Layer 1 so they get a
    real Stage 1 scan -- `filter_stage1` would otherwise carry them through with
    null price and market cap, which reaches Stage 2 but tells the operator
    nothing. `exclude` is applied here to avoid spending a provider call on a
    name already ruled out. `wheel.universe.filter_stage1` keeps its own copy of
    both as the tested authority; this is the cheap pass, not the decision.
    """

    excluded = {str(symbol).strip().upper() for symbol in exclude if str(symbol).strip()}
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in excluded:
            continue
        merged.setdefault(ticker, {"ticker": ticker, "name": row.get("name")})

    for symbol in include:
        ticker = str(symbol).strip().upper()
        if ticker and ticker not in excluded:
            merged.setdefault(ticker, {"ticker": ticker, "name": None})

    return [merged[ticker] for ticker in sorted(merged)]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def cache_path(universe_dir: str | Path, on: date) -> Path:
    return Path(universe_dir) / f"constituents-{on.isoformat()}.json"


def newest_cache(universe_dir: str | Path) -> Path | None:
    """Newest cached list by filename; the ISO stamp sorts chronologically."""

    candidates = sorted(Path(universe_dir).glob(CACHE_GLOB))
    return candidates[-1] if candidates else None


def write_cache(
    universe_dir: str | Path, rows: Sequence[Mapping[str, Any]], on: date
) -> Path:
    directory = Path(universe_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = cache_path(directory, on)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {
                "fetched_on": on.isoformat(),
                "source": "cboe_equity_options",
                "count": len(rows),
                "constituents": list(rows),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def read_cache(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    constituents = payload.get("constituents")
    if not isinstance(constituents, list):
        raise UniverseSourceError(f"{path}: no constituents array")
    return [dict(row) for row in constituents]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def fetch_constituents(
    *,
    on: date,
    download: Callable[[date], str] = download_symbol_directory,
) -> list[dict[str, Any]]:
    """Fetch and normalize the directory. Raises if the result is implausible."""

    rows = normalize_symbol_directory(download(on))
    if len(rows) < MINIMUM_PLAUSIBLE_SYMBOLS:
        raise UniverseSourceError(
            f"Symbol directory returned only {len(rows)} symbols, under the "
            f"{MINIMUM_PLAUSIBLE_SYMBOLS} plausibility floor -- treating as a "
            "failed fetch rather than screening a truncated universe."
        )
    return rows


def load_universe(
    universe_dir: str | Path,
    *,
    on: date,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
    download: Callable[[date], str] = download_symbol_directory,
) -> tuple[list[dict[str, Any]], str | None]:
    """Load the universe, fetching at most once a day, reusing stale on failure.

    Returns `(rows, staleness_warning)`. The warning is non-None whenever the
    live fetch failed and an older cache stood in -- it is surfaced in the run
    output and the report header, because silently screening last month's
    directory is exactly the failure this cache could otherwise hide.

    The directory is published daily and does not change intraday, so a cache
    file already written for `on` is used without a fetch. Operator overrides
    are applied on the way out rather than baked into the cache, so an edit to
    `universe.include` takes effect on the next run without a refetch.
    """

    today = cache_path(universe_dir, on)
    if today.is_file():
        rows = read_cache(today)
        return apply_operator_overrides(rows, include=include, exclude=exclude), None

    # Yesterday's file is the one CBOE has certainly finished publishing.
    try:
        rows = fetch_constituents(on=on - timedelta(days=1), download=download)
    except Exception as error:
        cached = newest_cache(universe_dir)
        if cached is None:
            raise UniverseSourceError(
                f"Symbol directory fetch failed and no cache exists: {error}"
            ) from error
        rows = read_cache(cached)
        return (
            apply_operator_overrides(rows, include=include, exclude=exclude),
            f"STALE UNIVERSE: CBOE symbol directory fetch failed ({error}); "
            f"reusing {cached.name} with {len(rows)} names.",
        )

    write_cache(universe_dir, rows, on)
    return apply_operator_overrides(rows, include=include, exclude=exclude), None
