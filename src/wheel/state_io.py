"""Run-state persistence -- the filesystem edge for the ST-SEL-07 diff.

Split out of `diff.py` so the comparison itself stays a pure function of two
dicts. Everything that touches disk lives here.
"""

from __future__ import annotations

import json
from pathlib import Path

from .diff import RunState


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
    """Return the most recent timestamped state file by filename.

    The zero-padded %Y-%m-%d-%H%M%S stamp makes lexicographic order
    chronological. The filename, not mtime, is the source of truth -- copies
    and syncs rewrite mtimes.
    """

    candidates = sorted(Path(output_dir).glob("run_state_*.json"))
    return candidates[-1] if candidates else None
