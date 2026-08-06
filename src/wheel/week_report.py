"""The weekly screen report: pure functions from scored snapshots to markdown.

Everything here is a pure function of (documents, rule results, positions,
account config). No clock, no filesystem, no network -- `screen.py` owns the
edges. The report never recomputes a verdict; it renders what the scorers said,
so it can never disagree with them.

Five sections, per the build order (§5.4): header, thesis-required, ranked
candidates, portfolio context, flagged/rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence

from .scorers import RuleResult, Verdict
from .snapshot_schema import resolve_field

# The three fitness gates; AL-SEL-04 (thesis) is deliberately separate so a
# fresh universe reads "worth writing theses for", not "466 rejections".
FITNESS_GATE_RULES = ("ST-SEL-01", "ST-SEL-04", "ST-SEL-10")
THESIS_RULE = "AL-SEL-04"

# Composite weights map config keys to the rules that carry them. Rules that
# returned NOT_APPLICABLE or CANNOT_EVALUATE are excluded and the remaining
# weights renormalized -- an ETF is ranked on what applies to it, not punished
# for what does not (§4.4).
COMPOSITE_WEIGHT_KEYS: Mapping[str, str] = {
    "ST-SEL-05": "stability",
    "ST-SEL-10": "iv_proxy_quality",
    "ST-SEL-12": "chart_position",
    "ST-SEL-06": "dividend",
    "ST-SEL-02": "analyst_strength",
}
_VERDICT_POINTS = {Verdict.PASS: 100.0, Verdict.FLAG: 50.0, Verdict.FAIL: 0.0}


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
    """Weighted 0-100 composite over the rules that actually applied."""

    by_rule = _by_rule(results)
    total_weight = 0.0
    total = 0.0
    for rule_id, weight_key in COMPOSITE_WEIGHT_KEYS.items():
        result = by_rule.get(rule_id)
        if result is None or result.verdict not in _VERDICT_POINTS:
            continue
        weight = float(weights[weight_key])
        total += _VERDICT_POINTS[result.verdict] * weight
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


def _vol_cell(by_rule: Mapping[str, RuleResult]) -> str:
    result = by_rule.get("ST-SEL-10")
    if result is None:
        return "—"
    vol = result.metrics.get("implied_volatility")
    if vol is None:
        vol = result.metrics.get("realized_vol_30d")
    if vol is None:
        return "—"
    text = f"{float(vol):.0%}†"
    return f"⚠ {text}" if result.verdict is Verdict.FLAG else text

def _high_cell(by_rule: Mapping[str, RuleResult]) -> str:
    result = by_rule.get("ST-SEL-12")
    if result is None:
        return "—"
    below = result.metrics.get("pct_below_two_year_high")
    if below is None:
        return "—"
    text = f"{float(below):.0%} below 2y high"
    return f"⚠ {text}" if result.verdict is Verdict.FLAG else text


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


def render_week_report(
    *,
    run_date: date,
    net_liq: float,
    per_name_cap: float,
    scored: Sequence[ScoredName],
    cross_results: Sequence[RuleResult],
    position_rows: Sequence[Mapping[str, Any]],
    missing: Sequence[tuple[str, str]],
    weights: Mapping[str, float],
) -> str:
    """Render the five-section weekly report as markdown."""

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

    ranked = _sort_ranked(
        [(n, composite_score(n.results, weights)) for n in buckets["candidate"]]
    )
    in_zone_rows = [(n, c) for n, c in ranked if in_zone(n.price, ceiling)]
    out_zone_rows = [(n, c) for n, c in ranked if not in_zone(n.price, ceiling)]

    lines: list[str] = []

    # ---- 1. Header -------------------------------------------------------
    lines.append(f"# Wheel screen — {run_date.isoformat()}")
    lines.append("")
    lines.append(
        f"- Account: net liq {_money(net_liq)} · per-name cap "
        f"{per_name_cap:.0%} · **zone ceiling {_money(ceiling)}** "
        "(Constitution §2.3 / AL-SEL-02)"
    )
    reserve = capacity["reserve_fraction"]
    reserve_note = "meets" if reserve >= 0.50 else "**BREACHES**"
    lines.append(
        f"- Reserve: {reserve:.0%} of net liq uncommitted — {reserve_note} "
        "the ≥50% floor (Constitution §1.3) · open positions: "
        f"{len(positions)}"
    )
    lines.append(
        f"- Screened {len(scored)} of {len(scored) + len(missing)} watchlist "
        f"names; {len(missing)} missing (see final section)"
    )
    lines.append("")

    # ---- 2. Thesis required ---------------------------------------------
    lines.append("## Thesis required (AL-SEL-04)")
    lines.append("")
    if buckets["thesis_required"]:
        lines.append(
            "Cleared every fitness filter; not tradeable until a thesis note "
            "exists. These are the names worth writing theses for."
        )
        lines.append("")
        lines.append("| Ticker | Score | Price | Sector | Write |")
        lines.append("|---|---|---|---|---|")
        for name, composite in _sort_ranked(
            [
                (n, composite_score(n.results, weights))
                for n in buckets["thesis_required"]
            ]
        ):
            price = _money(name.price) if name.price is not None else "—"
            sector = _get(name.document, "identity.sector") or "—"
            composite_text = "—" if composite is None else f"{composite:.0f}"
            lines.append(
                f"| {name.ticker} | {composite_text} | {price} | {sector} "
                f"| `notes/{name.ticker}.md` |"
            )
    else:
        lines.append("None — every fitness-cleared name has a thesis note.")
    lines.append("")

    # ---- 3. Ranked candidates -------------------------------------------
    lines.append("## Ranked candidates")
    lines.append("")
    if in_zone_rows:
        lines.append(_CANDIDATE_HEADER)
        for position_index, (name, composite) in enumerate(in_zone_rows, 1):
            lines.append(
                _candidate_row(str(position_index), name, composite, "in")
            )
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
    empty = True
    if buckets["rejected"]:
        empty = False
        lines.append("**Failed a fitness gate:**")
        for name in sorted(buckets["rejected"], key=lambda n: n.ticker):
            reasons = [
                f"{r.rule_id}: {r.reason}"
                for r in name.results
                if r.rule_id in FITNESS_GATE_RULES and r.verdict is Verdict.FAIL
            ]
            lines.append(f"- **{name.ticker}** — " + " ".join(reasons))
    if buckets["unevaluable"]:
        empty = False
        lines.append("**Could not evaluate (fail-closed, not scored):**")
        for name in sorted(buckets["unevaluable"], key=lambda n: n.ticker):
            reasons = [
                f"{r.rule_id}: {r.reason}"
                for r in name.results
                if r.verdict is Verdict.CANNOT_EVALUATE
            ]
            lines.append(f"- **{name.ticker}** — " + " ".join(reasons))
    if missing:
        empty = False
        lines.append("**No snapshot this run:**")
        for ticker, reason in sorted(missing):
            lines.append(f"- **{ticker}** — {reason}")
    if empty:
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
    return "\n".join(lines)
