"""Pure ST-SEL-07 run diffs.

Comparison only -- no filesystem. Persistence lives in `state_io.py`.
"""

from __future__ import annotations

from typing import Any, Mapping


RunState = dict[str, dict[str, str | float | None]]
RunDiff = dict[str, bool | list[Any]]


def compute_diff(
    prior_state: Mapping[str, Mapping[str, Any]] | None,
    current_state: Mapping[str, Mapping[str, Any]],
) -> RunDiff:
    """Purely compare qualification verdicts between two runs."""

    if prior_state is None:
        return {
            "first_run": True,
            "newly_qualified": [],
            "newly_dropped": [],
            "unchanged": [],
        }

    prior_scored = {
        symbol
        for symbol, values in prior_state.items()
        if values.get("verdict") == "scored"
    }
    current_scored = {
        symbol
        for symbol, values in current_state.items()
        if values.get("verdict") == "scored"
    }

    newly_qualified = [
        {
            "ticker": symbol,
            "prior_verdict": (
                prior_state.get(symbol, {}).get("verdict")
                if symbol in prior_state
                else None
            ),
        }
        for symbol in sorted(current_scored - prior_scored)
    ]
    newly_dropped = []
    for symbol in sorted(prior_scored - current_scored):
        current = current_state.get(symbol)
        if current is None:
            current_verdict = "absent"
            reason = "ticker absent from current state"
        else:
            current_verdict = current.get("verdict")
            reason = current.get("reason")
        newly_dropped.append(
            {
                "ticker": symbol,
                "current_verdict": current_verdict,
                "reason": reason,
            }
        )

    return {
        "first_run": False,
        "newly_qualified": newly_qualified,
        "newly_dropped": newly_dropped,
        "unchanged": sorted(prior_scored & current_scored),
    }
