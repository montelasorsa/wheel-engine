"""Layer 1 scorers: rule-mapped verdicts computed from a Layer 0 snapshot.

Each scorer is a pure function of (snapshot, thresholds) returning one
`RuleResult` carrying the Source Brief rule ID it implements. Nothing here
fetches, and nothing here decides — a scorer reports what a rule says about a
name, and the operator decides what to do about it (AGENTS.md §4).

These read the JSON snapshot contract in `snapshot_schema.py`, not the older
in-memory `TickerSnapshot`. `gates.py` still implements ST-SEL-01/02/03/04
against that older shape; as rules are ported here, the `gates.py` equivalent
becomes dead and moves to `legacy/`. Until the port is complete both exist, and
`pipeline.py` still calls the old path -- do not wire these in mid-port.

## Four verdicts, not two

A pass/fail boolean cannot express what the rules actually require:

- `PASS` / `FAIL` -- the rule applied and was answered.
- `NOT_APPLICABLE` -- the rule does not govern this instrument. ST-SEL-08 admits
  ETFs as valid candidates, and an ETF has no net income. Scoring that as a
  FAIL would reject the entire instrument class the rule exists to permit.
- `CANNOT_EVALUATE` -- the rule applies but the data is absent. Distinct from
  FAIL: a missing field is a data problem, not a judgment about the name.
  Callers fail closed (never treat it as a pass), but they report it honestly.

## Verdicts gate; scores rank

A verdict answers whether a rule was satisfied. It cannot answer *how well*,
and at universe scale that difference is the whole game: on the 2026-08-11 run
the five scoring rules produced only ~30 distinct composites across 1,285
names, with 255 tied at exactly 100. Ties broke alphabetically, so the
operator's "top 5" was the alphabetically-first five of 111 equal names.

So a `RuleResult` now carries an optional continuous `score` (0-100) alongside
its verdict. Gates stay strictly binary -- ST-SEL-01 both-negative, ST-SEL-04
below the floor, ST-SEL-10 above the ceiling still reject outright. Everything
that *ranks* is a curve, expressed as a `piecewise` anchor table so the shape is
readable and tunable in one place rather than buried in arithmetic.

The score stays attached to its rule ID for the same reason the verdict does:
§2 says a recommendation that cannot be mapped to a rule ID is a bug, and that
applies to a number as much as to a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from numbers import Real
from typing import Any, Mapping, Sequence

from .snapshot_schema import resolve_field

# ST-SEL-08: instrument classes with no company fundamentals behind them.
# Yahoo's `quoteType` vocabulary; compared case-insensitively.
FUNDAMENTAL_FREE_QUOTE_TYPES = frozenset({"ETF", "MUTUALFUND", "INDEX", "CURRENCY"})

IV_PROXY_NOTE = (
    "APPROXIMATION: no live IV feed exists at Layer 0, so 30-day annualized "
    "realized volatility stands in for implied volatility. ST-SEL-10's "
    "direction is correct on the proxy; its precision is not."
)


class Verdict(str, Enum):
    """What a rule concluded about one name.

    FLAG is the fifth, and after the move to continuous scoring it is reserved
    for the genuinely binary things an operator must *read*, not merely weigh:
    ST-SEL-01's net-income/cash-flow split, where a write-down and a failing
    business look identical until someone checks, and ST-ENT-05's earnings
    proximity, which is a do-not-open-across-it fact rather than a quantity.

    Graduated concerns are no longer flags. ST-SEL-10's 50-80% band and
    ST-SEL-12's near-high band both became curve segments, because at universe
    scale a flag that fires on 42% of names has stopped carrying information.
    """

    PASS = "pass"
    FAIL = "fail"
    FLAG = "flag"
    NOT_APPLICABLE = "not_applicable"
    CANNOT_EVALUATE = "cannot_evaluate"


class RuleKind(str, Enum):
    """How a verdict is used. Gates disqualify; scores rank; flags inform."""

    GATE = "gate"
    SCORE = "score"
    FLAG = "flag"


@dataclass(frozen=True)
class RuleResult:
    """One rule's auditable verdict on one snapshot, and how strongly.

    `score` is 0-100 and present only on rules that rank. None means "this rule
    contributes no ranking signal for this name" -- either it is a pure gate, or
    the data it needs is absent, or it does not govern this instrument. The
    composite excludes those and renormalizes the remaining weights (§4.4),
    which is why None and 0.0 must never be conflated: 0.0 is a name that scored
    worst, None is a name the rule cannot speak about.
    """

    rule_id: str
    kind: RuleKind
    verdict: Verdict
    reason: str
    metrics: Mapping[str, float | int | bool | str | None] = field(
        default_factory=dict
    )
    is_approximation: bool = False
    approximation_note: str | None = None
    score: float | None = None

    @property
    def disqualifying(self) -> bool:
        """True only when a gate actually failed.

        NOT_APPLICABLE and CANNOT_EVALUATE are deliberately not disqualifying
        here: the first is a rule that does not govern this name, the second is
        a data gap. Both are surfaced to the operator by the caller rather than
        silently collapsed into a rejection.
        """

        return self.kind is RuleKind.GATE and self.verdict is Verdict.FAIL


# ST-SEL-10's disqualifying ceiling. The Source Brief calls IV "materially
# above ~50%" a rejection signal; 80% is where that is unambiguous on any
# measure, which matters because this fires on a realized-vol proxy. The 50%
# line is no longer a verdict boundary -- it survives as an anchor on the
# volatility curve below, where it shapes the ranking instead of splitting it.
IV_DISQUALIFY_ABOVE = 0.80

# AL-SEL-06: "mid-cap or above at pilot scale". Mid-cap conventionally starts
# at $2B.
MIN_MARKET_CAP = 2_000_000_000.0

# ---------------------------------------------------------------------------
# Continuous score curves
#
# Each table is (input, score) anchors, ascending by input, interpolated
# linearly between and clamped outside. Written as tables rather than formulas
# because the shapes are deliberately not straight lines and the anchor points
# are the argument -- a reader can check them against the Source Brief without
# solving for a slope.
# ---------------------------------------------------------------------------

# ST-SEL-10. Lower volatility ranks higher: the methodology's most
# counterintuitive rule is that fat premium prices the one failure mode the
# strategy cannot survive. Steeper above 50% than below it, so the warning band
# still costs a name real ground without rejecting it.
VOLATILITY_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.10, 100.0),
    (0.50, 50.0),
    (0.79, 1.0),
)

# ST-SEL-12. Distance below the two-year high, rewarded steeply near the high
# and flattening out: the difference between 10% and 20% below is a materially
# different entry, the difference between 40% and 50% is not.
CHART_POSITION_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.00, 0.0),
    (0.10, 40.0),
    (0.20, 70.0),
    (0.40, 100.0),
)

# ST-SEL-01, scored rather than merely gated: "profitable company with solid
# cash flow" is a question of degree once the gate has answered the question of
# sign. Operating cash flow as a share of revenue.
#
# The anchors are the empirical percentile curve of the 2026-08-11 universe
# (p10 0.05, p25 0.108, median 0.188, p75 0.320, p90 0.479), frozen as
# constants. That gives a percentile's shape -- a score means "better than
# roughly this share of the market" -- without a percentile's cohort
# dependence. A live percentile would move a name's score because *other* names
# were screened, which would make week-over-week deltas meaningless.
CASH_FLOW_MARGIN_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.00, 0.0),
    (0.05, 10.0),
    (0.108, 25.0),
    (0.188, 50.0),
    (0.320, 75.0),
    (0.479, 90.0),
    (0.70, 100.0),
)

# ST-SEL-06. Dividend is "preferred, not required", so this is the component
# whose weight does the capping: a non-payer scores 0 here and is still a
# perfectly good candidate on the other four.
DIVIDEND_YIELD_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (5.0, 100.0),
)

# ST-SEL-02, on Yahoo's 1-5 recommendation mean where 1 is strong buy.
# Interpolating rather than bucketing costs nothing and avoids reintroducing
# the coarseness this whole scheme exists to remove.
ANALYST_RATING_ANCHORS: tuple[tuple[float, float], ...] = (
    (1.0, 100.0),
    (2.0, 75.0),
    (3.0, 25.0),
    (5.0, 0.0),
)


def piecewise(
    value: float,
    anchors: Sequence[tuple[float, float]],
) -> float:
    """Linearly interpolate `value` through an ascending anchor table.

    Clamps to the end anchors' scores outside the table's range: a name at 5%
    volatility is not better than 100, and one at 90% has already failed the
    gate. Pure, total, and independent of every other name being scored.
    """

    if not anchors:
        raise ValueError("piecewise needs at least one anchor")
    if value <= anchors[0][0]:
        return anchors[0][1]
    for (low_input, low_score), (high_input, high_score) in zip(
        anchors, anchors[1:]
    ):
        if value <= high_input:
            span = high_input - low_input
            if span <= 0:
                return high_score
            fraction = (value - low_input) / span
            return low_score + fraction * (high_score - low_score)
    return anchors[-1][1]

# AL-SIZ-04: "two or more open or candidate positions reporting in the same week".
EARNINGS_CLUSTER_MINIMUM = 2

ST_SEL_05_NOTE = (
    "APPROXIMATION: chart stability is measured from realized history -- the "
    "largest single-day move and annualized volatility over the past year. "
    "ST-SEL-05 also names moves driven by executive social media, which no "
    "price series can detect. Absence of a historical gap is not evidence "
    "that single-personality risk is absent."
)


@dataclass(frozen=True)
class SelectionThresholds:
    """Operator-configured numbers the selection rules compare against."""

    min_ttm_net_income: float
    min_operating_cash_flow: float
    min_price: float
    max_price: float
    max_mean_rating: float
    max_single_day_move: float
    iv_disqualify_above: float = IV_DISQUALIFY_ABOVE
    min_market_cap: float = MIN_MARKET_CAP
    earnings_flag_days: int = 45


def selection_thresholds_from_config(
    config: Mapping[str, Any],
) -> SelectionThresholds:
    """Purely extract the selection thresholds from parsed YAML."""

    thresholds = config["thresholds"]
    return SelectionThresholds(
        min_ttm_net_income=float(thresholds["profitability"]["min_ttm_net_income"]),
        min_operating_cash_flow=float(
            thresholds["profitability"]["min_operating_cash_flow"]
        ),
        min_price=float(thresholds["price"]["min_usd"]),
        max_price=float(thresholds["price"]["max_usd"]),
        max_mean_rating=float(thresholds["analyst"]["max_mean_rating"]),
        max_single_day_move=float(thresholds["stability"]["max_single_day_move"]),
        earnings_flag_days=int(thresholds["earnings"]["flag_within_days"]),
    )


def _number(value: object) -> float | None:
    """Coerce to a finite float, or None. Booleans are never numbers here."""

    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _get(snapshot: Mapping[str, Any], dotted: str) -> Any:
    """Read a contract field, treating an absent key as an absent value.

    The schema validator is what enforces presence. A scorer handed an
    unvalidated document should report CANNOT_EVALUATE, not raise.
    """

    try:
        return resolve_field(snapshot, dotted)
    except KeyError:
        return None


def _money(value: float) -> str:
    if abs(value) >= 1e9:
        return f"${value / 1e9:,.2f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:,.1f}M"
    return f"${value:,.2f}"


def has_company_fundamentals(snapshot: Mapping[str, Any]) -> bool:
    """False for ETFs and other instruments with no issuer behind them.

    ST-SEL-08. An unknown or missing quote_type is treated as an equity: the
    conservative reading, since it keeps the fundamental gates applying rather
    than waiving them on a name we failed to classify.
    """

    quote_type = _get(snapshot, "identity.quote_type")
    if not isinstance(quote_type, str):
        return True
    return quote_type.strip().upper() not in FUNDAMENTAL_FREE_QUOTE_TYPES


def _instrument_label(snapshot: Mapping[str, Any]) -> str:
    quote_type = _get(snapshot, "identity.quote_type")
    return quote_type.strip().upper() if isinstance(quote_type, str) else "unknown"


# --------------------------------------------------------------------------
# Hard gates
# --------------------------------------------------------------------------


def cash_flow_strength(snapshot: Mapping[str, Any]) -> float | None:
    """ST-SEL-01's ranking half: operating cash flow as a share of revenue.

    The gate answers *is it positive*; this answers *how solid*, which is the
    other half of the same eight-word rule. A business converting 40% of revenue
    to operating cash is a materially better multi-month hold than one
    converting 3%, and before this the two scored identically.

    None -- never 0.0 -- when revenue is missing or non-positive. A name whose
    denominator is unknown has no margin, which is not the same as a bad one.
    """

    cash_flow = _number(_get(snapshot, "fundamentals.operating_cash_flow_ttm"))
    revenue = _number(_get(snapshot, "fundamentals.revenue_ttm"))
    if cash_flow is None or revenue is None or revenue <= 0:
        return None
    return piecewise(cash_flow / revenue, CASH_FLOW_MARGIN_ANCHORS)


def evaluate_st_sel_01(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-01 -- profitable company with solid cash flow.

    Assignment may become a multi-month hold; fundamental solvency is what
    makes waiting survivable. Both measures must be positive to clear the gate,
    and `cash_flow_strength` ranks the survivors by how far past positive they
    are.
    """

    if not has_company_fundamentals(snapshot):
        # ST-SEL-08: an ETF has no net income. Absence here is the instrument
        # class, not a failing company.
        return RuleResult(
            rule_id="ST-SEL-01",
            kind=RuleKind.GATE,
            verdict=Verdict.NOT_APPLICABLE,
            reason=(
                f"Not applicable: {_instrument_label(snapshot)} has no issuer "
                "fundamentals (ST-SEL-08 admits these as valid candidates)."
            ),
            metrics={"quote_type": _get(snapshot, "identity.quote_type")},
        )

    net_income = _number(_get(snapshot, "fundamentals.net_income_ttm"))
    cash_flow = _number(_get(snapshot, "fundamentals.operating_cash_flow_ttm"))
    revenue = _number(_get(snapshot, "fundamentals.revenue_ttm"))
    strength = cash_flow_strength(snapshot)
    observed = {
        "net_income_ttm": net_income,
        "operating_cash_flow_ttm": cash_flow,
        "revenue_ttm": revenue,
        "operating_cash_flow_margin": (
            cash_flow / revenue
            if cash_flow is not None and revenue is not None and revenue > 0
            else None
        ),
    }

    missing = [
        name
        for name, value in (
            ("net_income_ttm", net_income),
            ("operating_cash_flow_ttm", cash_flow),
        )
        if value is None
    ]
    if missing:
        return RuleResult(
            rule_id="ST-SEL-01",
            kind=RuleKind.GATE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason=f"Cannot evaluate: missing {', '.join(missing)}.",
            metrics=observed,
        )

    income_ok = net_income > thresholds.min_ttm_net_income
    cash_ok = cash_flow > thresholds.min_operating_cash_flow

    # "Profitable company with solid cash flow" is two criteria, not one, so
    # one negative measure is a question rather than a verdict. Only both
    # negative is unambiguously unprofitable and disqualifying.
    if income_ok and cash_ok:
        return RuleResult(
            rule_id="ST-SEL-01",
            kind=RuleKind.GATE,
            verdict=Verdict.PASS,
            reason=(
                f"TTM net income {_money(net_income)} and operating cash flow "
                f"{_money(cash_flow)} are both positive."
            ),
            metrics=observed,
            score=strength,
        )

    if not income_ok and not cash_ok:
        return RuleResult(
            rule_id="ST-SEL-01",
            kind=RuleKind.GATE,
            verdict=Verdict.FAIL,
            reason=(
                f"net income {_money(net_income)} is not positive; operating "
                f"cash flow {_money(cash_flow)} is not positive."
            ),
            metrics=observed,
        )

    if not income_ok:
        # A write-down or one-time charge looks exactly like this. The cash
        # that funds a multi-month hold is still coming in.
        reason = (
            f"net income {_money(net_income)} is negative but operating cash "
            f"flow {_money(cash_flow)} is positive -- investigate one-time "
            "charges before treating this as unprofitable."
        )
    else:
        # The inverse and arguably the worse case: reported profit the
        # business is not converting to cash. ST-SEL-01 exists so a
        # multi-month hold is survivable, and cash is what funds survival.
        reason = (
            f"operating cash flow {_money(cash_flow)} is negative while net "
            f"income {_money(net_income)} is positive -- earnings are not "
            "cash-backed; investigate before relying on the reported profit."
        )
    return RuleResult(
        rule_id="ST-SEL-01",
        kind=RuleKind.FLAG,
        verdict=Verdict.FLAG,
        reason=reason,
        metrics=observed,
        score=strength,
    )


def evaluate_st_sel_04(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-04 -- hard floor, no sub-$10 stocks.

    Categorical, and unlike ST-SEL-03's band this floor does not scale with the
    account. It applies to every instrument class, ETFs included: the distress
    and spread concerns behind it are properties of the price, not the issuer.
    """

    price = _number(_get(snapshot, "price.current"))
    if price is None:
        return RuleResult(
            rule_id="ST-SEL-04",
            kind=RuleKind.GATE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: missing price.current.",
            metrics={"price": None},
        )

    passed = price >= thresholds.min_price
    return RuleResult(
        rule_id="ST-SEL-04",
        kind=RuleKind.GATE,
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        reason=(
            f"Price {_money(price)} {'meets' if passed else 'is below'} the "
            f"{_money(thresholds.min_price)} floor."
        ),
        metrics={"price": price},
    )


def evaluate_st_sel_10(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-10 -- high implied volatility disqualifies.

    The methodology's most counterintuitive rule: fat premium prices the one
    failure mode the strategy cannot survive, so raw IV materially above ~50%
    is a rejection signal rather than an attraction.

    Binary above 80%, continuous below it. The 50% line the Source Brief names
    is now an anchor on the curve rather than a flag boundary: between 50% and
    80% a name is worse, not suspect, and saying so with a number beats saying
    it with a warning symbol on a fifth of the universe.

    True IV does not exist at Layer 0. When `implied_volatility` is null the
    30-day realized-vol proxy is used and the result is marked as an
    approximation -- a name disqualified on the proxy must be reported as
    disqualified on a proxy, never as if IV had been measured.
    """

    implied = _number(_get(snapshot, "volatility.implied_volatility"))
    realized = _number(_get(snapshot, "volatility.realized_vol_30d"))

    if implied is not None:
        measure, source, is_proxy = implied, "implied volatility", False
    elif realized is not None:
        measure, source, is_proxy = realized, "30-day realized volatility", True
    else:
        return RuleResult(
            rule_id="ST-SEL-10",
            kind=RuleKind.GATE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason=(
                "Cannot evaluate: neither implied volatility nor the "
                "realized-volatility proxy is available."
            ),
            metrics={"implied_volatility": None, "realized_vol_30d": None},
            is_approximation=True,
            approximation_note=IV_PROXY_NOTE,
        )

    disqualified = measure > thresholds.iv_disqualify_above
    score = None if disqualified else piecewise(measure, VOLATILITY_ANCHORS)
    band = (
        f"exceeds the {thresholds.iv_disqualify_above:.0%} disqualifying ceiling"
        if disqualified
        else (
            f"is within the {thresholds.iv_disqualify_above:.0%} ceiling and "
            f"scores {score:.0f}/100 on the volatility curve"
        )
    )

    return RuleResult(
        rule_id="ST-SEL-10",
        kind=RuleKind.GATE,
        verdict=Verdict.FAIL if disqualified else Verdict.PASS,
        reason=(
            f"{source.capitalize()} {measure:.2%} {band}"
            + (" (measured on a proxy)." if is_proxy else ".")
        ),
        metrics={
            "implied_volatility": implied,
            "realized_vol_30d": realized,
            "measure_used": source,
        },
        is_approximation=is_proxy,
        approximation_note=IV_PROXY_NOTE if is_proxy else None,
        score=score,
    )


# --------------------------------------------------------------------------
# Soft scores and flags
# --------------------------------------------------------------------------


def evaluate_st_sel_08(snapshot: Mapping[str, Any]) -> RuleResult:
    """ST-SEL-08 -- lower-priced ETFs are valid candidates.

    Unlike every other rule here, this one accepts and rejects nothing. It
    reports which instrument class a name is, because that determines whether
    the issuer-dependent rules apply at all. The branch itself lives in
    `has_company_fundamentals`; this makes the classification visible in output
    so a row of NOT_APPLICABLE verdicts has a stated cause.

    ETFs trade the thinner premium for no earnings event and no single-company
    headline risk -- a different profile, not a worse one.
    """

    quote_type = _get(snapshot, "identity.quote_type")
    if not isinstance(quote_type, str) or not quote_type.strip():
        return RuleResult(
            rule_id="ST-SEL-08",
            kind=RuleKind.FLAG,
            verdict=Verdict.CANNOT_EVALUATE,
            reason=(
                "Cannot classify: identity.quote_type is absent. Treated as an "
                "equity, so the issuer-dependent rules still apply."
            ),
            metrics={"quote_type": None, "has_company_fundamentals": True},
        )

    issuer_backed = has_company_fundamentals(snapshot)
    return RuleResult(
        rule_id="ST-SEL-08",
        kind=RuleKind.FLAG,
        verdict=Verdict.PASS,
        reason=(
            f"Classified {quote_type.strip().upper()}: "
            + (
                "issuer-backed, so the fundamental rules apply."
                if issuer_backed
                else "no issuer, so ST-SEL-01/02, AL-SEL-06 and ST-ENT-05 do "
                "not apply. A valid candidate, not a rejection."
            )
        ),
        metrics={
            "quote_type": quote_type.strip().upper(),
            "has_company_fundamentals": issuer_backed,
        },
    )


def evaluate_st_sel_02(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-02 -- bullish or very bullish analyst consensus.

    A cheap filter against selecting into a deteriorating name. Scored rather
    than gated: it is a directional tailwind, not a solvency test.
    """

    if not has_company_fundamentals(snapshot):
        return RuleResult(
            rule_id="ST-SEL-02",
            kind=RuleKind.SCORE,
            verdict=Verdict.NOT_APPLICABLE,
            reason=(
                f"Not applicable: {_instrument_label(snapshot)} carries no "
                "analyst consensus (ST-SEL-08)."
            ),
            metrics={"recommendation_mean": None},
        )

    rating = _number(_get(snapshot, "analyst.recommendation_mean"))
    opinions = _number(_get(snapshot, "analyst.analyst_opinions"))
    if rating is None:
        return RuleResult(
            rule_id="ST-SEL-02",
            kind=RuleKind.SCORE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: missing analyst.recommendation_mean.",
            metrics={"recommendation_mean": None, "analyst_opinions": opinions},
        )

    # 1 = strong buy, 5 = sell: lower is stronger. The configured maximum still
    # sets the verdict for audit, but the ranking reads the curve -- "bullish or
    # very bullish" is a spectrum, and 1.4 is not the same recommendation as 2.4.
    passed = rating <= thresholds.max_mean_rating
    score = piecewise(rating, ANALYST_RATING_ANCHORS)
    return RuleResult(
        rule_id="ST-SEL-02",
        kind=RuleKind.SCORE,
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        reason=(
            f"Mean analyst rating {rating:.2f} is "
            f"{'at or below' if passed else 'above'} the "
            f"{thresholds.max_mean_rating:.2f} maximum (1=strong buy, 5=sell); "
            f"scores {score:.0f}/100."
        ),
        metrics={"recommendation_mean": rating, "analyst_opinions": opinions},
        score=score,
    )


def evaluate_st_sel_03(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-03 -- share price roughly $10-$50.

    Capital efficiency, not a quality judgment. AL-SEL-02 replaces this fixed
    band with one derived from account size, which needs `net_liq` and is
    therefore not evaluable at Layer 0 -- the configured band is an interim
    stand-in, and the reason says so.
    """

    price = _number(_get(snapshot, "price.current"))
    if price is None:
        return RuleResult(
            rule_id="ST-SEL-03",
            kind=RuleKind.SCORE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: missing price.current.",
            metrics={"price": None},
        )

    passed = thresholds.min_price <= price <= thresholds.max_price
    return RuleResult(
        rule_id="ST-SEL-03",
        kind=RuleKind.SCORE,
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        reason=(
            f"Price {_money(price)} is "
            f"{'within' if passed else 'outside'} the configured "
            f"{_money(thresholds.min_price)}-{_money(thresholds.max_price)} "
            "band (interim: AL-SEL-02's derived band needs account net_liq)."
        ),
        metrics={"price": price},
    )


def evaluate_st_sel_05(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-05 -- stable chart without violent movement.

    Gap risk is the failure mode the strategy cannot manage: rolling needs an
    orderly market, and a 30% overnight gap removes the option. Measured from
    realized history, which is a proxy in the same sense ST-SEL-10's is -- and
    a weaker one, because the rule explicitly names social-media-driven moves
    that no price series predicts.
    """

    max_move = _number(_get(snapshot, "stability.max_single_day_move_1y"))
    realized_vol = _number(_get(snapshot, "stability.realized_vol_1y"))
    observed = {"max_single_day_move_1y": max_move, "realized_vol_1y": realized_vol}

    if max_move is None:
        return RuleResult(
            rule_id="ST-SEL-05",
            kind=RuleKind.SCORE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: missing stability.max_single_day_move_1y.",
            metrics=observed,
            is_approximation=True,
            approximation_note=ST_SEL_05_NOTE,
        )

    passed = max_move <= thresholds.max_single_day_move
    return RuleResult(
        rule_id="ST-SEL-05",
        kind=RuleKind.SCORE,
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        reason=(
            f"Largest single-day move {max_move:.2%} "
            f"{'is within' if passed else 'exceeds'} the "
            f"{thresholds.max_single_day_move:.2%} limit"
            + (
                f"; annualized realized volatility {realized_vol:.2%}."
                if realized_vol is not None
                else "."
            )
        ),
        metrics=observed,
        is_approximation=True,
        approximation_note=ST_SEL_05_NOTE,
    )


def evaluate_st_sel_06(snapshot: Mapping[str, Any]) -> RuleResult:
    """ST-SEL-06 -- dividend preferred, not required.

    Never a gate: the rule says preferred. A payer scores by yield; a non-payer
    scores 0 and remains a perfectly good candidate on the other four
    components. This is the component whose *weight* does the capping -- the
    yield curve runs the full 0-100 like every other, and what stops a fat
    dividend dominating the composite is that it is one fifth of it.
    """

    pays = _get(snapshot, "dividend.pays_dividend")
    yield_percent = _number(_get(snapshot, "dividend.yield_percent"))
    if not isinstance(pays, bool):
        return RuleResult(
            rule_id="ST-SEL-06",
            kind=RuleKind.SCORE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: missing dividend.pays_dividend.",
            metrics={"pays_dividend": None, "yield_percent": yield_percent},
        )

    yield_text = (
        f"{yield_percent:.2f}%" if yield_percent is not None else "unavailable"
    )
    # A confirmed non-payer scores 0: that is an observation, not a data gap.
    # A payer whose yield is missing gets None -- the rule cannot rank it.
    if not pays:
        score = 0.0
    elif yield_percent is None:
        score = None
    else:
        score = piecewise(yield_percent, DIVIDEND_YIELD_ANCHORS)

    return RuleResult(
        rule_id="ST-SEL-06",
        kind=RuleKind.SCORE,
        verdict=Verdict.PASS if pays else Verdict.FAIL,
        reason=(
            f"{'Pays' if pays else 'Does not pay'} a dividend "
            f"(yield {yield_text}); preferred, not required"
            + (f"; scores {score:.0f}/100." if score is not None else ".")
        ),
        metrics={"pays_dividend": pays, "yield_percent": yield_percent},
        score=score,
    )


def evaluate_st_sel_12(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-12 -- do not open at or near a multi-year high.

    Entry point affects assignment probability independent of every other
    filter, which makes this a matter of degree throughout: a name 12% below
    its high is a better entry than one 3% below, and both are worse than one
    30% below. A pure gradient, with no threshold at all.

    It used to flag inside a 10% band. On the 2026-08-11 universe that fired on
    536 of 1,285 names -- with the market near highs, "near the high" is close
    to a description of the market rather than of a name, and a warning on 42%
    of candidates warns about nothing.

    Measured against the two-year high the snapshot carries. The Source Brief
    says "multi-year" and its worked example cites a three-year high, so a
    52-week window would be a narrower test than the rule describes.
    """

    below_high = _number(_get(snapshot, "chart_position.pct_below_two_year_high"))
    two_year_high = _number(_get(snapshot, "chart_position.two_year_high"))
    observed = {
        "pct_below_two_year_high": below_high,
        "two_year_high": two_year_high,
    }
    if below_high is None:
        return RuleResult(
            rule_id="ST-SEL-12",
            kind=RuleKind.SCORE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: missing chart_position.pct_below_two_year_high.",
            metrics=observed,
        )

    # A name trading at or above its two-year high yields a zero or slightly
    # negative distance; the curve clamps both to 0, the worst entry there is.
    score = piecewise(below_high, CHART_POSITION_ANCHORS)
    return RuleResult(
        rule_id="ST-SEL-12",
        kind=RuleKind.SCORE,
        verdict=Verdict.PASS,
        reason=(
            f"Price is {abs(below_high):.2%} below the two-year high, "
            f"scoring {score:.0f}/100 on the entry-point curve."
        ),
        metrics=observed,
        score=score,
    )


def evaluate_st_ent_05(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-ENT-05 -- avoid holding through earnings or other binary events.

    Flag only, never a disqualifier: an imminent earnings date does not make a
    name unsuitable, it means do not open across it.
    """

    days = _number(_get(snapshot, "earnings.days_to_earnings"))
    next_date = _get(snapshot, "earnings.next_earnings_date")
    observed = {"days_to_earnings": days, "next_earnings_date": next_date}

    if days is None:
        # An ETF has no earnings at all -- that is the absence of the event,
        # not a missing measurement.
        if not has_company_fundamentals(snapshot):
            return RuleResult(
                rule_id="ST-ENT-05",
                kind=RuleKind.FLAG,
                verdict=Verdict.NOT_APPLICABLE,
                reason=(
                    f"Not applicable: {_instrument_label(snapshot)} has no "
                    "earnings event (ST-SEL-08 notes this as an ETF advantage)."
                ),
                metrics=observed,
            )
        return RuleResult(
            rule_id="ST-ENT-05",
            kind=RuleKind.FLAG,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: no earnings date available.",
            metrics=observed,
        )

    imminent = 0 <= days < thresholds.earnings_flag_days
    return RuleResult(
        rule_id="ST-ENT-05",
        kind=RuleKind.FLAG,
        verdict=Verdict.FLAG if imminent else Verdict.PASS,
        reason=(
            f"Next earnings {next_date} is {int(days)} days out"
            + (
                f" -- inside the {thresholds.earnings_flag_days}-day window; "
                "do not open across it."
                if imminent
                else f", beyond the {thresholds.earnings_flag_days}-day window."
            )
        ),
        metrics=observed,
    )


def evaluate_al_sel_04(snapshot: Mapping[str, Any]) -> RuleResult:
    """AL-SEL-04 -- written thesis gate.

    A name is not tradeable until `notes/<TICKER>.md` exists with the business
    case and name-specific kill-switch conditions. A hard precondition by
    design: ST-SEL-09 requires willingness to own for twelve months, and an
    unwritten thesis is an unexamined one.
    """

    exists = _get(snapshot, "operator_gates.thesis_note_exists")
    path = _get(snapshot, "operator_gates.thesis_note_path")
    observed = {"thesis_note_exists": exists, "thesis_note_path": path}

    if not isinstance(exists, bool):
        return RuleResult(
            rule_id="AL-SEL-04",
            kind=RuleKind.GATE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: operator_gates.thesis_note_exists is unanswered.",
            metrics=observed,
        )

    return RuleResult(
        rule_id="AL-SEL-04",
        kind=RuleKind.GATE,
        verdict=Verdict.PASS if exists else Verdict.FAIL,
        reason=(
            f"Thesis note {path} is present."
            if exists
            else "No thesis note exists; the name is not tradeable until one does."
        ),
        metrics=observed,
    )


def evaluate_al_sel_06(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """AL-SEL-06 -- market cap is a separate filter from share price.

    Price governs sizing; market cap governs quality, liquidity and gap risk.
    Conflating them is how a screen rejects a sound $15 large-cap and accepts
    an unsound $45 micro-cap.
    """

    market_cap = _number(_get(snapshot, "identity.market_cap"))
    if market_cap is None:
        if not has_company_fundamentals(snapshot):
            return RuleResult(
                rule_id="AL-SEL-06",
                kind=RuleKind.SCORE,
                verdict=Verdict.NOT_APPLICABLE,
                reason=(
                    f"Not applicable: {_instrument_label(snapshot)} has no "
                    "issuer market cap (ST-SEL-08)."
                ),
                metrics={"market_cap": None},
            )
        return RuleResult(
            rule_id="AL-SEL-06",
            kind=RuleKind.SCORE,
            verdict=Verdict.CANNOT_EVALUATE,
            reason="Cannot evaluate: missing identity.market_cap.",
            metrics={"market_cap": None},
        )

    passed = market_cap >= thresholds.min_market_cap
    return RuleResult(
        rule_id="AL-SEL-06",
        kind=RuleKind.SCORE,
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        reason=(
            f"Market cap {_money(market_cap)} "
            f"{'meets' if passed else 'is below'} the "
            f"{_money(thresholds.min_market_cap)} mid-cap floor."
        ),
        metrics={"market_cap": market_cap},
    )


# AL-SEL-04 takes no thresholds, so gates are called explicitly rather than
# iterated over.

# ST-SEL-06 takes no thresholds, so the soft rules are called explicitly in
# `evaluate_single_ticker_rules` rather than iterated over.


def evaluate_hard_gates(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> tuple[RuleResult, ...]:
    """Run every ported hard gate against one snapshot, in rule order."""

    return (
        evaluate_st_sel_01(snapshot, thresholds),
        evaluate_st_sel_04(snapshot, thresholds),
        evaluate_st_sel_10(snapshot, thresholds),
        evaluate_al_sel_04(snapshot),
    )


def evaluate_single_ticker_rules(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> tuple[RuleResult, ...]:
    """Every rule answerable from one snapshot: gates first, then soft rules."""

    return evaluate_hard_gates(snapshot, thresholds) + (
        evaluate_st_sel_08(snapshot),
        evaluate_st_sel_02(snapshot, thresholds),
        evaluate_st_sel_03(snapshot, thresholds),
        evaluate_st_sel_05(snapshot, thresholds),
        evaluate_st_sel_06(snapshot),
        evaluate_st_sel_12(snapshot, thresholds),
        evaluate_st_ent_05(snapshot, thresholds),
        evaluate_al_sel_06(snapshot, thresholds),
    )


# --------------------------------------------------------------------------
# Cross-candidate rules
#
# These take the whole candidate set, not one snapshot: concentration and
# clustering are properties of a portfolio, invisible from any single name.
# They return one RuleResult for the set rather than per ticker, and they are
# flags -- AL-SIZ-03 is explicitly "a warning, not a block", and AL-SIZ-04 is
# "a display, not a constraint".
# --------------------------------------------------------------------------


def _grouped(
    snapshots: Sequence[Mapping[str, Any]],
    dotted: str,
) -> dict[str, list[str]]:
    """Group ticker symbols by a snapshot field, skipping null values."""

    groups: dict[str, list[str]] = {}
    for snapshot in snapshots:
        value = _get(snapshot, dotted)
        if not isinstance(value, str) or not value.strip():
            continue
        ticker = _get(snapshot, "ticker")
        groups.setdefault(value, []).append(
            ticker if isinstance(ticker, str) else "?"
        )
    return {key: sorted(names) for key, names in groups.items()}


def evaluate_al_siz_03(
    snapshots: Sequence[Mapping[str, Any]],
) -> RuleResult:
    """AL-SIZ-03 -- industry concentration is a warning, not a block.

    Two semiconductor names in different GICS sub-industries are not
    diversified in any way that matters during a semiconductor selloff. But
    sub-industry taxonomies are noisy, and a hard rule on noisy data produces
    false blocks -- so this warns and logs.
    """

    if not snapshots:
        return RuleResult(
            rule_id="AL-SIZ-03",
            kind=RuleKind.FLAG,
            verdict=Verdict.CANNOT_EVALUATE,
            reason=(
                "No thesis-backed candidates to evaluate yet. This rule is "
                "scoped to names the operator is actually considering -- "
                "thesis-backed candidates plus open positions -- because "
                "across a whole screened universe every week clusters."
            ),
            metrics={"candidates": 0},
        )

    groups = _grouped(snapshots, "identity.industry")
    repeated = {
        industry: names for industry, names in groups.items() if len(names) > 1
    }
    metrics = {
        "candidates": len(snapshots),
        "industries": len(groups),
        "concentrated_industries": len(repeated),
    }
    if not repeated:
        return RuleResult(
            rule_id="AL-SIZ-03",
            kind=RuleKind.FLAG,
            verdict=Verdict.PASS,
            reason=(
                f"No industry repeats across {len(snapshots)} candidates "
                f"({len(groups)} distinct industries)."
            ),
            metrics=metrics,
        )

    detail = "; ".join(
        f"{industry}: {', '.join(names)}"
        for industry, names in sorted(repeated.items())
    )
    return RuleResult(
        rule_id="AL-SIZ-03",
        kind=RuleKind.FLAG,
        verdict=Verdict.FLAG,
        reason=f"Industry concentration (warning, not a block) -- {detail}.",
        metrics=metrics,
    )


def evaluate_al_siz_04(
    snapshots: Sequence[Mapping[str, Any]],
) -> RuleResult:
    """AL-SIZ-04 -- flag earnings clustering.

    Two or more open or candidate positions reporting in the same week is a
    hidden correlation the sector view misses entirely: names in unrelated
    sectors reporting together still produce concentrated event risk.
    """

    if not snapshots:
        return RuleResult(
            rule_id="AL-SIZ-04",
            kind=RuleKind.FLAG,
            verdict=Verdict.CANNOT_EVALUATE,
            reason=(
                "No thesis-backed candidates to evaluate yet. This rule is "
                "scoped to names the operator is actually considering -- "
                "thesis-backed candidates plus open positions -- because "
                "across a whole screened universe every week clusters."
            ),
            metrics={"candidates": 0},
        )

    weeks = _grouped(snapshots, "earnings.earnings_week")
    clustered = {
        week: names
        for week, names in weeks.items()
        if len(names) >= EARNINGS_CLUSTER_MINIMUM
    }
    metrics = {
        "candidates": len(snapshots),
        "weeks_with_earnings": len(weeks),
        "clustered_weeks": len(clustered),
    }
    if not clustered:
        return RuleResult(
            rule_id="AL-SIZ-04",
            kind=RuleKind.FLAG,
            verdict=Verdict.PASS,
            reason=(
                f"No earnings week carries {EARNINGS_CLUSTER_MINIMUM} or more "
                f"of the {len(snapshots)} candidates."
            ),
            metrics=metrics,
        )

    detail = "; ".join(
        f"{week}: {', '.join(names)}" for week, names in sorted(clustered.items())
    )
    return RuleResult(
        rule_id="AL-SIZ-04",
        kind=RuleKind.FLAG,
        verdict=Verdict.FLAG,
        reason=f"Earnings clustering (display, not a constraint) -- {detail}.",
        metrics=metrics,
    )


CROSS_CANDIDATE_RULES = (evaluate_al_siz_03, evaluate_al_siz_04)


def evaluate_cross_candidate_rules(
    snapshots: Sequence[Mapping[str, Any]],
) -> tuple[RuleResult, ...]:
    """Run every portfolio-level rule over the candidate set."""

    return tuple(rule(snapshots) for rule in CROSS_CANDIDATE_RULES)


def disqualified_by(results: tuple[RuleResult, ...]) -> tuple[RuleResult, ...]:
    """The gate failures that actually reject a name."""

    return tuple(result for result in results if result.disqualifying)


def unevaluated(results: tuple[RuleResult, ...]) -> tuple[RuleResult, ...]:
    """Gates that could not run. Fail closed: a name here is not a candidate.

    Kept separate from `disqualified_by` so the operator can tell "this name is
    unsuitable" from "we could not tell", which are different problems with
    different fixes.
    """

    return tuple(
        result
        for result in results
        if result.kind is RuleKind.GATE and result.verdict is Verdict.CANNOT_EVALUATE
    )


def clears_hard_gates(results: tuple[RuleResult, ...]) -> bool:
    """True only when every gate either passed or did not apply.

    Fail-closed by construction: CANNOT_EVALUATE is not a pass.
    """

    return not disqualified_by(results) and not unevaluated(results)
