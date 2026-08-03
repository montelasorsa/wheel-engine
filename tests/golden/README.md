# Golden regression baseline

Frozen inputs and expected outputs from one known-good full-universe run: the
end-to-end check the unit suite cannot give.

**Empty on purpose.** Populating it requires a real 466-ticker run, which this
structure-only reorg did not perform. To create the baseline: run the pipeline,
then freeze the snapshots alongside the resulting composites and verdicts so a
later refactor can be proven behaviour-identical rather than merely green.
