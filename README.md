# Wheel Engine

A governed, deterministic screening system for the options Wheel strategy,
built to stay correct under adversarial conditions: data providers that
rate-limit, time out and return nulls; candidates that rank highest precisely
because they are broken; weekly runs nobody is watching; and an operator whose
incentive after a bad week is to bend the rules.

Each run scores ~5,300 optionable names from the CBOE options symbol directory
against a written rule set and produces a ranked weekly report. Every verdict
cites a rule ID defined in the governance documents. **The tool proposes; the
operator decides.** Nothing executes a trade, and a recommendation that cannot
be mapped to a rule ID is a bug.

Module 1 of AdVenture Labs.

## Architecture: trust boundaries

The design is organized around two boundaries, and both are enforced by tests,
not by convention.

**The snapshot boundary.** Layer 0 fetches market data and writes it as
timestamped JSON snapshots. Layer 1 scores those snapshots and never makes a
live call. Every source of nondeterminism — the network, provider quirks, the
clock — is confined to the edge and frozen into a fixed input, so everything
downstream is a pure function of the snapshot:

- the same snapshot produces the same score, every time;
- a scoring change is reviewed as a diff against frozen golden files, and a
  scorer change that does not regenerate them in the same commit is incomplete;
- Layer 1 is developed and tested entirely offline.

**Provider isolation.** No provider import (`yfinance`, `requests`,
`curl_cffi`, `dotenv`, …) may appear outside `src/wheel_mcp/`.
`tests/test_provider_isolation.py` walks every file under `src/` and fails the
suite on a violation, and it asserts the scan still finds the import where it
*is* allowed, so the check cannot rot into a no-op. `dotenv` is on the list
because a module that can read an API key is a module that can make a call:
Layer 1 sees snapshots, never credentials.

**Data and secrets stay out of the repo by construction.** Operational data
(snapshots, positions, weekly reports, notes) lives in a sibling folder,
`~/Developer/WheelOps/`. A folder outside the repo cannot enter git by
accident; a `.gitignore` line can be deleted. `tests/test_secrets_hygiene.py`
scans every tracked file for a credential assignment and proves its own scan
would catch one.

| Layer | Where | Boundary rule |
|---|---|---|
| 0 · Acquisition | `src/wheel_mcp/` | Fetch and write snapshots. No interpretation. The only place a provider is imported. |
| 1 · Rules engine | `src/wheel/` | Pure function of the snapshot. Gates are binary; ranking is a continuous 0–100 score. Missing data is flagged, never read as zero. |
| 3 · Operator | a person | Sole execution authority. |

Layer 2, decision support, was retired on 2026-09-08. Its number is kept
because the governance documents cite layers by number.

The weekly run is one chain:

```
wheel-screen → wheel-enrich → wheel-render → wheel-deliver → wheel-backup
```

Stage 1 is a cheap scan that rejects names on price and structure before a
five-call deep snapshot is spent on them. A failing step stops the run and
posts a notification naming itself; backup runs last and cannot fail a week
whose report is already delivered. Full detail is in `docs/ARCHITECTURE.md`.

## Governance

The rules live in versioned documents, not in code, and when code and the
Constitution disagree, the Constitution wins.

| Document | Role |
|---|---|
| `governance/CONSTITUTION.md` | Binding rules: capital, selection, entry, management, assignment, the kill switch, and how the rules themselves may change. |
| `governance/SOURCE-BRIEF.md` | Every rule ID — `ST-*` from the source methodology, `AL-*` added here — with its definition, rationale and known gaps. |
| `governance/PROPOSAL.md` | The investment case: architecture, validation criteria, sizing, and the objections it has to answer. |

Rules change only by written amendment under Constitution Article X: on a
fixed quarterly cadence, never on the day a change is wanted, never while a
position is at a loss, and a rule may be loosened only with evidence that it
was wrong. Decisions not yet written into governance are logged with their
rationale in `docs/DECISIONS.md`.

**Worked example: AL-SEL-07.** The 2026-08-13 run filled every Zone 1 slot with
derivative-income ETFs yielding 38% to 386%. Option-premium distributions read
as extraordinary dividends and structural NAV decay read as a discount from
the high, so the screen ranked capital destruction highest. The fix was not a
quiet patch: a new rule, AL-SEL-07 (an ETF structural screen at Stage 1), was
written into the Source Brief in the same commit as the code, because code may
not cite a rule that has no definition.

## Status

- **Screener: complete.** Snapshot contract, Layer 1 scorers covering 27 rule
  IDs, the `/wheel-screen` pipeline, and a golden baseline frozen from the
  2026-08-06 live run.
- **Weekly schedule: built and tested.** A launchd agent runs the full chain on
  Sundays at 08:00. Installing it is a deliberate manual step.
- **MCP server** for pulling data mid-conversation: deferred indefinitely.
- **Layer 2 decision support:** retired 2026-09-08, preserved in `legacy/` as
  an audit trail.
- **Cash management and position tracking:** not built. The screener reads the
  operator's position ledger; nothing in the repo maintains it yet.
- **Open gaps** that bound what the code can claim, such as IV Rank needing
  ~26 weeks of history before AL-ENT-01 can be enforced, are tracked in
  `AGENTS.md` §9.

## Setup

Requires Python 3.12 or later: the pinned numpy has no build for 3.11.

```bash
git clone https://github.com/montelasorsa/wheel-engine.git && cd wheel-engine
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config/example.yaml config.yaml   # edit paths; config.yaml is gitignored
cp .env.example .env                 # only needed if the FMP fallback is enabled
```

## Run

```bash
commands/wheel-screen               # full run: fetch + score (hours on a cold cache)
commands/wheel-screen --score-only  # re-score existing snapshots (seconds)
commands/wheel-render               # weekly artifacts → portable HTML
```

The weekly schedule is installed manually with `scripts/install-schedule.sh`.
See `docs/RUNBOOK.md`.

## Test

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

500 tests and 82 subtests, about a second, no network. The suite is verified
from a clean clone on Python 3.12.

Pass `tests/` explicitly: `legacy/` is quarantined and doesn't import cleanly.
A scorer change regenerates the golden baseline in the same commit:

```bash
PYTHONPATH=src .venv/bin/python tests/test_golden_baseline.py --regenerate
```

## Documentation

| Need | File |
|---|---|
| Agent instructions and project rules | `AGENTS.md` |
| How the system works | `docs/ARCHITECTURE.md` |
| Why a choice was made | `docs/DECISIONS.md` |
| Operating the schedule | `docs/RUNBOOK.md` |
| Snapshot contract (Layer 0 → Layer 1) | `docs/snapshot-schema.md` |
| Binding rules (version of record) | `governance/` |

## How this was built

Built with [Claude Code](https://claude.com/claude-code) as the implementation
agent. `AGENTS.md` is its operating contract: the layer boundaries, the
golden-file rule, the ban on inventing rule IDs, and the instruction to verify
results in a terminal rather than trust a self-report. The decisions — the
rule set, the architecture, what to retire — were the operator's, and each is
recorded with its rationale in `docs/DECISIONS.md`. The tests and golden-file
diffs are the check on the agent's work.

## License

Not yet licensed. Published for review.
