"""Pure score filters and composite scoring."""

from .score_filters import (
    CompositeWeights,
    ScoreResult,
    ScoredTicker,
    ScoringThresholds,
    annualized_realized_volatility,
    composite_weights_from_config,
    compute_universe_volatility_percentile,
    score_eligible_snapshot,
    scoring_thresholds_from_config,
)
from .flags import (
    EarningsProximityFlag,
    FlaggedScoredTicker,
    attach_earnings_flags,
    compute_earnings_proximity_flag,
    extract_next_earnings_date,
)

__all__ = [
    "CompositeWeights",
    "ScoreResult",
    "ScoredTicker",
    "ScoringThresholds",
    "annualized_realized_volatility",
    "composite_weights_from_config",
    "compute_universe_volatility_percentile",
    "score_eligible_snapshot",
    "scoring_thresholds_from_config",
    "EarningsProximityFlag",
    "FlaggedScoredTicker",
    "attach_earnings_flags",
    "compute_earnings_proximity_flag",
    "extract_next_earnings_date",
]
