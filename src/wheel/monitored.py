"""The monitored tier and its week-over-week movement -- pure.

At universe scale the screen surfaces 50-200 scored candidates. A full list is
a phone book, not a screen, so the operator's working watchlist is a *tier*:
everything above a score floor, capped per zone and overall, with thesis-backed
names first. This is where ST-SEL-07's "roughly 10 names, reviewed every few
weeks" actually lives -- produced by the screener, not fed into it.

Week-over-week comparison reads the previous run's JSON sidecar rather than
re-parsing the rendered markdown: recovering numbers from prose tables breaks
the first time a column moves.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

# Zone bands as multiples of the derived ceiling (Constitution §2.3 /
# AL-SEL-02). Zone 1 is tradeable now; the rest are visible but locked
# (AL-SEL-03) and carry the account size that unlocks them.
ZONE_MULTIPLES: tuple[tuple[str, float], ...] = (
    ("Zone 1", 1.0),
    ("Zone 2", 2.0),
    ("Zone 3", 4.0),
)
BEYOND_ZONE = "Beyond zones"


@dataclass(frozen=True)
class MonitoredConfig:
    """Operator-configured shape of the monitored tier."""

    floor_score: float
    max_per_zone: int
    total_cap: int


def monitored_config_from_config(config: Mapping[str, Any]) -> MonitoredConfig:
    monitored = config.get("monitored") or {}
    return MonitoredConfig(
        floor_score=float(monitored.get("floor_score", 60)),
        max_per_zone=int(monitored.get("max_per_zone", 5)),
        total_cap=int(monitored.get("total_cap", 25)),
    )


def zone_for(price: float | None, ceiling: float) -> str:
    """Which zone band a price falls in; unknown price sorts to the end."""

    if price is None or ceiling <= 0:
        return BEYOND_ZONE
    for name, multiple in ZONE_MULTIPLES:
        if price <= ceiling * multiple:
            return name
    return BEYOND_ZONE


def zone_order(zone: str) -> int:
    names = [name for name, _ in ZONE_MULTIPLES] + [BEYOND_ZONE]
    return names.index(zone) if zone in names else len(names)


@dataclass(frozen=True)
class MonitoredEntry:
    """One name on the monitored list, with everything the row renders."""

    ticker: str
    score: float
    price: float | None
    zone: str
    sector: str | None
    dividend_yield: float | None
    volatility: float | None
    pct_below_high: float | None
    earnings_date: str | None
    thesis_backed: bool
    flags: tuple[str, ...]
    delta: float | None = None      # None on a first run: no prior to compare
    is_new: bool = False


def select_monitored(
    candidates: Sequence[MonitoredEntry],
    settings: MonitoredConfig,
) -> tuple[dict[str, list[MonitoredEntry]], dict[str, int]]:
    """Apply the floor, per-zone cap and total cap.

    Returns (kept by zone, how many more exist in each zone). Thesis-backed
    names sort above un-backed ones within a zone -- the operator has already
    invested judgment in them -- then by score descending.
    """

    above_floor = [c for c in candidates if c.score >= settings.floor_score]

    by_zone: dict[str, list[MonitoredEntry]] = {}
    for entry in above_floor:
        by_zone.setdefault(entry.zone, []).append(entry)

    kept: dict[str, list[MonitoredEntry]] = {}
    overflow: dict[str, int] = {}
    remaining = settings.total_cap

    for zone in sorted(by_zone, key=zone_order):
        ranked = sorted(
            by_zone[zone],
            key=lambda e: (not e.thesis_backed, -e.score, e.ticker),
        )
        allowance = max(0, min(settings.max_per_zone, remaining))
        kept[zone] = ranked[:allowance]
        overflow[zone] = len(ranked) - len(kept[zone])
        remaining -= len(kept[zone])

    return kept, overflow


# ---------------------------------------------------------------------------
# Week-over-week sidecar
# ---------------------------------------------------------------------------

SIDECAR_SUFFIX = ".monitored.json"


def sidecar_payload(
    run_date: str,
    kept: Mapping[str, Sequence[MonitoredEntry]],
    settings: MonitoredConfig,
) -> dict[str, Any]:
    """The machine-readable record next week diffs against."""

    return {
        "run_date": run_date,
        "floor_score": settings.floor_score,
        "entries": {
            entry.ticker: {
                "score": entry.score,
                "zone": entry.zone,
                "thesis_backed": entry.thesis_backed,
            }
            for entries in kept.values()
            for entry in entries
        },
    }


def write_sidecar(weeks_dir: str | Path, run_date: str, payload: Mapping[str, Any]) -> Path:
    directory = Path(weeks_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_date}{SIDECAR_SUFFIX}"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", "utf-8")
    temporary.replace(path)
    return path


def read_prior_sidecar(
    weeks_dir: str | Path, run_date: str
) -> Mapping[str, Any] | None:
    """The newest sidecar strictly before `run_date`; None on a first run."""

    directory = Path(weeks_dir)
    if not directory.is_dir():
        return None
    candidates = sorted(
        path
        for path in directory.glob(f"*{SIDECAR_SUFFIX}")
        if path.name[: -len(SIDECAR_SUFFIX)] < run_date
    )
    if not candidates:
        return None
    try:
        payload = json.loads(candidates[-1].read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def apply_movement(
    entries: Sequence[MonitoredEntry],
    prior: Mapping[str, Any] | None,
) -> list[MonitoredEntry]:
    """Attach score deltas and new-entry labels from the prior sidecar."""

    if not prior:
        return list(entries)
    prior_entries = prior.get("entries") or {}
    updated = []
    for entry in entries:
        record = prior_entries.get(entry.ticker)
        if not isinstance(record, Mapping) or not isinstance(
            record.get("score"), (int, float)
        ):
            updated.append(
                MonitoredEntry(**{**entry.__dict__, "is_new": True, "delta": None})
            )
            continue
        updated.append(
            MonitoredEntry(
                **{**entry.__dict__, "delta": entry.score - float(record["score"])}
            )
        )
    return updated


def find_exits(
    current: Sequence[MonitoredEntry],
    prior: Mapping[str, Any] | None,
    *,
    scored_now: Mapping[str, float],
    rejected_now: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Names on last week's list that are not on this week's, and why."""

    if not prior:
        return []
    present = {entry.ticker for entry in current}
    exits: list[dict[str, Any]] = []
    for ticker in sorted((prior.get("entries") or {})):
        if ticker in present:
            continue
        if ticker in rejected_now:
            reason = f"failed a gate — {rejected_now[ticker]}"
        elif ticker in scored_now:
            reason = f"dropped below the score floor (now {scored_now[ticker]:.0f})"
        else:
            reason = "no longer in the screened universe"
        exits.append({"ticker": ticker, "reason": reason})
    return exits
