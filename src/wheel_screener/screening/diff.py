"""Qualification-state persistence and pure ST-SEL-07 run diffs."""

from __future__ import annotations

import json
from pathlib import Path
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


def load_prior_state(path: str | Path) -> RunState | None:
    """Load one prior state file; a missing path is a valid first run."""

    state_path = Path(path)
    if not state_path.exists():
        return None
    payload = json.loads(state_path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"Run state must be a JSON object: {state_path}")
    return payload


def save_current_state(path: str | Path, state: RunState) -> Path:
    """Atomically persist current state at the IO edge."""

    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n"
    )
    temporary_path.replace(state_path)
    return state_path


def latest_state_file(output_dir: str | Path) -> Path | None:
    """Return the most recent timestamped state file by filename."""

    candidates = sorted(Path(output_dir).glob("run_state_*.json"))
    return candidates[-1] if candidates else None

