"""Pure hard-gate partitioning for screen reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .snapshot import TickerSnapshot

from .gates import (
    GateFailureKind,
    GateResult,
    HardGateThresholds,
    evaluate_hard_gates,
)


@dataclass(frozen=True)
class EvaluatedTicker:
    """One normalized snapshot and its hard-gate audit trail."""

    snapshot: TickerSnapshot
    gate_results: tuple[GateResult, ...]


@dataclass(frozen=True)
class HardGateBuckets:
    """Exclusive hard-gate reporting buckets."""

    passed: tuple[EvaluatedTicker, ...]
    failed_fitness: tuple[EvaluatedTicker, ...]
    failed_missing_data: tuple[EvaluatedTicker, ...]


def partition_hard_gates(
    snapshots: Sequence[TickerSnapshot],
    thresholds: HardGateThresholds,
) -> HardGateBuckets:
    """Evaluate snapshots, then split the exclusive reporting buckets."""

    return partition_evaluated_hard_gates(
        evaluate_hard_gates_for_snapshots(snapshots, thresholds)
    )


def evaluate_hard_gates_for_snapshots(
    snapshots: Sequence[TickerSnapshot],
    thresholds: HardGateThresholds,
) -> tuple[EvaluatedTicker, ...]:
    """Evaluate each snapshot once so individual gates can be rescued later."""

    return tuple(
        EvaluatedTicker(
            snapshot=snapshot,
            gate_results=evaluate_hard_gates(snapshot, thresholds),
        )
        for snapshot in snapshots
    )


def partition_evaluated_hard_gates(
    evaluated_tickers: Sequence[EvaluatedTicker],
) -> HardGateBuckets:
    """Split existing results without re-running any hard gate."""

    passed = []
    failed_fitness = []
    failed_missing_data = []

    for evaluated in evaluated_tickers:
        failures = [
            result for result in evaluated.gate_results if not result.passed
        ]
        if not failures:
            passed.append(evaluated)
        elif any(
            result.failure_kind is GateFailureKind.FITNESS
            for result in failures
        ):
            failed_fitness.append(evaluated)
        else:
            failed_missing_data.append(evaluated)

    return HardGateBuckets(
        passed=tuple(passed),
        failed_fitness=tuple(failed_fitness),
        failed_missing_data=tuple(failed_missing_data),
    )
