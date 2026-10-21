# Wheel Engine

Deterministic weekly screener for the options Wheel strategy. Module 1 of AdVenture Labs.

It scores a broad universe of optionable stocks against a written rule set and
produces a ranked weekly report. **The tool proposes; the operator decides.**
Nothing here places or recommends a trade without a rule ID behind it, and
nothing executes one.

## How it works

```
wheel-screen → wheel-enrich → wheel-render → wheel-deliver → wheel-backup
```

| Layer | Where | Rule |
|---|---|---|
| 0 · Acquisition | `src/wheel_mcp/` | Fetch from yfinance, write timestamped JSON snapshots. The only place a provider is imported. |
| 1 · Rules engine | `src/wheel/` | Pure function of the snapshot. Same input, same output. Offline and fully tested. |
| 3 · Operator | you | Sole execution authority. |

Every verdict traces to a rule in `governance/SOURCE-BRIEF.md` (`ST-*` for
source methodology, `AL-*` for AdVenture Labs additions). A recommendation that
can't be mapped to a rule ID is a bug.

Operational data (snapshots, positions, weekly output, notes) lives in a
sibling folder, `~/Developer/WheelOps/`, and never enters this repo.

## Setup

```bash
cd ~/Developer/wheel-engine
python3 -m venv .venv
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

The weekly schedule (Sunday 08:00 via launchd) is installed manually with
`scripts/install-schedule.sh`. See `docs/RUNBOOK.md`.

## Test

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q
```

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
