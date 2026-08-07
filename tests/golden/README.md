# Golden files — two sets, two jobs

## `tests/golden/*.json` — hand-built unit fixtures

Constructed snapshots with *chosen* edge cases: a fully-populated compliant
equity (F as it was drafted, not as it trades), an ETF with the entire
issuer-dependent half null (the ST-SEL-08 branch), a high-volatility rejection
(APLD, the Source Brief's own counterexample), and a flag-zone name (MARA).
They exercise specific branches and stay stable by design — edit one only to
add a deliberate new edge case.

## `tests/golden/live/` — REAL-DATA regression baseline (§5.8)

Actual Layer 0 output from the 2026-08-06 acquisition run, copied verbatim
from `WheelOps/snapshots/`. These are market snapshots, not operational data —
no positions, no decisions, no thesis content. `expected_scores.json` freezes
every verdict, reason, metric, composite, and classification the Layer 1
scorers produced for them.

`tests/test_golden_baseline.py` recomputes and compares exactly. Per
AGENTS.md §4.3, **any commit that changes scorer behavior regenerates the
baseline in that same commit**:

    PYTHONPATH=src python tests/test_golden_baseline.py --regenerate

The diff of `expected_scores.json` is then the review artifact: it shows
precisely which verdicts moved, on real inputs, and why.

Notable facts these snapshots pin (from the live run): F rejected on negative
TTM net income — real data disagreeing with the hand-built fixture is exactly
why both sets exist; and AL-SIZ-04 flagging F/KO/T all reporting in week
2026-W43 across three different sectors.
