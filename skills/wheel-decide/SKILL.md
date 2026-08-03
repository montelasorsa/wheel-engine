---
description: Walk the operator through a single position decision (open, roll, close, or take assignment) with rule IDs and reasoning attached.
disable-model-invocation: true
---

# /wheel-engine:wheel-decide

Operator-triggered. Component C surface — the judgment layer.

**Scaffold — the workflow body is not written yet.** Intended shape:

1. Take a ticker or open position as `$ARGUMENTS`.
2. Present the situation and the available actions, each tagged with its rule ID.
3. Record the operator's decision and their stated reasoning to the decision log.

Hard boundary, per AGENTS.md §4: this presents options and reasoning. It never
selects, opens, closes, rolls, or sizes a position. The roll decision in
particular depends on operator conviction and cannot be automated.
