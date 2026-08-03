"""Narrow FMP rescue for a missing yfinance operating-cash-flow field."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Callable, Mapping, Sequence

from wheel_screener.data import TickerSnapshot

from .hard_gates import (
    GateFailureKind,
    GateResult,
    HardGateThresholds,
    evaluate_profitability,
)
from .pipeline import EvaluatedTicker


RESCUED_FIELD = "operating_cash_flow_ttm"


def rescue_enabled_from_config(config: Mapping[str, Any]) -> bool:
    """Read the explicit, default-off rescue switch."""

    value = config.get("RESCUE_ENABLED", False)
    if not isinstance(value, bool):
        raise ValueError("RESCUE_ENABLED must be true or false.")
    return value


@dataclass(frozen=True)
class OperatingCashFlowRescueAttempt:
    """Audit record for one possible FMP fallback."""

    symbol: str
    queried_fmp: bool
    yfinance_value: float | int | None
    fmp_value: float | None
    f1_before: GateResult
    f1_after: GateResult
    error: str | None = None


@dataclass(frozen=True)
class OperatingCashFlowRescueBatch:
    """Updated evaluations plus a complete fallback-call audit."""

    evaluated_tickers: tuple[EvaluatedTicker, ...]
    attempts: tuple[OperatingCashFlowRescueAttempt, ...]

    @property
    def queried_symbols(self) -> tuple[str, ...]:
        return tuple(
            attempt.symbol for attempt in self.attempts if attempt.queried_fmp
        )


def _f1_result(evaluated: EvaluatedTicker) -> GateResult:
    return next(
        result for result in evaluated.gate_results if result.gate_id == "F1"
    )


def apply_fmp_operating_cash_flow(
    snapshot: TickerSnapshot,
    value: float,
) -> TickerSnapshot:
    """Purely fill the approved null field and attach FMP provenance."""

    existing = snapshot.fundamentals.get(RESCUED_FIELD)
    if existing is not None:
        raise ValueError(
            f"{snapshot.symbol} already has {RESCUED_FIELD}; "
            "FMP must not replace or cross-validate yfinance."
        )
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError("FMP operating cash flow must be finite.")

    fundamentals = dict(snapshot.fundamentals)
    fundamentals[RESCUED_FIELD] = numeric_value
    sources = dict(snapshot.field_sources)
    sources[RESCUED_FIELD] = "fmp"
    return replace(
        snapshot,
        fundamentals=fundamentals,
        field_sources=sources,
    )


def is_operating_cash_flow_only_blocker(
    evaluated: EvaluatedTicker,
    thresholds: HardGateThresholds,
) -> bool:
    """Return true only when FMP could be the sole hard-gate rescue."""

    snapshot = evaluated.snapshot
    if snapshot.fundamentals.get(RESCUED_FIELD) is not None:
        return False

    f1 = _f1_result(evaluated)
    if (
        f1.passed
        or f1.failure_kind is not GateFailureKind.MISSING_DATA
        or any(
            not result.passed
            for result in evaluated.gate_results
            if result.gate_id != "F1"
        )
    ):
        return False

    # Probe only F1 to prove no other F1 input already blocks the name.
    probe = apply_fmp_operating_cash_flow(
        snapshot,
        thresholds.min_operating_cash_flow + 1.0,
    )
    return evaluate_profitability(probe, thresholds).passed


def _replace_f1(
    evaluated: EvaluatedTicker,
    new_snapshot: TickerSnapshot,
    new_f1: GateResult,
) -> EvaluatedTicker:
    results = tuple(
        new_f1 if result.gate_id == "F1" else result
        for result in evaluated.gate_results
    )
    return EvaluatedTicker(snapshot=new_snapshot, gate_results=results)


def rescue_operating_cash_flow_ttm(
    evaluated_tickers: Sequence[EvaluatedTicker],
    thresholds: HardGateThresholds,
    fetch_fmp_value: Callable[[str], float | None],
    *,
    enabled: bool = False,
) -> OperatingCashFlowRescueBatch:
    """Query FMP only for eligible nulls, then re-run F1 and nothing else."""

    if not enabled:
        return OperatingCashFlowRescueBatch(
            evaluated_tickers=tuple(evaluated_tickers),
            attempts=tuple(
                OperatingCashFlowRescueAttempt(
                    symbol=evaluated.snapshot.symbol,
                    queried_fmp=False,
                    yfinance_value=evaluated.snapshot.fundamentals.get(
                        RESCUED_FIELD
                    ),
                    fmp_value=None,
                    f1_before=_f1_result(evaluated),
                    f1_after=_f1_result(evaluated),
                )
                for evaluated in evaluated_tickers
            ),
        )

    updated = []
    attempts = []
    for evaluated in evaluated_tickers:
        f1_before = _f1_result(evaluated)
        yfinance_value = evaluated.snapshot.fundamentals.get(RESCUED_FIELD)
        if not is_operating_cash_flow_only_blocker(evaluated, thresholds):
            updated.append(evaluated)
            attempts.append(
                OperatingCashFlowRescueAttempt(
                    symbol=evaluated.snapshot.symbol,
                    queried_fmp=False,
                    yfinance_value=yfinance_value,
                    fmp_value=None,
                    f1_before=f1_before,
                    f1_after=f1_before,
                )
            )
            continue

        try:
            fmp_value = fetch_fmp_value(evaluated.snapshot.symbol)
        except Exception as exc:
            updated.append(evaluated)
            attempts.append(
                OperatingCashFlowRescueAttempt(
                    symbol=evaluated.snapshot.symbol,
                    queried_fmp=True,
                    yfinance_value=yfinance_value,
                    fmp_value=None,
                    f1_before=f1_before,
                    f1_after=f1_before,
                    error=(
                        f"{type(exc).__name__}: FMP rescue request failed."
                    ),
                )
            )
            continue

        if fmp_value is None:
            updated.append(evaluated)
            attempts.append(
                OperatingCashFlowRescueAttempt(
                    symbol=evaluated.snapshot.symbol,
                    queried_fmp=True,
                    yfinance_value=yfinance_value,
                    fmp_value=None,
                    f1_before=f1_before,
                    f1_after=f1_before,
                )
            )
            continue

        rescued_snapshot = apply_fmp_operating_cash_flow(
            evaluated.snapshot,
            fmp_value,
        )
        # F1 / ST-SEL-01 is the only gate re-run after this field rescue.
        f1_after = evaluate_profitability(rescued_snapshot, thresholds)
        rescued_evaluated = _replace_f1(
            evaluated,
            rescued_snapshot,
            f1_after,
        )
        updated.append(rescued_evaluated)
        attempts.append(
            OperatingCashFlowRescueAttempt(
                symbol=evaluated.snapshot.symbol,
                queried_fmp=True,
                yfinance_value=yfinance_value,
                fmp_value=float(fmp_value),
                f1_before=f1_before,
                f1_after=f1_after,
            )
        )

    return OperatingCashFlowRescueBatch(
        evaluated_tickers=tuple(updated),
        attempts=tuple(attempts),
    )
