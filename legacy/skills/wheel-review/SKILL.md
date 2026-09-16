---
description: Review closed and open positions against the logged reasoning to check whether the strategy is behaving as designed.
disable-model-invocation: true
---

# /wheel-engine:wheel-review

Operator-triggered retrospective over the decision log.

**Scaffold — the workflow body is not written yet.** Intended shape:

1. Read the decision log and the timestamped run history.
2. Compare what was expected at decision time against what happened.
3. Surface drift: rules cited but not followed, or followed but not working.

Reports only. Any rule change is an amendment the operator makes deliberately
in the governing docs, never a silent adjustment made here.
