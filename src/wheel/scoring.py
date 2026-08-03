"""Pure, rule-mapped score filters for hard-gate survivors."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence

import pandas as pd

from .snapshot import TickerSnapshot
from .gates import GateResult


IV_PROXY_APPROXIMATION = (
    "APPROXIMATION: 30-day annualized realized volatility is used as an "
    "interim proxy for implied volatility; no live IV is used."
)


class IneligibleForScoringError(ValueError):
    """Raised if scoring is requested for a hard-gate failure."""


@dataclass(frozen=True)
class ScoreResult:
    """Auditable 0-100 output from one score filter."""

    filter_id: str
    rule_ids: tuple[str, ...]
    score: float | None
    reason: str
    is_approximation: bool = False
    approximation_note: str | None = None
    # Raw inputs behind `score`, kept for the CSV that Components B and C read.
    # Empty whenever the filter could not evaluate: never infer a value.
    metrics: Mapping[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoringThresholds:
    """Operator-configured thresholds used by score filters."""

    stability_history_days: int
    max_single_day_move: float
    max_realized_vol_universe_percentile: float
    iv_lookback_trading_days: int
    annualization_trading_days: int
    iv_quality_zone_min: float
    iv_quality_zone_max: float
    iv_high_vol_penalty_above: float
    chart_history_days: int
    min_below_two_year_high: float
    max_mean_rating: float


@dataclass(frozen=True)
class CompositeWeights:
    """Config-driven composite weights."""

    stability: float
    iv_proxy_quality: float
    chart_position: float
    dividend: float
    analyst_strength: float


@dataclass(frozen=True)
class ScoredTicker:
    """Four filter scores plus the F2 margin and weighted composite."""

    symbol: str
    filter_results: tuple[ScoreResult, ...]
    analyst_strength_score: float | None
    analyst_strength_reason: str
    composite_score: float | None
    contains_approximation: bool
    approximation_notes: tuple[str, ...]


def scoring_thresholds_from_config(
    config: Mapping[str, Any],
) -> ScoringThresholds:
    """Purely extract Step 4 thresholds from parsed YAML data."""

    thresholds = config["thresholds"]
    stability = thresholds["stability"]
    iv_proxy = thresholds["iv_proxy"]
    chart_position = thresholds["chart_position"]
    analyst = thresholds["analyst"]
    return ScoringThresholds(
        stability_history_days=int(stability["history_days"]),
        max_single_day_move=float(stability["max_single_day_move"]),
        max_realized_vol_universe_percentile=float(
            stability["max_realized_vol_universe_percentile"]
        ),
        iv_lookback_trading_days=int(iv_proxy["lookback_trading_days"]),
        annualization_trading_days=int(
            iv_proxy["annualization_trading_days"]
        ),
        iv_quality_zone_min=float(iv_proxy["quality_zone_min"]),
        iv_quality_zone_max=float(iv_proxy["quality_zone_max"]),
        iv_high_vol_penalty_above=float(
            iv_proxy["high_vol_penalty_above"]
        ),
        chart_history_days=int(chart_position["history_days"]),
        min_below_two_year_high=float(
            chart_position["min_below_two_year_high"]
        ),
        max_mean_rating=float(analyst["max_mean_rating"]),
    )


def composite_weights_from_config(
    config: Mapping[str, Any],
) -> CompositeWeights:
    """Purely extract and validate composite weights from parsed YAML data."""

    weights = CompositeWeights(
        stability=float(config["weights"]["stability"]),
        iv_proxy_quality=float(config["weights"]["iv_proxy_quality"]),
        chart_position=float(config["weights"]["chart_position"]),
        dividend=float(config["weights"]["dividend"]),
        analyst_strength=float(config["weights"]["analyst_strength"]),
    )
    total = sum(
        (
            weights.stability,
            weights.iv_proxy_quality,
            weights.chart_position,
            weights.dividend,
            weights.analyst_strength,
        )
    )
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise ValueError(f"Composite weights must total 1.0; got {total}.")
    return weights


def _price_series(
    history: pd.DataFrame,
    *,
    calendar_days: int | None = None,
) -> pd.Series:
    if history is None or history.empty or "date" not in history.columns:
        return pd.Series(dtype=float)

    price_column = (
        "adjusted_close"
        if "adjusted_close" in history.columns
        else "close"
    )
    if price_column not in history.columns:
        return pd.Series(dtype=float)

    normalized = history.loc[:, ["date", price_column]].copy()
    normalized["date"] = pd.to_datetime(normalized["date"], utc=True)
    normalized[price_column] = pd.to_numeric(
        normalized[price_column], errors="coerce"
    )
    normalized = normalized.dropna().sort_values("date", kind="stable")
    if normalized.empty:
        return pd.Series(dtype=float)
    if calendar_days is not None:
        cutoff = normalized["date"].iloc[-1] - pd.Timedelta(days=calendar_days)
        normalized = normalized.loc[normalized["date"] >= cutoff]
    return normalized.set_index("date")[price_column]


def _daily_returns(
    history: pd.DataFrame,
    *,
    calendar_days: int | None = None,
) -> pd.Series:
    prices = _price_series(history, calendar_days=calendar_days)
    return prices.pct_change(fill_method=None).dropna()


def annualized_realized_volatility(
    snapshot: TickerSnapshot,
    *,
    lookback_trading_days: int,
    annualization_trading_days: int,
    calendar_days: int | None = None,
) -> float | None:
    """Compute annualized close-to-close realized volatility."""

    returns = _daily_returns(
        snapshot.price_history,
        calendar_days=calendar_days,
    )
    if len(returns) < lookback_trading_days:
        return None
    sample = returns.tail(lookback_trading_days)
    volatility = sample.std(ddof=1) * math.sqrt(annualization_trading_days)
    return float(volatility) if math.isfinite(volatility) else None


def compute_universe_volatility_percentile(
    snapshots: Sequence[TickerSnapshot],
    thresholds: ScoringThresholds,
) -> float | None:
    """Compute F5's configured realized-vol benchmark across the universe."""

    values = []
    for snapshot in snapshots:
        returns = _daily_returns(
            snapshot.price_history,
            calendar_days=thresholds.stability_history_days,
        )
        if len(returns) < 2:
            continue
        volatility = returns.std(ddof=1) * math.sqrt(
            thresholds.annualization_trading_days
        )
        if math.isfinite(volatility):
            values.append(float(volatility))
    if not values:
        return None
    return float(
        pd.Series(values).quantile(
            thresholds.max_realized_vol_universe_percentile
        )
    )


def score_stability(
    snapshot: TickerSnapshot,
    thresholds: ScoringThresholds,
    universe_volatility_percentile: float | None,
) -> ScoreResult:
    """Score F5's gap and universe-relative volatility conditions."""

    returns = _daily_returns(
        snapshot.price_history,
        calendar_days=thresholds.stability_history_days,
    )
    if returns.empty:
        return ScoreResult(
            filter_id="F5",
            rule_ids=("ST-SEL-05",),
            score=None,
            reason="Cannot score: price history has no daily returns.",
        )
    if universe_volatility_percentile is None:
        return ScoreResult(
            filter_id="F5",
            rule_ids=("ST-SEL-05",),
            score=None,
            reason="Cannot score: universe volatility percentile is unavailable.",
        )

    max_move = float(returns.abs().max())
    realized_volatility = float(
        returns.std(ddof=1)
        * math.sqrt(thresholds.annualization_trading_days)
    )

    # F5 / ST-SEL-05: 50 points per satisfied stability condition.
    move_passed = max_move <= thresholds.max_single_day_move
    volatility_passed = realized_volatility < universe_volatility_percentile
    score = 50.0 * float(move_passed) + 50.0 * float(volatility_passed)
    return ScoreResult(
        filter_id="F5",
        rule_ids=("ST-SEL-05",),
        score=score,
        reason=(
            f"Max absolute daily move {max_move:.2%} "
            f"({'passes' if move_passed else 'fails'}) the "
            f"{thresholds.max_single_day_move:.2%} limit; annualized "
            f"realized vol {realized_volatility:.2%} "
            f"({'is below' if volatility_passed else 'is not below'}) the "
            f"universe percentile benchmark "
            f"{universe_volatility_percentile:.2%}."
        ),
        metrics={
            "max_daily_move": max_move,
            "realized_vol": realized_volatility,
        },
    )


def score_dividend(snapshot: TickerSnapshot) -> ScoreResult:
    """Award F6's dividend bonus and surface the provider yield."""

    dividend_events = (
        pd.to_numeric(snapshot.dividends.get("dividend"), errors="coerce")
        if "dividend" in snapshot.dividends.columns
        else pd.Series(dtype=float)
    )
    pays_dividend = bool((dividend_events.fillna(0) > 0).any())
    yield_value = snapshot.fundamentals.get("dividend_yield_percent")
    yield_metric = (
        float(yield_value)
        if isinstance(yield_value, (int, float))
        and math.isfinite(float(yield_value))
        else None
    )
    yield_text = (
        f"{yield_metric:.2f}%" if yield_metric is not None else "unavailable"
    )

    # F6 / ST-SEL-06: dividend payers receive the full bonus.
    return ScoreResult(
        filter_id="F6",
        rule_ids=("ST-SEL-06",),
        score=100.0 if pays_dividend else 0.0,
        reason=(
            f"{'Pays' if pays_dividend else 'Does not pay'} a dividend in "
            f"the fetched history; surfaced yield is {yield_text}."
        ),
        metrics={"dividend_yield": yield_metric},
    )


def _iv_proxy_score(
    realized_volatility: float,
    thresholds: ScoringThresholds,
) -> float:
    minimum = thresholds.iv_quality_zone_min
    maximum = thresholds.iv_quality_zone_max
    high = thresholds.iv_high_vol_penalty_above

    if realized_volatility < minimum:
        return max(0.0, 100.0 * realized_volatility / minimum)
    if realized_volatility <= maximum:
        return 100.0
    if realized_volatility < high:
        fraction = (realized_volatility - maximum) / (high - maximum)
        return 100.0 - 50.0 * fraction
    return max(0.0, 50.0 * (1.0 - (realized_volatility - high) / high))


def score_iv_proxy(
    snapshot: TickerSnapshot,
    thresholds: ScoringThresholds,
) -> ScoreResult:
    """Score F7 with an explicitly labeled realized-volatility proxy."""

    realized_volatility = annualized_realized_volatility(
        snapshot,
        lookback_trading_days=thresholds.iv_lookback_trading_days,
        annualization_trading_days=thresholds.annualization_trading_days,
    )
    if realized_volatility is None:
        return ScoreResult(
            filter_id="F7",
            rule_ids=("ST-SEL-10", "ST-SEL-11"),
            score=None,
            reason=f"{IV_PROXY_APPROXIMATION} Insufficient price history.",
            is_approximation=True,
            approximation_note=IV_PROXY_APPROXIMATION,
        )

    # F7 / ST-SEL-10, ST-SEL-11: high volatility loses points.
    score = _iv_proxy_score(realized_volatility, thresholds)
    return ScoreResult(
        filter_id="F7",
        rule_ids=("ST-SEL-10", "ST-SEL-11"),
        score=score,
        reason=(
            f"{IV_PROXY_APPROXIMATION} The proxy is "
            f"{realized_volatility:.2%}; score {score:.2f}/100."
        ),
        is_approximation=True,
        approximation_note=IV_PROXY_APPROXIMATION,
        metrics={"realized_vol_30d": realized_volatility},
    )


def score_chart_position(
    snapshot: TickerSnapshot,
    thresholds: ScoringThresholds,
) -> ScoreResult:
    """Penalize F8 when price is within 5% of its two-year high."""

    prices = _price_series(
        snapshot.price_history,
        calendar_days=thresholds.chart_history_days,
    )
    if prices.empty:
        return ScoreResult(
            filter_id="F8",
            rule_ids=("ST-SEL-12",),
            score=None,
            reason="Cannot score: two-year price history is unavailable.",
        )

    current_price = float(prices.iloc[-1])
    high = float(prices.max())
    if high <= 0:
        return ScoreResult(
            filter_id="F8",
            rule_ids=("ST-SEL-12",),
            score=None,
            reason="Cannot score: two-year high is not positive.",
        )
    below_high = (high - current_price) / high

    # F8 / ST-SEL-12: within 5% of the two-year high receives no points.
    too_close = below_high <= thresholds.min_below_two_year_high
    return ScoreResult(
        filter_id="F8",
        rule_ids=("ST-SEL-12",),
        score=0.0 if too_close else 100.0,
        reason=(
            f"Adjusted close is {below_high:.2%} below the two-year high; "
            f"{'within' if too_close else 'outside'} the "
            f"{thresholds.min_below_two_year_high:.2%} penalty zone."
        ),
        metrics={"pct_below_2y_high": below_high},
    )


def score_analyst_strength(
    snapshot: TickerSnapshot,
    thresholds: ScoringThresholds,
) -> tuple[float | None, str]:
    """Score the F2 pass margin used by the configured composite."""

    value = snapshot.analyst.get("recommendation_mean")
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None, "Cannot score analyst strength: recommendation is missing."
    rating = float(value)
    denominator = thresholds.max_mean_rating - 1.0
    if denominator <= 0:
        return None, "Cannot score analyst strength: invalid configured maximum."
    score = max(
        0.0,
        min(100.0, 100.0 * (thresholds.max_mean_rating - rating) / denominator),
    )
    return (
        score,
        f"Mean rating {rating:.2f} has a {score:.2f}/100 margin score "
        f"against the {thresholds.max_mean_rating:.2f} gate.",
    )


def score_eligible_snapshot(
    snapshot: TickerSnapshot,
    gate_results: Sequence[GateResult],
    thresholds: ScoringThresholds,
    weights: CompositeWeights,
    universe_volatility_percentile: float | None,
) -> ScoredTicker:
    """Score one ticker only after every hard gate has passed."""

    if not gate_results or not all(result.passed for result in gate_results):
        raise IneligibleForScoringError(
            f"{snapshot.symbol} did not pass every hard gate."
        )

    results = (
        score_stability(
            snapshot,
            thresholds,
            universe_volatility_percentile,
        ),
        score_dividend(snapshot),
        score_iv_proxy(snapshot, thresholds),
        score_chart_position(snapshot, thresholds),
    )
    analyst_score, analyst_reason = score_analyst_strength(
        snapshot,
        thresholds,
    )
    scores = {result.filter_id: result.score for result in results}
    required = (scores["F5"], scores["F6"], scores["F7"], scores["F8"])
    if analyst_score is None or any(score is None for score in required):
        composite = None
    else:
        composite = (
            float(scores["F5"]) * weights.stability
            + float(scores["F7"]) * weights.iv_proxy_quality
            + float(scores["F8"]) * weights.chart_position
            + float(scores["F6"]) * weights.dividend
            + analyst_score * weights.analyst_strength
        )
        composite = max(0.0, min(100.0, composite))

    notes = tuple(
        dict.fromkeys(
            result.approximation_note
            for result in results
            if result.approximation_note is not None
        )
    )
    return ScoredTicker(
        symbol=snapshot.symbol,
        filter_results=results,
        analyst_strength_score=analyst_score,
        analyst_strength_reason=analyst_reason,
        composite_score=composite,
        contains_approximation=bool(notes),
        approximation_notes=notes,
    )

