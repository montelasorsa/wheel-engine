"""Layer 0: enumerate the investable universe from index constituent lists.

The screener needs ~1,500 liquid US equities to choose from. Enumerating them
properly needs an exchange listing feed we do not buy, so index composition is
the pragmatic stand-in: the S&P 500 + MidCap 400 + SmallCap 600 together cover
the large/mid/small-cap US market. **This is enumeration, not a quality
filter** -- index membership says nothing the screener's own rules do not say
better, and the rules still run on every name.

This is the project's SECOND external data source (AGENTS.md §6 named yfinance
as the single adapter; see the §10 decision-log row). It is fetched rarely,
cached, and reused stale on failure -- a Wikipedia table change should degrade
the run, not block the week.

Fetch and normalize only. No interpretation: the floors live in
`wheel.universe`, which stays pure and provider-free.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

# Wikipedia's index pages. Each carries a constituents table whose ticker
# column is named differently per page, hence the per-source column hints.
INDEX_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "index": "sp500",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "ticker_columns": ("Symbol", "Ticker symbol"),
        "name_columns": ("Security", "Company"),
        "sector_columns": ("GICS Sector",),
    },
    {
        "index": "sp400",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "ticker_columns": ("Symbol", "Ticker symbol"),
        "name_columns": ("Security", "Company"),
        "sector_columns": ("GICS Sector",),
    },
    {
        "index": "sp600",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
        "ticker_columns": ("Symbol", "Ticker symbol"),
        "name_columns": ("Security", "Company"),
        "sector_columns": ("GICS Sector",),
    },
)

CACHE_GLOB = "constituents-*.json"


class UniverseSourceError(RuntimeError):
    """Raised when no constituent list could be obtained, cache included."""


def _first_matching_column(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    lowered = {str(column).strip().lower(): column for column in frame.columns}
    for candidate in candidates:
        column = lowered.get(candidate.strip().lower())
        if column is not None:
            return column
    return None


def normalize_constituent_table(
    frame: pd.DataFrame,
    *,
    index_name: str,
    ticker_columns: Sequence[str],
    name_columns: Sequence[str] = (),
    sector_columns: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Purely reduce one scraped table to `{ticker, name, sector, index}` rows.

    Yahoo uses `-` where the indices use `.` for share classes (BRK.B is
    BRK-B); normalizing here keeps the difference out of every downstream call.
    """

    ticker_column = _first_matching_column(frame, ticker_columns)
    if ticker_column is None:
        raise UniverseSourceError(
            f"{index_name}: no ticker column among {list(ticker_columns)}; "
            f"table has {list(frame.columns)[:8]}"
        )
    name_column = _first_matching_column(frame, name_columns)
    sector_column = _first_matching_column(frame, sector_columns)

    rows: list[dict[str, Any]] = []
    for _, record in frame.iterrows():
        raw = record.get(ticker_column)
        if not isinstance(raw, str):
            raw = "" if raw is None or pd.isna(raw) else str(raw)
        ticker = raw.strip().upper().replace(".", "-")
        if not ticker:
            continue

        def text(column: str | None) -> str | None:
            if column is None:
                return None
            value = record.get(column)
            if value is None or (not isinstance(value, str) and pd.isna(value)):
                return None
            value = str(value).strip()
            return value or None

        rows.append(
            {
                "ticker": ticker,
                "name": text(name_column),
                "sector": text(sector_column),
                "index": index_name,
            }
        )
    return rows


def merge_constituents(
    tables: Sequence[Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Union the index tables, first occurrence winning, sorted by ticker."""

    merged: dict[str, dict[str, Any]] = {}
    for table in tables:
        for row in table:
            merged.setdefault(str(row["ticker"]), dict(row))
    return [merged[ticker] for ticker in sorted(merged)]


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
            {"fetched_on": on.isoformat(), "count": len(rows), "constituents": list(rows)},
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


def fetch_constituents(
    *,
    read_html: Callable[..., list[pd.DataFrame]] = pd.read_html,
    sources: Sequence[Mapping[str, Any]] = INDEX_SOURCES,
) -> list[dict[str, Any]]:
    """Fetch and merge every index table. Raises if none could be read."""

    tables: list[list[dict[str, Any]]] = []
    failures: list[str] = []
    for source in sources:
        try:
            frames = read_html(source["url"])
        except Exception as error:
            failures.append(f"{source['index']}: {type(error).__name__}: {error}")
            continue
        for frame in frames:
            try:
                rows = normalize_constituent_table(
                    frame,
                    index_name=str(source["index"]),
                    ticker_columns=source["ticker_columns"],
                    name_columns=source.get("name_columns", ()),
                    sector_columns=source.get("sector_columns", ()),
                )
            except UniverseSourceError:
                continue  # wrong table on the page; try the next one
            if rows:
                tables.append(rows)
                break
        else:
            failures.append(f"{source['index']}: no constituents table found")

    if not tables:
        raise UniverseSourceError(
            "No index constituents could be read. " + "; ".join(failures)
        )
    return merge_constituents(tables)


def load_universe(
    universe_dir: str | Path,
    *,
    on: date,
    read_html: Callable[..., list[pd.DataFrame]] = pd.read_html,
    sources: Sequence[Mapping[str, Any]] = INDEX_SOURCES,
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch constituents, caching on success and reusing stale on failure.

    Returns `(rows, staleness_warning)`. The warning is non-None whenever the
    live fetch failed and a cache stood in -- it is surfaced in the run output
    and the report header, because silently screening last month's index is
    exactly the failure this cache could otherwise hide.
    """

    try:
        rows = fetch_constituents(read_html=read_html, sources=sources)
    except Exception as error:
        cached = newest_cache(universe_dir)
        if cached is None:
            raise UniverseSourceError(
                f"Constituent fetch failed and no cache exists: {error}"
            ) from error
        rows = read_cache(cached)
        return rows, (
            f"STALE UNIVERSE: constituent fetch failed ({error}); reusing "
            f"{cached.name} with {len(rows)} names."
        )

    write_cache(universe_dir, rows, on)
    return rows, None
