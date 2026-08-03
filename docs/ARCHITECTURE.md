# Architecture — Wheel Engine

Plugin surface, MCP data boundary, deterministic core. Written during the reorg
that replaced the "Python package + local HTML/Flask UI" shape.

## The three layers, and where the line sits

```
  /wheel-engine:*  skills      ← invocation surface (an LLM is here)
         │
         ▼
  src/wheel/       core        ← Layer 1: deterministic, rule-mapped, pure
         │
         ▼
  src/wheel_mcp/   MCP data    ← the only code that talks to a provider
```

**The plugin is an invocation surface, not a decision layer.** AGENTS.md §4
states Component A is pure Layer 1 with no LLM inference. Wrapping it in a
Claude Code plugin puts an LLM in front of the screen, so the boundary is now
enforced in two places rather than assumed:

- Every score, gate, and flag is computed in `src/wheel/` by pure functions of
  input data and the rule table. No model inference participates in a verdict.
- The three operator-triggered skills set `disable-model-invocation: true`, so
  Claude cannot invoke them on its own. Selection stays operator-initiated.

A recommendation that cannot cite a rule ID is a bug, not a feature.

## Core (`src/wheel/`)

Pure and offline-testable. Imports no data provider — `import yfinance` appears
nowhere in this package, which is what keeps the 44-test suite runnable with no
network.

| Module | Responsibility | Rules |
|---|---|---|
| `snapshot.py` | `TickerSnapshot` + all provider-response normalization | — |
| `gates.py` | Hard gates F1–F4, F9 | ST-SEL-01…04 |
| `partition.py` | Split evaluated tickers into passed / fitness-fail / missing-data | — |
| `scoring.py` | Score filters F5–F8, F2 margin, weighted composite | ST-SEL-05/06/10/11/12 |
| `flags.py` | F10 earnings proximity — flag only, never disqualifying | ST-ENT-05 |
| `diff.py` | Pure change-vs-last-run comparison | ST-SEL-07 |
| `state_io.py` | Run-state persistence (the filesystem edge for the diff) | — |
| `run_state.py` | Assemble one run's verdicts, attach flags, diff, persist | — |
| `result.py` | `PipelineResult` — one run assembled for consumers | — |
| `csv_output.py` | The 33-column CSV interchange | — |
| `pipeline.py` | Composition root: config → fetch → gate → score → flag → diff | — |

## MCP boundary (`src/wheel_mcp/`)

`yahoo.py` owns pacing (`RequestThrottle`), bounded retries, and the provider
import. It hands raw responses to `wheel.snapshot.build_ticker_snapshot` and
holds no screening rule.

The MCP protocol wrapper (`wheel_mcp/server.py`, referenced by `.mcp.json`) is
**not implemented yet** — this reorg moved the fetch code to the boundary where
that server will sit. `/plugin` will report the server as failing to start until
it exists.

## CSV is interchange, not presentation

The CSV is the documented hand-off to Components B and C. It survived the UI cut
for that reason; the HTML report did not.

**Breaking change: 34 → 33 columns.** `fmp_rescued_fields` was dropped with the
FMP rescue path. No downstream consumer existed at the time of the change. If
provenance tracking is needed again, it gets designed against the real MCP
interface rather than restored in its FMP-shaped form.

## What was cut, and why it is still on disk

`legacy/` holds the quarantined UI layer (`serve.py`, `html_render.py`,
`report.html.j2` and their 25 tests), the FMP rescue path (`fmp_adapter.py`,
`rescue.py` and their 10 tests), and the one-off Step 8 audit script. Nothing in
`src/` imports any of it. It is kept only so the operator can verify nothing
needed was lost before deleting.

## Amendments to the governing documents

This architecture contradicts documents that are still authoritative elsewhere.
These are deliberate amendments, recorded so they are not mistaken for drift:

1. **UI removal.** AGENTS.md §5 and build spec §1.4/§5 mandate static HTML plus
   a local serve route. Spec Step 7 was built, tested, and passing — it is
   superseded, not skipped.
2. **Repo location.** AGENTS.md and spec §5 place the repo in
   `The Wheel/Development/` inside iCloud. It now lives at
   `~/Developer/wheel-engine`, and `config.yaml`'s paths are absolute because
   sibling-relative paths broke on the move.
3. **Layer boundary.** See the top of this document. A plugin surface in front
   of Layer 1 needs the explicit statement it now has.
4. **Component scope.** AGENTS.md §2 restricts work to Component A.
   `/wheel-engine:wheel-decide` and the decision-log SOP are Component C
   surface; the plugin spans A and C.
5. **Data sources.** FMP is cut outright rather than kept dormant, superseding
   the `RESCUE_ENABLED` guidance in AGENTS.md §6. Market data comes from one
   source, through MCP.
6. **Tech stack.** Jinja2, Flask/`http.server`, `python-dotenv`, and `requests`
   leave the core with the UI and FMP. MCP is added and needs to be reflected
   in the approved-stack list.
