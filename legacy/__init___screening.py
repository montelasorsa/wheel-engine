"""Deterministic, rule-mapped screening functions."""

from .hard_gates import (
    GateFlag,
    GateFailureKind,
    GateResult,
    HardGateThresholds,
    evaluate_hard_gates,
    evaluate_options_existence,
    evaluate_price_band,
    evaluate_profitability,
    evaluate_recommendation_mean,
    evaluate_sub_ten_floor,
    hard_gate_thresholds_from_config,
)
from .pipeline import (
    EvaluatedTicker,
    HardGateBuckets,
    evaluate_hard_gates_for_snapshots,
    partition_hard_gates,
    partition_evaluated_hard_gates,
)
from .rescue import (
    OperatingCashFlowRescueAttempt,
    OperatingCashFlowRescueBatch,
    apply_fmp_operating_cash_flow,
    is_operating_cash_flow_only_blocker,
    rescue_enabled_from_config,
    rescue_operating_cash_flow_ttm,
)
from .diff import (
    compute_diff,
    latest_state_file,
    load_prior_state,
    save_current_state,
)

__all__ = [
    "GateFlag",
    "GateFailureKind",
    "GateResult",
    "HardGateThresholds",
    "evaluate_hard_gates",
    "evaluate_options_existence",
    "evaluate_price_band",
    "evaluate_profitability",
    "evaluate_recommendation_mean",
    "evaluate_sub_ten_floor",
    "hard_gate_thresholds_from_config",
    "EvaluatedTicker",
    "HardGateBuckets",
    "evaluate_hard_gates_for_snapshots",
    "partition_hard_gates",
    "partition_evaluated_hard_gates",
    "OperatingCashFlowRescueAttempt",
    "OperatingCashFlowRescueBatch",
    "apply_fmp_operating_cash_flow",
    "is_operating_cash_flow_only_blocker",
    "rescue_enabled_from_config",
    "rescue_operating_cash_flow_ttm",
    "compute_diff",
    "latest_state_file",
    "load_prior_state",
    "save_current_state",
]
