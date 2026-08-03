"""The presentation layer's input contract.

`Step5PipelineOutput` carries the scored survivors and the diff, but not the
hard-gate buckets, the fetch-error symbols, or the universe list -- all three
are needed for a CSV row per evaluated ticker. `PipelineResult` wraps it with
those, so the renderers take one argument and compute nothing themselves.

This lives in `reporting` rather than `screening` on purpose. `scoring` imports
`GateResult` from `screening`, so anything in `screening/__init__` that reaches
back into `scoring` closes an import cycle. Nothing imports `reporting` except
the runner, which makes it the safe home for a type that references both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .flags import FlaggedScoredTicker
from .partition import HardGateBuckets
from .diff import RunDiff, RunState
from .run_state import Step5PipelineOutput


@dataclass(frozen=True)
class PipelineResult:
    """One complete run, assembled for rendering."""

    run_timestamp: datetime
    run_date: date
    universe_symbols: tuple[str, ...]
    fetch_error_symbols: tuple[str, ...]
    buckets: HardGateBuckets
    step5: Step5PipelineOutput
    universe_volatility_percentile: float | None

    @property
    def flagged_scored(self) -> tuple[FlaggedScoredTicker, ...]:
        return self.step5.flagged_scored

    @property
    def diff(self) -> RunDiff:
        return self.step5.diff

    @property
    def current_state(self) -> RunState:
        return self.step5.current_state
