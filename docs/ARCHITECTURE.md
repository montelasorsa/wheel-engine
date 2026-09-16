# Architecture — Wheel Engine

A deterministic weekly options-wheel screener. It fetches a universe, freezes it
to disk, scores the frozen copy against a written rule set, renders a report and
mails it — unattended, every Sunday morning.

**The one idea everything else follows from:** isolate nondeterminism at the
edge and convert it into a fixed input. One layer talks to the network. Every
layer after it is a pure function of what that layer wrote down.

---

## The layers, and where the lines sit

```
  Layer 0   src/wheel_mcp/    acquisition — the ONLY code that imports a provider
                │
                │  writes JSON snapshots to WheelOps/snapshots/
                ▼
  Layer 1   src/wheel/        rules engine — pure, offline, rule-mapped
                │
                │  writes weeks/YYYY-MM-DD.md + .html
                ▼
  Layer 3   the operator      sole execution authority (thinkorswim)
```

Layer 2 — decision support — **was retired on 2026-09-08** (`c0d43ec`). The
numbering is kept rather than closed up: the Constitution and Source Brief cite
these layer numbers, and renumbering them to make a diagram tidy would break
every citation. See [DECISIONS.md](DECISIONS.md) for the reasoning; the short
version is that evaluating judgment is the operator's work, not the tool's.

**A recommendation that cannot cite a rule ID is a bug.** Rule IDs are
`ST-*` (source methodology) or `AL-*` (AdVenture Labs additions), and every one
is defined in `governance/SOURCE-BRIEF.md`. Code never invents one.

### Why the boundary holds

Not by convention — by test. `tests/test_provider_isolation.py` walks every
file under `src/`, and a provider import found outside `src/wheel_mcp/` fails
the suite. It also asserts the scan still detects the import where it *is*
allowed, so the check cannot rot into a no-op that always passes.

---

## Layer 0 — acquisition (`src/wheel_mcp/`)

| Module | Responsibility |
|---|---|
| `universe_source.py` | Enumerate the universe from the CBOE options directory |
| `yahoo.py` | The network edge: paced, retrying fetches. The one provider import |
| `info_cache.py` | The Stage 1 quote-metadata cache |
| `acquire.py` | Two-stage scan: cheap Stage 1, then deep Stage 2 snapshots |
| `snapshot_writer.py` | Build and write the contract snapshot Layer 1 reads |
| `enrich_fetch.py` | Fetch `info` for top monitored names after the screen |
| `fmp.py` | Null-fill fallback — **disabled by default** |

**Universe: CBOE, not an index.** Index membership correlates with optionability
but does not decide it, and a name without listed options cannot be wheeled at
all. ~5,300 names, published daily as CSV, cached to `WheelOps/universe/`.

**Two-stage fetch.** A deep snapshot costs 5 provider calls. Spending them on
names rejected on price alone costs ~20 minutes and learns nothing, so Stage 1
is a cheap metadata scan that applies the disqualifiers a single `info` call can
answer — including **AL-SEL-07**, the ETF structural screen (`d1a8fb6`), which
sits at Stage 1 so a structured product costs zero deep calls.

**The Stage 1 cache is keyed by ISO week** and reads the current week and the
previous one. Two runs in the same ISO week are minutes apart rather than hours;
the first run after a gap is cold. On 2026-08-16 a cold run took ~4h45m across
5,217 Stage 1 fetches.

**FMP is disabled.** `providers.fmp_enabled` defaults to false and the local
config has no `providers` block. It was readmitted 2026-08-11 as a bounded
null-fill over four allowlisted fields — never primary, never parallel, key from
`.env` — but in practice it is off, and names with null hard-gate fields fail
closed instead. The allowlist is pinned by `tests/test_fmp.py::AllowlistTests`;
widening it is a governance decision, not a code change.

---

## Layer 1 — the rules engine (`src/wheel/`)

Pure and offline-testable. Imports no provider, makes no network call, and the
whole suite runs in under a second.

| Module | Responsibility | Rules |
|---|---|---|
| `snapshot_schema.py` | The Layer 0 → Layer 1 contract | — |
| `snapshot.py` | Normalized underlying data | — |
| `universe.py` | Stage 1 filtering | AL-SEL-07 |
| `gates.py` | Hard gates — binary, disqualifying | ST-SEL-01…04 |
| `scorers.py` | Rule-mapped verdicts from a snapshot | ST-SEL-* |
| `scoring.py` | 0–100 continuous scores, weighted composite | ST-SEL-05/06/10/11/12 |
| `flags.py` | Informational only, never disqualifying | ST-ENT-05 |
| `monitored.py` | The monitored tier and week-over-week movement | AL-SEL-02/03 |
| `enrich.py` | Shape provider `info` into the enrichment contract | — |
| `screen.py` | Composition root: snapshots → scores → report |  — |
| `week_report.py` | Scored snapshots → markdown | — |
| `render_html.py` | Frozen week → static HTML | — |
| `deliver.py` | File copy, then email via Apple Mail | — |
| `notify.py` | Failure notification for the scheduled run | — |
| `applescript.py` | String quoting shared by `deliver` and `notify` | — |

### Gates are binary; ranking is continuous

Five PASS/FLAG/FAIL rules can express only a few dozen distinct composites. The
2026-08-11 run tied 255 of 1,285 names at exactly 100 and broke ties
alphabetically, so the "top 5" was the alphabetically-first five of 111 equals.
Continuous scoring (`1334b59`) replaced the buckets: hard gates stay binary, and
the five ranking rules emit 0–100 from a piecewise anchor table. The same run
then produced 1,171 distinct scores for 1,171 names.

### Null ≠ zero

Zero free cash flow is a real signal and fails ST-SEL-01. *Null* free cash flow
is missing data, and rejecting on it would reject a name on a data gap rather
than on its merits. A candidate with missing fields is scored on the fields it
has and carries a `data_incomplete` flag, which the weekly report surfaces so
the operator can check by hand.

### The golden-file rule (AGENTS.md §4.3)

Any change to a scorer regenerates and diffs goldens **in the same commit**.
This is mechanical, not aspirational: `tests/golden/live/` holds five real
snapshots from the first live acquisition, `expected_scores.json` freezes every
verdict, reason, metric and composite computed from them, and
`test_golden_baseline.py` recomputes and compares exactly. Frozen 2026-08-07
(`aa0c59e`). Regenerate with `--regenerate`; the diff of `expected_scores.json`
is the review artifact.

Hand-built fixtures stay as unit-level edge cases. The live set is the
integration net — it caught that F fails on real negative TTM net income where
the hand-built fixture passes.

---

## Snapshot-then-score

Layer 0 fetches → writes timestamped JSON → Layer 1 reads the snapshot, never a
live call. That single indirection is what buys:

- **Reproducibility.** Same snapshot, same score, every time.
- **Golden-file testing.** Frozen input plus known-correct output.
- **Offline development.** Layer 1 needs no network, ever.
- **Cheap reruns.** A scoring change re-scores existing snapshots in seconds
  instead of re-fetching for hours.

Snapshots are the interchange format. There is no CSV hand-off any more — it
existed for Components B and C, which were Layer 2.

---

## The weekly run

Installed as a launchd user agent, **Sundays at 08:00** local. Installing is a
manual step, always — nothing in the build runs `install-schedule.sh`.

```
wheel-screen → wheel-enrich → wheel-render → wheel-deliver → wheel-backup
```

The first four are fail-stop: a failing step stops the rest, logs a `FAILED`
line and posts a notification naming it. Backup runs outside that wrapper —
by then the report is already delivered, and an unreachable iCloud folder is
not a failed week.

The whole run is held awake by `caffeinate -i` for its duration, because
launchd does not keep the Mac awake for a job it started and a ~5h run would
otherwise pause at the first idle sleep.

**Delivery is two things with different stakes** (`0e4df50`). The file copy to
`~/Downloads/wheel/` is the artifact and the one delivery failure that is fatal.
The email is a convenience: Mail is driven through `osascript` rather than SMTP
because the account is already configured there and the alternative is a
password in a repo that has spent real effort keeping secrets out. Mail being
closed on a Sunday must not take down an otherwise complete run, so a failed
send warns loudly and exits zero.

Operator procedures — install, kickstart, logs, what to do when the email
doesn't arrive — are in [RUNBOOK.md](RUNBOOK.md).

---

## Where data lives

`~/Developer/WheelOps/` is a **sibling** of the repo, never inside it. Not a
`.gitignore` entry — physical separation. A `.gitignore` line can be deleted;
a folder outside the repo cannot enter git by accident.

```
WheelOps/
├── universe/      CBOE directory cache + per-run funnel stats
├── cache/         Stage 1 info cache, keyed by ISO week
├── snapshots/     the frozen provider responses Layer 1 scores
├── weeks/         YYYY-MM-DD.md, .html, monitored.json
├── enrichment/    YYYY-MM-DD/<TICKER>.json
├── logs/          launchd-YYYY-MM-DD.log
├── notes/         per-ticker thesis files, operator-written
└── positions/     trade ledger
```

`config.yaml` is gitignored and holds absolute paths. Secrets live only in
`.env`, never in config, never in a tracked file.

---

## `legacy/`

Quarantined, not deleted — the audit trail is the point. Nothing in `src/`
imports any of it, and no test collects it (`pytest tests/`, never bare
`pytest`, which would try to collect `legacy/` and error).

- The UI layer: `serve.py`, `html_render.py`, `report.html.j2`
- The FMP rescue path: `fmp_adapter.py`, `rescue.py`
- The pre-snapshot pipeline: `pipeline.py`, `diff.py`, `run_state.py`,
  `state_io.py`, `result.py`, `partition.py`, `csv_output.py`
- Retired Layer 2: `decide.py`, `review.py`, `decision_record.py`,
  `skills/`, and `.mcp.json`
- `universe_source_wikipedia.py`, superseded by CBOE

---

## Amendments to the governing documents

Deliberate divergences, recorded so they are not mistaken for drift:

1. **Repo location.** AGENTS.md and build spec §5 place the repo inside iCloud
   at `The Wheel/Development/`. It lives at `~/Developer/wheel-engine` — iCloud
   sync fights git internals. `config.yaml` paths are absolute because
   sibling-relative paths broke on the move.
2. **UI.** The build spec mandates a local serve route. Removed, not deferred:
   an application reopens on taste every time it is examined. A *renderer* —
   a pure function from frozen data with a checkable finish line — is permitted,
   and `render_html.py` is one.
3. **Layer 2.** Retired 2026-09-08. The Constitution's Article XIII and
   §9.3/§9.4 went with it. **Open item:** §13.6's annual re-examination of
   §11.2 has no replacement home.
4. **MCP server.** `wheel_mcp/server.py` was deferred until Layer 2 was live.
   Layer 2 is retired, so there is no longer a date it returns on. `.mcp.json`
   moved to `legacy/` rather than sit in the repo pointing at a module that
   does not exist.
