"""Stage 1 universe filtering -- pure, no network, no provider import.

The screener surfaces candidates from a broad universe rather than ranking a
list the operator already chose. Enumerating that universe needs a provider
(see `wheel_mcp.universe_source`), but deciding who survives the cheap filters
is rule logic and lives here at Layer 1.

Only the two cheapest rules run at this stage:

- **ST-SEL-04** -- the absolute $10 floor. Categorical, does not scale.
- **AL-SEL-06** -- market cap floor, mid-cap or above at pilot scale. Price and
  market cap answer different questions; conflating them is how a screen
  rejects a sound $15 large-cap and accepts an unsound $45 micro-cap.

Everything else needs a full snapshot and belongs to Stage 2. Optionability
(ST-SEL-13) is deliberately NOT checked here: it costs one provider call per
name, and the Stage 2 snapshot already records `options.has_options` for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from numbers import Real
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class UniverseFilters:
    """Operator-configured Stage 1 floors and overrides."""

    price_floor: float
    market_cap_floor: float
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class Stage1Survivor:
    """One name that cleared the cheap filters, with what Stage 1 measured."""

    ticker: str
    price: float | None
    market_cap: float | None
    sector: str | None
    forced: bool = False  # from `include`: kept regardless of the floors
    # True when `price` came from the Stage 1 cache rather than a live quote.
    # It is a floor check either way, but it must not then be used as evidence
    # that a name has *not moved* -- see `should_reuse_snapshot`.
    price_is_cached: bool = False


@dataclass(frozen=True)
class Stage1Result:
    """Survivors plus a per-reason accounting of everything dropped."""

    survivors: tuple[Stage1Survivor, ...]
    rejected: Mapping[str, tuple[str, ...]]
    scanned: int

    @property
    def rejected_count(self) -> int:
        return sum(len(names) for names in self.rejected.values())


def universe_filters_from_config(config: Mapping[str, Any]) -> UniverseFilters:
    """Purely extract the Stage 1 block from parsed YAML."""

    universe = config["universe"]
    return UniverseFilters(
        price_floor=float(universe["price_floor"]),
        market_cap_floor=float(universe["market_cap_floor"]),
        include=normalize_symbols(universe.get("include") or ()),
        exclude=normalize_symbols(universe.get("exclude") or ()),
    )


def normalize_symbols(symbols: Iterable[Any]) -> tuple[str, ...]:
    """Upper-case, de-duplicate, drop blanks, preserve first-seen order."""

    seen: set[str] = set()
    ordered: list[str] = []
    for entry in symbols:
        symbol = str(entry).strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return tuple(ordered)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def filter_stage1(
    rows: Sequence[Mapping[str, Any]],
    filters: UniverseFilters,
) -> Stage1Result:
    """Apply the cheap filters to raw scanned rows.

    `rows` carry at least `ticker`, and optionally `price`, `market_cap` and
    `sector`. Missing data is a rejection with its own reason, never a silent
    drop and never a pass -- fail closed, same as the Layer 1 gates.

    `include` names bypass the floors entirely (the operator asked for them by
    name) but still obey `exclude`, which always wins.
    """

    excluded = set(filters.exclude)
    forced = set(filters.include)

    survivors: list[Stage1Survivor] = []
    rejected: dict[str, list[str]] = {}
    seen: set[str] = set()

    def reject(reason: str, ticker: str) -> None:
        rejected.setdefault(reason, []).append(ticker)

    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)

        price = _number(row.get("price"))
        market_cap = _number(row.get("market_cap"))
        sector = row.get("sector")
        sector = sector if isinstance(sector, str) and sector.strip() else None
        cached = bool(row.get("price_is_cached"))

        if ticker in excluded:
            reject("excluded by config", ticker)
            continue

        if ticker in forced:
            survivors.append(
                Stage1Survivor(
                    ticker,
                    price,
                    market_cap,
                    sector,
                    forced=True,
                    price_is_cached=cached,
                )
            )
            continue

        if price is None:
            reject("no price", ticker)
            continue
        if price < filters.price_floor:
            reject("price below floor (ST-SEL-04)", ticker)
            continue
        if market_cap is None:
            reject("no market cap", ticker)
            continue
        if market_cap < filters.market_cap_floor:
            reject("market cap below floor (AL-SEL-06)", ticker)
            continue

        survivors.append(
            Stage1Survivor(
                ticker, price, market_cap, sector, price_is_cached=cached
            )
        )

    # `include` names absent from the scan are still carried into Stage 2;
    # the deep fetch is what discovers whether they are real.
    for ticker in filters.include:
        if ticker in seen or ticker in excluded:
            continue
        seen.add(ticker)
        survivors.append(Stage1Survivor(ticker, None, None, None, forced=True))

    survivors.sort(key=lambda survivor: survivor.ticker)
    return Stage1Result(
        survivors=tuple(survivors),
        rejected={reason: tuple(names) for reason, names in sorted(rejected.items())},
        scanned=len(seen),
    )


# ---------------------------------------------------------------------------
# Stage 1 cache freshness
#
# The decision is here, pure; the files are Layer 0's (`wheel_mcp.info_cache`).
# Same split as the Stage 2 reuse decision below, for the same reason.
# ---------------------------------------------------------------------------

INFO_CACHE_MAX_AGE_DAYS = 7


def is_info_fresh(
    entry: Mapping[str, Any] | None,
    *,
    on: str,
    max_age_days: int = INFO_CACHE_MAX_AGE_DAYS,
) -> bool:
    """Is a cached Stage 1 row still usable on `on` (an ISO date)?

    Stage 1 asks three questions -- price above $10, market cap above $2B,
    which sector -- and none of them turns over daily for a name large enough
    to pass. A week-old answer is the same answer, and asking again costs 5,300
    provider calls and forty minutes.

    Fails closed on anything unparseable: a cache entry that cannot be dated is
    not a cache entry.
    """

    if not isinstance(entry, Mapping):
        return False
    fetched_on = entry.get("fetched_on")
    if not isinstance(fetched_on, str):
        return False
    try:
        fetched = date.fromisoformat(fetched_on)
        asked = date.fromisoformat(on)
    except (TypeError, ValueError):
        return False
    age = (asked - fetched).days
    return 0 <= age < max_age_days


# ---------------------------------------------------------------------------
# Stage 2 reuse decision
# ---------------------------------------------------------------------------

REUSE_PRICE_TOLERANCE = 0.05


def same_iso_week(left: str, right: str) -> bool:
    """True when two ISO dates fall in the same ISO week."""

    try:
        first, second = date.fromisoformat(left), date.fromisoformat(right)
    except (TypeError, ValueError):
        return False
    return first.isocalendar()[:2] == second.isocalendar()[:2]


def should_reuse_snapshot(
    existing: Mapping[str, Any] | None,
    *,
    run_date: str,
    stage1_price: float | None,
    tolerance: float = REUSE_PRICE_TOLERANCE,
    stage1_price_is_cached: bool = False,
) -> bool:
    """Reuse a same-week snapshot when the price has barely moved.

    A deep snapshot costs five provider calls; at universe scale that is the
    dominant cost of a run. Within one ISO week, a name whose price has not
    moved more than `tolerance` is telling the same story, so the existing
    file stands. Any doubt -- missing snapshot, missing price, different week
    -- refetches, because a stale snapshot silently scores the wrong week.

    `stage1_price_is_cached` closes a trap the Stage 1 cache would otherwise
    set. A cached price is by construction close to the price in a same-week
    snapshot -- they may even come from the same original quote -- so the
    tolerance test would pass automatically and every snapshot would be reused
    forever. The cache would look like a speedup while quietly freezing the
    screen. When the price is cached the test is refused outright: the reuse
    decision needs a *fresh* observation to be a decision at all.
    """

    if not existing:
        return False
    snapshot_date = existing.get("snapshot_date")
    if not isinstance(snapshot_date, str) or not same_iso_week(snapshot_date, run_date):
        return False
    if stage1_price_is_cached:
        return False

    stage1 = _number(stage1_price)
    try:
        previous = _number(existing["price"]["current"])
    except (KeyError, TypeError):
        return False
    if stage1 is None or previous is None or previous <= 0:
        return False
    return abs(stage1 - previous) / previous <= tolerance
