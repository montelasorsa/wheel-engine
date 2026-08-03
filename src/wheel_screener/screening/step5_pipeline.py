"""Step 5 orchestration with pure flag/state cores and isolated JSON IO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence

from wheel_screener.scoring import (
    FlaggedScoredTicker,
    ScoredTicker,
    attach_earnings_flags,
)

from .diff import (
    RunDiff,
    RunState,
    compute_diff,
    latest_state_file,
    load_prior_state,
    save_current_state,
)
from .pipeline import EvaluatedTicker, HardGateBuckets


@dataclass(frozen=True)
class Step5PipelineOutput:
    """Step 5 results preserved for the future report layer."""

    flagged_scored: tuple[FlaggedScoredTicker, ...]
    diff: RunDiff
    current_state: RunState
    state_path: Path
    prior_state_path: Path | None


def _failure_reason(evaluated: EvaluatedTicker) -> str | None:
    failures = [
        f"{result.gate_id}: {result.reason}"
        for result in evaluated.gate_results
        if not result.passed
    ]
    return "; ".join(failures) if failures else None


def build_run_state(
    universe_symbols: Sequence[str],
    *,
    fetch_error_symbols: Sequence[str],
    buckets: HardGateBuckets,
    scored_tickers: Sequence[ScoredTicker],
) -> RunState:
    """Purely build one state record for every universe ticker."""

    scored_by_symbol = {item.symbol: item for item in scored_tickers}
    fitness_by_symbol = {
        item.snapshot.symbol: item for item in buckets.failed_fitness
    }
    missing_by_symbol = {
        item.snapshot.symbol: item for item in buckets.failed_missing_data
    }
    fetch_errors = set(fetch_error_symbols)

    state: RunState = {}
    for symbol in universe_symbols:
        if symbol in fetch_errors:
            state[symbol] = {
                "verdict": "fetch_error",
                "reason": "fetch error",
                "composite": None,
            }
        elif symbol in scored_by_symbol:
            state[symbol] = {
                "verdict": "scored",
                "reason": None,
                "composite": scored_by_symbol[symbol].composite_score,
            }
        elif symbol in fitness_by_symbol:
            state[symbol] = {
                "verdict": "fitness_fail",
                "reason": _failure_reason(fitness_by_symbol[symbol]),
                "composite": None,
            }
        elif symbol in missing_by_symbol:
            state[symbol] = {
                "verdict": "missing_data",
                "reason": _failure_reason(missing_by_symbol[symbol]),
                "composite": None,
            }
        else:
            raise ValueError(f"No run verdict was produced for {symbol}.")
    return state


def run_state_path(output_dir: str | Path, run_timestamp: datetime) -> Path:
    """Derive a timestamped state path under the configured output folder."""

    filename = run_timestamp.strftime("run_state_%Y-%m-%d-%H%M%S.json")
    return Path(output_dir) / filename


def finalize_step5_run(
    *,
    universe_symbols: Sequence[str],
    fetch_error_symbols: Sequence[str],
    buckets: HardGateBuckets,
    scored_tickers: Sequence[ScoredTicker],
    calendars_by_symbol: Mapping[str, Mapping | None],
    run_date: date,
    run_timestamp: datetime,
    earnings_threshold_days: int,
    output_dir: str | Path,
) -> Step5PipelineOutput:
    """Attach F10, diff against prior state, then save current state."""

    flagged = attach_earnings_flags(
        scored_tickers,
        calendars_by_symbol,
        run_date=run_date,
        threshold_days=earnings_threshold_days,
    )
    current_state = build_run_state(
        universe_symbols,
        fetch_error_symbols=fetch_error_symbols,
        buckets=buckets,
        scored_tickers=scored_tickers,
    )
    prior_path = latest_state_file(output_dir)
    prior_state = (
        load_prior_state(prior_path) if prior_path is not None else None
    )
    diff = compute_diff(prior_state, current_state)
    state_path = save_current_state(
        run_state_path(output_dir, run_timestamp),
        current_state,
    )
    return Step5PipelineOutput(
        flagged_scored=flagged,
        diff=diff,
        current_state=current_state,
        state_path=state_path,
        prior_state_path=prior_path,
    )

