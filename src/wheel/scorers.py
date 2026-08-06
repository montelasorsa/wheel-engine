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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from numbers import Real
from typing import Any, Mapping

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
    """What a rule concluded about one name."""

    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    CANNOT_EVALUATE = "cannot_evaluate"


class RuleKind(str, Enum):
    """How a verdict is used. Gates disqualify; scores rank; flags inform."""

    GATE = "gate"
    SCORE = "score"
    FLAG = "flag"


@dataclass(frozen=True)
class RuleResult:
    """One rule's auditable verdict on one snapshot."""

    rule_id: str
    kind: RuleKind
    verdict: Verdict
    reason: str
    metrics: Mapping[str, float | int | bool | str | None] = field(
        default_factory=dict
    )
    is_approximation: bool = False
    approximation_note: str | None = None

    @property
    def disqualifying(self) -> bool:
        """True only when a gate actually failed.

        NOT_APPLICABLE and CANNOT_EVALUATE are deliberately not disqualifying
        here: the first is a rule that does not govern this name, the second is
        a data gap. Both are surfaced to the operator by the caller rather than
        silently collapsed into a rejection.
        """

        return self.kind is RuleKind.GATE and self.verdict is Verdict.FAIL


@dataclass(frozen=True)
class SelectionThresholds:
    """Operator-configured numbers the selection rules compare against."""

    min_ttm_net_income: float
    min_operating_cash_flow: float
    min_price: float
    max_implied_volatility: float


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
        # ST-SEL-10: "materially above ~50%" is a rejection signal.
        max_implied_volatility=float(
            thresholds["iv_proxy"]["high_vol_penalty_above"]
        ),
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


def evaluate_st_sel_01(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> RuleResult:
    """ST-SEL-01 -- profitable company with solid cash flow.

    Assignment may become a multi-month hold; fundamental solvency is what
    makes waiting survivable. Both measures must be positive.
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
    observed = {
        "net_income_ttm": net_income,
        "operating_cash_flow_ttm": cash_flow,
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
        )

    failures = []
    if not income_ok:
        failures.append(f"net income {_money(net_income)} is not positive")
    if not cash_ok:
        failures.append(f"operating cash flow {_money(cash_flow)} is not positive")
    return RuleResult(
        rule_id="ST-SEL-01",
        kind=RuleKind.GATE,
        verdict=Verdict.FAIL,
        reason="; ".join(failures) + ".",
        metrics=observed,
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

    passed = measure <= thresholds.max_implied_volatility
    return RuleResult(
        rule_id="ST-SEL-10",
        kind=RuleKind.GATE,
        verdict=Verdict.PASS if passed else Verdict.FAIL,
        reason=(
            f"{source.capitalize()} {measure:.2%} "
            f"{'is at or below' if passed else 'exceeds'} the "
            f"{thresholds.max_implied_volatility:.2%} ceiling"
            + (" (measured on a proxy)." if is_proxy else ".")
        ),
        metrics={
            "implied_volatility": implied,
            "realized_vol_30d": realized,
            "measure_used": source,
        },
        is_approximation=is_proxy,
        approximation_note=IV_PROXY_NOTE if is_proxy else None,
    )


HARD_GATES = (
    evaluate_st_sel_01,
    evaluate_st_sel_04,
    evaluate_st_sel_10,
)


def evaluate_hard_gates(
    snapshot: Mapping[str, Any],
    thresholds: SelectionThresholds,
) -> tuple[RuleResult, ...]:
    """Run every ported hard gate against one snapshot, in rule order."""

    return tuple(gate(snapshot, thresholds) for gate in HARD_GATES)


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
