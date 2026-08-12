"""The weekly screen report: pure functions from scored snapshots to markdown.

Everything here is a pure function of (documents, rule results, positions,
account config). No clock, no filesystem, no network -- `screen.py` owns the
edges. The report never recomputes a verdict; it renders what the scorers said,
so it can never disagree with them.

Five sections: header, monitored tier, ranked candidates, portfolio context,
and a grouped flagged/rejected summary. At universe scale the last two matter
most -- listing 150 rejected names individually is noise, while the handful
carrying FLAG verdicts is exactly what needs a human.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from .monitored import (
    BEYOND_ZONE,
    MonitoredConfig,
    MonitoredEntry,
    apply_movement,
    find_exits,
    select_monitored,
    zone_for,
    zone_order,
)
from .scorers import RuleKind, RuleResult, Verdict
from .snapshot_schema import resolve_field

# The three fitness gates; AL-SEL-04 (thesis) is deliberately separate so a
# fresh universe reads "worth writing theses for", not "466 rejections".
FITNESS_GATE_RULES = ("ST-SEL-01", "ST-SEL-04", "ST-SEL-10")
THESIS_RULE = "AL-SEL-04"

# How many ST-SEL-01 split flags to list by name before collapsing to a count.
# Enough to work through in a sitting; past that it is a research backlog, not
# a to-do list, and the count is the more useful fact.
SPLIT_FLAG_LISTING_CAP = 20

# Composite weights map config keys to the rules that carry them. A rule whose
# `score` is None is excluded and the remaining weights renormalized -- an ETF
# is ranked on what applies to it, not punished for what does not (§4.4).
#
# ST-SEL-05 (stability) is deliberately absent: it has no continuous form, and
# a verdict bucket mixed into a field of curves would put a 100/50/0 step back
# into the ranking. It still runs, still renders, and still shows the operator
# the largest single-day move; it simply does not order the list.
COMPOSITE_WEIGHT_KEYS: Mapping[str, str] = {
    "ST-SEL-10": "volatility",
    "ST-SEL-12": "chart_position",
    "ST-SEL-01": "cash_flow_strength",
    "ST-SEL-06": "dividend",
    "ST-SEL-02": "analyst_strength",
}


def _get(document: Mapping[str, Any], dotted: str) -> Any:
    try:
        return resolve_field(document, dotted)
    except KeyError:
        return None


def _by_rule(results: Sequence[RuleResult]) -> dict[str, RuleResult]:
    return {result.rule_id: result for result in results}


@dataclass(frozen=True)
class ScoredName:
    """One watchlist name: its snapshot document and every rule verdict."""

    document: Mapping[str, Any]
    results: tuple[RuleResult, ...]

    @property
    def ticker(self) -> str:
        return str(self.document.get("ticker", "?"))

    @property
    def price(self) -> float | None:
        value = _get(self.document, "price.current")
        return float(value) if isinstance(value, (int, float)) else None


def composite_score(
    results: Sequence[RuleResult],
    weights: Mapping[str, float],
) -> float | None:
    """Weighted 0-100 composite over the rules that could rank this name.

    Reads each rule's continuous `score`, not its verdict. That is the whole
    point: five verdicts can express at most a few dozen distinct composites,
    which is why the 2026-08-11 run tied 255 names at exactly 100 and then broke
    those ties alphabetically.

    A rule with `score is None` contributes nothing and its weight is
    renormalized away, so an ETF is ranked on the components that govern it.
    """

    by_rule = _by_rule(results)
    total_weight = 0.0
    total = 0.0
    for rule_id, weight_key in COMPOSITE_WEIGHT_KEYS.items():
        result = by_rule.get(rule_id)
        if result is None or result.score is None:
            continue
        weight = float(weights[weight_key])
        total += result.score * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return total / total_weight


def data_incomplete(results: Sequence[RuleResult]) -> bool:
    """§4.4: scored on available fields, flagged when any field was missing."""

    return any(r.verdict is Verdict.CANNOT_EVALUATE for r in results)


def classify(results: Sequence[RuleResult]) -> str:
    """rejected | unevaluable | thesis_required | candidate."""

    by_rule = _by_rule(results)
    fitness = [by_rule[r] for r in FITNESS_GATE_RULES if r in by_rule]
    if any(r.verdict is Verdict.FAIL for r in fitness):
        return "rejected"
    if any(r.verdict is Verdict.CANNOT_EVALUATE for r in fitness):
        return "unevaluable"
    thesis = by_rule.get(THESIS_RULE)
    if thesis is None or thesis.verdict is Verdict.CANNOT_EVALUATE:
        return "unevaluable"
    if thesis.verdict is Verdict.FAIL:
        return "thesis_required"
    return "candidate"


# ---------------------------------------------------------------------------
# Zone derivation -- Constitution §2.3 / AL-SEL-02, AL-SEL-03
# ---------------------------------------------------------------------------


def zone_ceiling(net_liq: float, per_name_cap: float) -> float:
    """max_strike = (net_liquidity × per_name_cap) ÷ 100."""

    return net_liq * per_name_cap / 100.0


def in_zone(price: float | None, ceiling: float) -> bool | None:
    """Strike ≈ price stands in at screen time; the real strike is below it."""

    if price is None:
        return None
    return price <= ceiling


def unlock_net_liq(price: float, per_name_cap: float) -> float:
    """The account size at which this price enters the zone."""

    return price * 100.0 / per_name_cap


# ---------------------------------------------------------------------------
# Positions -- tolerant aggregation over the WheelOps/positions/ ledger
# ---------------------------------------------------------------------------


def open_positions(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rows with usable numbers and a status of open (or none stated)."""

    kept = []
    for row in rows:
        status = str(row.get("status") or "open").strip().lower()
        if status != "open":
            continue
        try:
            strike = float(row.get("strike"))
        except (TypeError, ValueError):
            continue
        try:
            contracts = int(float(row.get("contracts") or 1))
        except (TypeError, ValueError):
            contracts = 1
        kept.append(
            {
                "ticker": str(row.get("ticker") or "?").upper(),
                "sector": str(row.get("sector") or "unknown"),
                "strike": strike,
                "contracts": contracts,
                "collateral": strike * 100.0 * contracts,
            }
        )
    return kept


def assignment_capacity(
    positions: Sequence[Mapping[str, Any]],
    net_liq: float,
) -> dict[str, float]:
    """AL-CSH-02: total obligation if everything assigned vs what exists."""

    needed = sum(float(p["collateral"]) for p in positions)
    return {
        "needed": needed,
        "available": net_liq,
        "reserve_fraction": (net_liq - needed) / net_liq if net_liq > 0 else 0.0,
    }


def sector_exposure(
    positions: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Deployed collateral per sector, as fractions of total deployed."""

    total = sum(float(p["collateral"]) for p in positions)
    if total <= 0:
        return {}
    by_sector: dict[str, float] = {}
    for position in positions:
        by_sector[position["sector"]] = (
            by_sector.get(position["sector"], 0.0) + float(position["collateral"])
        )
    return {sector: value / total for sector, value in sorted(by_sector.items())}


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _money(value: float) -> str:
    return f"${value:,.0f}" if abs(value) >= 100 else f"${value:,.2f}"


def _plural(count: int, word: str) -> str:
    return word if count == 1 else f"{word}s"


def _vol_cell(by_rule: Mapping[str, RuleResult]) -> str:
    result = by_rule.get("ST-SEL-10")
    if result is None:
        return "—"
    vol = result.metrics.get("implied_volatility")
    if vol is None:
        vol = result.metrics.get("realized_vol_30d")
    if vol is None:
        return "—"
    return f"{float(vol):.0%}†"


def _high_cell(by_rule: Mapping[str, RuleResult]) -> str:
    result = by_rule.get("ST-SEL-12")
    if result is None:
        return "—"
    below = result.metrics.get("pct_below_two_year_high")
    if below is None:
        return "—"
    # abs(): a name at or above its high yields a signed zero or a small
    # negative, and "-0.00% below" is arithmetic leaking into prose. The metric
    # itself stays signed so the snapshot keeps telling the truth.
    return f"{abs(float(below)):.0%} below 2y high"


def _earnings_cell(by_rule: Mapping[str, RuleResult]) -> str:
    result = by_rule.get("ST-ENT-05")
    if result is None or result.verdict is Verdict.NOT_APPLICABLE:
        return "none (no earnings)"
    day = result.metrics.get("next_earnings_date")
    days = result.metrics.get("days_to_earnings")
    if day is None:
        return "unknown"
    text = f"{day} ({int(days)}d)" if days is not None else str(day)
    return f"⚠ {text}" if result.verdict is Verdict.FLAG else text


def _dividend_cell(document: Mapping[str, Any]) -> str:
    if _get(document, "dividend.pays_dividend"):
        yield_percent = _get(document, "dividend.yield_percent")
        if isinstance(yield_percent, (int, float)):
            return f"{yield_percent:.2f}%"
        return "yes"
    return "—"


def _flags_cell(name: ScoredName) -> str:
    flags = []
    if data_incomplete(name.results):
        flags.append("data_incomplete")
    return ", ".join(flags) if flags else "—"


def _candidate_row(
    rank: str,
    name: ScoredName,
    composite: float | None,
    zone_text: str,
) -> str:
    by_rule = _by_rule(name.results)
    price = _money(name.price) if name.price is not None else "—"
    sector = _get(name.document, "identity.sector") or "—"
    composite_text = "—" if composite is None else f"{composite:.0f}"
    return (
        f"| {rank} | {name.ticker} | {composite_text} | {price} | {zone_text} "
        f"| {sector} | {_dividend_cell(name.document)} | {_vol_cell(by_rule)} "
        f"| {_high_cell(by_rule)} | {_earnings_cell(by_rule)} "
        f"| {_flags_cell(name)} |"
    )


_CANDIDATE_HEADER = (
    "| # | Ticker | Score | Price | Zone | Sector | Div | Vol† | Chart | "
    "Earnings | Flags |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|"
)


def _sort_ranked(
    names: Sequence[tuple[ScoredName, float | None]],
) -> list[tuple[ScoredName, float | None]]:
    return sorted(
        names,
        key=lambda pair: (
            (1, 0.0, pair[0].ticker)
            if pair[1] is None
            else (0, -pair[1], pair[0].ticker)
        ),
    )


# ---------------------------------------------------------------------------
# Monitored-tier assembly
# ---------------------------------------------------------------------------


def _is_thesis_backed(name: "ScoredName") -> bool:
    thesis = _by_rule(name.results).get(THESIS_RULE)
    return thesis is not None and thesis.verdict is Verdict.PASS


def _metric(by_rule: Mapping[str, RuleResult], rule: str, key: str) -> Any:
    result = by_rule.get(rule)
    return None if result is None else result.metrics.get(key)


def _entry_flags(name: "ScoredName") -> tuple[str, ...]:
    """Short labels for every FLAG verdict, plus the data-quality marker."""

    # ST-SEL-10 and ST-SEL-12 are absent on purpose: both became continuous
    # score components, so their old "elevated vol" / "near high" labels have
    # no verdict left to attach to. The vol and chart columns carry the number.
    labels = {
        "ST-SEL-01": "net income/OCF split",
        "ST-ENT-05": "earnings soon",
    }
    flags = [
        labels.get(result.rule_id, result.rule_id)
        for result in name.results
        if result.verdict is Verdict.FLAG
    ]
    if data_incomplete(name.results):
        flags.append("data_incomplete")
    return tuple(flags)


def build_monitored_entry(
    name: "ScoredName",
    *,
    score: float,
    ceiling: float,
) -> MonitoredEntry:
    by_rule = _by_rule(name.results)
    volatility = _metric(by_rule, "ST-SEL-10", "implied_volatility")
    if volatility is None:
        volatility = _metric(by_rule, "ST-SEL-10", "realized_vol_30d")
    thesis = by_rule.get(THESIS_RULE)
    return MonitoredEntry(
        ticker=name.ticker,
        score=score,
        price=name.price,
        zone=zone_for(name.price, ceiling),
        sector=_get(name.document, "identity.sector"),
        dividend_yield=_get(name.document, "dividend.yield_percent"),
        volatility=volatility,
        pct_below_high=_metric(by_rule, "ST-SEL-12", "pct_below_two_year_high"),
        earnings_date=_metric(by_rule, "ST-ENT-05", "next_earnings_date"),
        thesis_backed=bool(thesis is not None and thesis.verdict is Verdict.PASS),
        flags=_entry_flags(name),
    )


_MONITORED_HEADER = (
    "| Ticker | Score | Price | Sector | Div | Vol† | Chart | Earnings | Flags |\n"
    "|---|---|---|---|---|---|---|---|---|"
)


def _delta_text(entry: MonitoredEntry) -> str:
    if entry.is_new:
        return " **NEW**"
    if entry.delta is None:
        return ""
    if abs(entry.delta) < 0.5:
        return " —"
    return f" {'↑' if entry.delta > 0 else '↓'}{abs(entry.delta):.0f}"


def _monitored_row(entry: MonitoredEntry) -> str:
    price = _money(entry.price) if entry.price is not None else "—"
    div = f"{entry.dividend_yield:.2f}%" if entry.dividend_yield is not None else "—"
    vol = f"{entry.volatility:.0%}†" if entry.volatility is not None else "—"
    chart = (
        f"{abs(entry.pct_below_high):.0%} below"
        if entry.pct_below_high is not None
        else "—"
    )
    marker = "**" if entry.thesis_backed else ""
    return (
        f"| {marker}{entry.ticker}{marker} | {entry.score:.0f}{_delta_text(entry)} "
        f"| {price} | {entry.sector or '—'} | {div} | {vol} | {chart} "
        f"| {entry.earnings_date or '—'} | {', '.join(entry.flags) or '—'} |"
    )


def render_week_report(
    *,
    run_date: date,
    net_liq: float,
    per_name_cap: float,
    scored: Sequence["ScoredName"],
    cross_results: Sequence[RuleResult],
    position_rows: Sequence[Mapping[str, Any]],
    missing: Sequence[tuple[str, str]],
    weights: Mapping[str, float],
    monitored_settings: MonitoredConfig | None = None,
    prior_monitored: Mapping[str, Any] | None = None,
    run_manifest: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, list[MonitoredEntry]]]:
    """Render the weekly report; also return the monitored tier for the sidecar."""

    settings = monitored_settings or MonitoredConfig(60.0, 5, 25)
    manifest = run_manifest or {}
    ceiling = zone_ceiling(net_liq, per_name_cap)
    positions = open_positions(position_rows)
    capacity = assignment_capacity(positions, net_liq)

    buckets: dict[str, list[ScoredName]] = {
        "candidate": [],
        "thesis_required": [],
        "rejected": [],
        "unevaluable": [],
    }
    for name in scored:
        buckets[classify(name.results)].append(name)

    # The monitored tier spans everything that cleared fitness, thesis-backed
    # or not; the thesis gate decides sort order, not membership.
    eligible = buckets["candidate"] + buckets["thesis_required"]
    scores = {n.ticker: composite_score(n.results, weights) for n in eligible}
    entries = [
        build_monitored_entry(name, score=scores[name.ticker], ceiling=ceiling)
        for name in eligible
        if scores[name.ticker] is not None
    ]
    entries = apply_movement(entries, prior_monitored)
    kept, overflow = select_monitored(entries, settings)

    ranked = _sort_ranked(
        [(n, scores[n.ticker]) for n in buckets["candidate"]]
    )
    in_zone_rows = [(n, c) for n, c in ranked if in_zone(n.price, ceiling)]
    out_zone_rows = [(n, c) for n, c in ranked if not in_zone(n.price, ceiling)]

    lines: list[str] = []

    # ---- 1. Header -------------------------------------------------------
    lines.append(f"# Wheel screen — {run_date.isoformat()}")
    lines.append("")
    if manifest.get("universe_stale_warning"):
        lines.append(f"> ⚠ {manifest['universe_stale_warning']}")
        lines.append("")
    lines.append(
        f"- Account: net liq {_money(net_liq)} · per-name cap "
        f"{per_name_cap:.0%} · **zone ceiling {_money(ceiling)}** "
        "(Constitution §2.3 / AL-SEL-02)"
    )
    reserve = capacity["reserve_fraction"]
    lines.append(
        f"- Reserve: {reserve:.0%} of net liq uncommitted — "
        f"{'meets' if reserve >= 0.50 else '**BREACHES**'} the ≥50% floor "
        f"(Constitution §1.3) · open positions: {len(positions)}"
    )
    funnel = []
    if manifest.get("universe_size"):
        funnel.append(f"universe {manifest['universe_size']}")
    if manifest.get("stage1_survivors") is not None:
        funnel.append(f"stage 1 {manifest['stage1_survivors']}")
    funnel.append(f"stage 2 {len(scored)}")
    funnel.append(f"cleared gates {len(eligible)}")
    funnel.append(f"monitored {sum(len(v) for v in kept.values())}")
    lines.append("- Funnel: " + " → ".join(funnel))

    # Stated once, here, rather than as a rejection count for every name in the
    # universe. AL-SEL-04 is what promotes a screened name to a tradeable one,
    # so its absence is a backlog, not a verdict.
    thesis_backed = sum(1 for name in eligible if _is_thesis_backed(name))
    lines.append(
        f"- Thesis notes: {thesis_backed} of {len(eligible)} gate-cleared "
        f"{_plural(len(eligible), 'name')}. Write `notes/<TICKER>.md` to "
        "promote one (AL-SEL-04)."
    )
    lines.append("")

    # ---- 2. Monitored ----------------------------------------------------
    lines.append(f"## Monitored (score ≥ {settings.floor_score:.0f})")
    lines.append("")
    if any(kept.values()):
        lines.append(
            "The working watchlist ST-SEL-07 asks for, produced by the screen "
            "rather than fed into it. **Bold** names have a thesis note and "
            "sort first; the rest are candidates worth writing one for."
        )
        for zone in sorted(kept, key=zone_order):
            if not kept[zone]:
                continue
            if zone == "Zone 1":
                heading = f"{zone} — tradeable now (≤ {_money(ceiling)})"
            elif zone == BEYOND_ZONE:
                heading = f"{zone} — locked (AL-SEL-03)"
            else:
                unlock = unlock_net_liq(
                    min(
                        (e.price for e in kept[zone] if e.price is not None),
                        default=0.0,
                    ),
                    per_name_cap,
                )
                heading = (
                    f"{zone} — locked (AL-SEL-03); nearest unlocks at "
                    f"~{_money(unlock)}"
                )
            lines.append("")
            lines.append(f"### {heading}")
            lines.append("")
            lines.append(_MONITORED_HEADER)
            for entry in kept[zone]:
                lines.append(_monitored_row(entry))
            if overflow.get(zone):
                lines.append("")
                lines.append(f"*…and {overflow[zone]} more in this zone.*")
    else:
        lines.append(
            f"No name scored at or above {settings.floor_score:.0f} this week."
        )

    exits = find_exits(
        [e for entries in kept.values() for e in entries],
        prior_monitored,
        scored_now={
            ticker: value for ticker, value in scores.items() if value is not None
        },
        rejected_now={
            name.ticker: "; ".join(
                r.rule_id for r in name.results if r.disqualifying
            )
            for name in buckets["rejected"]
        },
    )
    if exits:
        lines.append("")
        lines.append("**Exits since last week**")
        for exit_row in exits:
            lines.append(f"- {exit_row['ticker']} — {exit_row['reason']}")
    lines.append("")

    # ---- 3. Ranked candidates -------------------------------------------
    lines.append("## Ranked candidates (thesis-backed, all gates cleared)")
    lines.append("")
    if in_zone_rows:
        lines.append(_CANDIDATE_HEADER)
        for position_index, (name, composite) in enumerate(in_zone_rows, 1):
            lines.append(_candidate_row(str(position_index), name, composite, "in"))
    else:
        lines.append("No in-zone candidates cleared every gate this week.")
    if out_zone_rows:
        lines.append("")
        lines.append(
            "**Out of zone — displayed but locked (AL-SEL-03).** Entry "
            "requires an explicit override with a logged prediction."
        )
        lines.append("")
        lines.append(_CANDIDATE_HEADER)
        for name, composite in out_zone_rows:
            price = name.price or 0.0
            zone_text = (
                f"locked — if assigned {price * 100.0 / net_liq:.0%} of net "
                f"liq; unlocks at ~{_money(unlock_net_liq(price, per_name_cap))}"
            )
            lines.append(_candidate_row("·", name, composite, zone_text))
    lines.append("")

    # ---- 4. Portfolio context -------------------------------------------
    lines.append("## Portfolio context")
    lines.append("")
    exposure = sector_exposure(positions)
    if exposure:
        exposure_text = " · ".join(
            f"{sector} {fraction:.0%}" for sector, fraction in exposure.items()
        )
        breach = any(fraction > 0.50 for fraction in exposure.values())
        lines.append(
            f"- Sector exposure of deployed collateral: {exposure_text}"
            + (" — **exceeds the 50% sector ceiling (AL-SIZ-02)**" if breach else "")
        )
    else:
        lines.append("- Sector exposure: no open positions recorded.")
    for result in cross_results:
        marker = "⚠ " if result.verdict is Verdict.FLAG else ""
        lines.append(f"- {marker}{result.rule_id}: {result.reason}")
    lines.append(
        f"- Assignment capacity (AL-CSH-02): if everything assigned, "
        f"{_money(capacity['needed'])} needed vs {_money(capacity['available'])} "
        "available."
    )
    lines.append("")

    # ---- 5. Flagged / rejected ------------------------------------------
    lines.append("## Flagged / rejected")
    lines.append("")

    # Only the split flag is listed by name. It is the one verdict where the
    # data cannot decide: a write-down with cash still coming in and a business
    # that has stopped converting profit look identical until someone reads the
    # filing. Everything else is a number in a column.
    split_flagged = [
        (name, result)
        for name in eligible
        for result in name.results
        if result.rule_id == "ST-SEL-01" and result.verdict is Verdict.FLAG
    ]
    if split_flagged:
        total = len(split_flagged)
        lines.append(
            f"**ST-SEL-01 split — {total} {_plural(total, 'name')} needing a "
            "human.** Net income and operating cash flow disagree in sign; "
            "the rule cannot tell a one-time charge from a failing business:"
        )
        for name, result in sorted(split_flagged, key=lambda pair: pair[0].ticker)[
            : SPLIT_FLAG_LISTING_CAP
        ]:
            lines.append(f"- **{name.ticker}** — {result.reason}")
        if total > SPLIT_FLAG_LISTING_CAP:
            lines.append(f"- …and {total - SPLIT_FLAG_LISTING_CAP} more.")
        lines.append("")

    # AL-SEL-04 is excluded on purpose. It is a promotion gate, not a fitness
    # gate: with no thesis notes written it is true of every name in the
    # universe, so counting it reported "100 rejected — no thesis note" for a
    # reason that rejected nobody. The header's thesis line says it once.
    rejection_counts: dict[str, int] = {}
    for name in buckets["rejected"]:
        for result in name.results:
            if result.disqualifying and result.rule_id != THESIS_RULE:
                rejection_counts[result.rule_id] = (
                    rejection_counts.get(result.rule_id, 0) + 1
                )
    if rejection_counts:
        blurbs = {
            "ST-SEL-01": "net income and cash flow both negative",
            "ST-SEL-04": "price below the $10 floor",
            "ST-SEL-10": "volatility above the 80% ceiling",
        }
        total = len(buckets["rejected"])
        lines.append(
            f"**Rejected — {total} {_plural(total, 'name')}, by gate.** "
            "A name failing several gates is counted under each:"
        )
        for rule_id, count in sorted(rejection_counts.items()):
            lines.append(
                f"- {rule_id}: {count} {_plural(count, 'name')}"
                + (f" — {blurbs[rule_id]}" if rule_id in blurbs else "")
            )
        lines.append("")

    if buckets["unevaluable"]:
        count = len(buckets["unevaluable"])
        lines.append(
            f"**Could not evaluate — {count} {_plural(count, 'name')}** "
            "(fail-closed, not scored):"
        )
        counts: dict[str, int] = {}
        for name in buckets["unevaluable"]:
            for result in name.results:
                if result.verdict is Verdict.CANNOT_EVALUATE:
                    counts[result.rule_id] = counts.get(result.rule_id, 0) + 1
        for rule_id, count in sorted(counts.items()):
            lines.append(f"- {rule_id}: {count} {_plural(count, 'name')}")
        lines.append("")

    if missing:
        lines.append(f"**Unusable snapshots — {len(missing)}:**")
        for ticker, reason in sorted(missing)[:10]:
            lines.append(f"- **{ticker}** — {reason}")
        if len(missing) > 10:
            lines.append(f"- …and {len(missing) - 10} more.")
        lines.append("")

    if not (
        split_flagged or rejection_counts or buckets["unevaluable"] or missing
    ):
        lines.append("None.")
        lines.append("")

    lines.append(
        "† Volatility is the 30-day realized proxy, not implied volatility "
        "(no live IV feed at Layer 0). Chart stability shares the same "
        "limitation. Verdicts on these rules are approximations by "
        "construction."
    )
    lines.append("")
    lines.append(
        "*Screen output proposes; the operator decides. Nothing here is an "
        "instruction to trade.*"
    )
    lines.append("")
    return "\n".join(lines), kept
