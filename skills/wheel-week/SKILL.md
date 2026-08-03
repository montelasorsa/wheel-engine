---
description: Run the weekly Wheel screen over the configured universe and present ranked candidates for operator review.
disable-model-invocation: true
---

# /wheel-engine:wheel-week

Operator-triggered. Runs the deterministic screen and reports what changed.

**Scaffold — the workflow body is not written yet.** Intended shape:

1. Run the screen over the configured universe via `wheel.pipeline.run_pipeline`.
2. Report the ranked survivors, the ST-SEL-07 change-vs-last-run diff, and the
   missing-data and fetch-error buckets.
3. Surface F10 earnings proximity per `ST-ENT-05` as a flag, never a filter.

Scoring is deterministic and happens in `src/wheel/`. This skill presents the
result; it must never re-rank, re-score, or select a name. Per AGENTS.md §4 the
operator decides — `disable-model-invocation: true` keeps this operator-triggered.
