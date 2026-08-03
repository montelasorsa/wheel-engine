"""Pure hard-gate evaluations for Component A."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from numbers import Real
from typing import Any, Mapping

from .snapshot import TickerSnapshot


@dataclass(frozen=True)
class GateFlag:
    """A non-disqualifying signal attached to a gate result."""

    name: str
    active: bool
    reason: str


class GateFailureKind(str, Enum):
    """Why a hard gate failed."""

    FITNESS = "fitness"
    MISSING_DATA = "missing_data"


@dataclass(frozen=True)
class GateResult:
    """Auditable pass/fail output from one hard gate."""

    gate_id: str
    rule_ids: tuple[str, ...]
    passed: bool
    reason: str
    flags: tuple[GateFlag, ...] = ()
    failure_kind: GateFailureKind | None = None
    # Observed raw inputs, kept for the report and CSV. Unlike ScoreResult's
    # metrics (computed outputs, empty when nothing was computed), a None here
    # is a true observation of absence -- it is what "missing data" looked
    # like, which the missing-data display needs to show.
    metrics: Mapping[str, float | int | bool | None] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class HardGateThresholds:
    """Operator-configured numeric thresholds used by the hard gates."""

    min_ttm_net_income: float
    min_operating_cash_flow: float
    max_mean_rating: float
    min_price: float
    max_price: float
    pilot_bias_max_price: float


def hard_gate_thresholds_from_config(
    config: Mapping[str, Any],
) -> HardGateThresholds:
    """Purely extract Step 3 thresholds from parsed YAML data."""

    thresholds = config["thresholds"]
    profitability = thresholds["profitability"]
    analyst = thresholds["analyst"]
    price = thresholds["price"]
    return HardGateThresholds(
        min_ttm_net_income=float(profitability["min_ttm_net_income"]),
        min_operating_cash_flow=float(
            profitability["min_operating_cash_flow"]
        ),
        max_mean_rating=float(analyst["max_mean_rating"]),
        min_price=float(price["min_usd"]),
        max_price=float(price["max_usd"]),
        pilot_bias_max_price=float(price["pilot_bias_max_usd"]),
    )


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _money(value: float) -> str:
    return f"${value:,.2f}"


def evaluate_profitability(
    snapshot: TickerSnapshot,
    thresholds: HardGateThresholds,
) -> GateResult:
    """Require positive TTM net income and operating cash flow."""

    net_income = _finite_number(snapshot.fundamentals.get("net_income_ttm"))
    cash_flow = _finite_number(
        snapshot.fundamentals.get("operating_cash_flow_ttm")
    )

    missing = []
    if net_income is None:
        missing.append("net_income_ttm")
    if cash_flow is None:
        missing.append("operating_cash_flow_ttm")
    observed = {
        "net_income_ttm": net_income,
        "operating_cash_flow_ttm": cash_flow,
    }
    if missing:
        return GateResult(
            gate_id="F1",
            rule_ids=("ST-SEL-01",),
            passed=False,
            reason=f"Cannot evaluate: missing {', '.join(missing)}.",
            failure_kind=GateFailureKind.MISSING_DATA,
            metrics=observed,
        )

    # F1 / ST-SEL-01: both profitability measures must be strictly positive.
    passed = (
        net_income > thresholds.min_ttm_net_income
        and cash_flow > thresholds.min_operating_cash_flow
    )
    if passed:
        reason = (
            f"TTM net income {_money(net_income)} and operating cash flow "
            f"{_money(cash_flow)} are both positive."
        )
    else:
        failures = []
        if net_income <= thresholds.min_ttm_net_income:
            failures.append(f"net income {_money(net_income)} is not positive")
        if cash_flow <= thresholds.min_operating_cash_flow:
            failures.append(
                f"operating cash flow {_money(cash_flow)} is not positive"
            )
        reason = "; ".join(failures) + "."

    return GateResult(
        gate_id="F1",
        rule_ids=("ST-SEL-01",),
        passed=passed,
        reason=reason,
        failure_kind=None if passed else GateFailureKind.FITNESS,
        metrics=observed,
    )


def evaluate_recommendation_mean(
    snapshot: TickerSnapshot,
    thresholds: HardGateThresholds,
) -> GateResult:
    """Require a bullish-enough mean analyst recommendation."""

    recommendation_mean = _finite_number(
        snapshot.analyst.get("recommendation_mean")
    )
    if recommendation_mean is None:
        return GateResult(
            gate_id="F2",
            rule_ids=("ST-SEL-02",),
            passed=False,
            reason="Cannot evaluate: missing recommendation_mean.",
            failure_kind=GateFailureKind.MISSING_DATA,
            metrics={"recommendation_mean": None},
        )

    # F2 / ST-SEL-02: 1=strong buy and 5=sell, so lower is stronger.
    passed = recommendation_mean <= thresholds.max_mean_rating
    comparison = "at or below" if passed else "above"
    return GateResult(
        gate_id="F2",
        rule_ids=("ST-SEL-02",),
        passed=passed,
        reason=(
            f"Mean analyst rating {recommendation_mean:.2f} is {comparison} "
            f"the {thresholds.max_mean_rating:.2f} maximum "
            "(1=strong buy, 5=sell)."
        ),
        failure_kind=None if passed else GateFailureKind.FITNESS,
        metrics={"recommendation_mean": recommendation_mean},
    )


def evaluate_price_band(
    snapshot: TickerSnapshot,
    thresholds: HardGateThresholds,
) -> GateResult:
    """Require the configured pilot-era price band and surface pilot bias."""

    price = _finite_number(snapshot.fundamentals.get("current_price"))
    if price is None:
        return GateResult(
            gate_id="F3",
            rule_ids=("ST-SEL-03", "ST-SEL-13"),
            passed=False,
            reason="Cannot evaluate: missing current_price.",
            flags=(
                GateFlag(
                    name="pilot_band",
                    active=False,
                    reason="Not evaluated because current_price is missing.",
                ),
            ),
            failure_kind=GateFailureKind.MISSING_DATA,
            metrics={"price": None},
        )

    # F3 / ST-SEL-03, ST-SEL-13: gate at $10-$50; $10-$30 is a flag only.
    passed = thresholds.min_price <= price <= thresholds.max_price
    pilot_band = (
        thresholds.min_price <= price <= thresholds.pilot_bias_max_price
    )
    price_band = (
        f"{_money(thresholds.min_price)}-{_money(thresholds.max_price)}"
    )
    pilot_price_band = (
        f"{_money(thresholds.min_price)}-"
        f"{_money(thresholds.pilot_bias_max_price)}"
    )
    if passed:
        reason = f"Price {_money(price)} is within the {price_band} band."
    else:
        reason = f"Price {_money(price)} is outside the {price_band} band."

    flag_reason = (
        f"Price {_money(price)} is within the {pilot_price_band} pilot band."
        if pilot_band
        else f"Price {_money(price)} is outside the {pilot_price_band} pilot band."
    )
    return GateResult(
        gate_id="F3",
        rule_ids=("ST-SEL-03", "ST-SEL-13"),
        passed=passed,
        reason=reason,
        flags=(
            GateFlag(
                name="pilot_band",
                active=pilot_band,
                reason=flag_reason,
            ),
        ),
        failure_kind=None if passed else GateFailureKind.FITNESS,
        metrics={"price": price},
    )


def evaluate_sub_ten_floor(
    snapshot: TickerSnapshot,
    thresholds: HardGateThresholds,
) -> GateResult:
    """Reject stocks below the absolute $10 floor."""

    price = _finite_number(snapshot.fundamentals.get("current_price"))
    if price is None:
        return GateResult(
            gate_id="F4",
            rule_ids=("ST-SEL-04",),
            passed=False,
            reason="Cannot evaluate: missing current_price.",
            failure_kind=GateFailureKind.MISSING_DATA,
            metrics={"price": None},
        )

    # F4 / ST-SEL-04: sub-$10 stocks fail the absolute price floor.
    passed = price >= thresholds.min_price
    comparison = "meets" if passed else "is below"
    return GateResult(
        gate_id="F4",
        rule_ids=("ST-SEL-04",),
        passed=passed,
        reason=(
            f"Price {_money(price)} {comparison} "
            f"the {_money(thresholds.min_price)} floor."
        ),
        failure_kind=None if passed else GateFailureKind.FITNESS,
        metrics={"price": price},
    )


def evaluate_options_existence(snapshot: TickerSnapshot) -> GateResult:
    """Require basic evidence that listed options are available."""

    if snapshot.option_expirations is None:
        return GateResult(
            gate_id="F9",
            rule_ids=("ST-SEL",),
            passed=False,
            reason="Cannot evaluate: options availability metadata is missing.",
            failure_kind=GateFailureKind.MISSING_DATA,
            metrics={"options_available": None},
        )

    # F9 / ST-SEL (liquidity): existence only; never fetch chain data here.
    passed = len(snapshot.option_expirations) > 0
    reason = (
        f"Options are available ({len(snapshot.option_expirations)} listed expirations)."
        if passed
        else "No listed option expirations are available."
    )
    return GateResult(
        gate_id="F9",
        rule_ids=("ST-SEL",),
        passed=passed,
        reason=reason,
        failure_kind=None if passed else GateFailureKind.FITNESS,
        metrics={"options_available": passed},
    )


def evaluate_hard_gates(
    snapshot: TickerSnapshot,
    thresholds: HardGateThresholds,
) -> tuple[GateResult, ...]:
    """Evaluate all Step 3 hard gates in specification order."""

    return (
        evaluate_profitability(snapshot, thresholds),
        evaluate_recommendation_mean(snapshot, thresholds),
        evaluate_price_band(snapshot, thresholds),
        evaluate_sub_ten_floor(snapshot, thresholds),
        evaluate_options_existence(snapshot),
    )
