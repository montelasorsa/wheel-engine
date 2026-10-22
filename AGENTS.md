# AGENTS.md — Wheel Engine

**Version 2.2 · 2026-10-22**
Supersedes: AGENTS.md v2.1

---

## §1 What this project is

A personal options trading operations tool for a systematic weekly Wheel workflow.
Owner: Monte. Module 1 of AdVenture Labs.

Two objectives:
1. Stock screening against a written rule set
2. Cash management and position tracking

The tool **proposes**. The operator **decides**. Nothing executes a trade.

---

## §2 Governing documents — version of record

| Document | Version | Location | Role |
|---|---|---|---|
| Strategy Constitution | **v2.1** | `governance/CONSTITUTION.md` | Binding rules. When code and Constitution disagree, Constitution wins. |
| ScottishTrader Source Brief | **v2.1** | `governance/SOURCE-BRIEF.md` | Rule definitions, rationale, gap register. Every rule ID lives here. |
| Investment Proposal | **v1.3** | `governance/PROPOSAL.md` | Architecture, validation criteria, sizing logic. |
| This file | **v2.2** | repo root | Agent instructions. |

The distilled Reddit transcripts are **not in the repo** — the source PDF lives
in `The Wheel/Research/` outside it. Every rule they informed is already written
into the Source Brief, which is what code cites.

**Rule ID convention:** `ST-[DOMAIN]-[NN]` = source methodology. `AL-[DOMAIN]-[NN]` = AdVenture Labs
additions. Domains: FRM, SEL, ENT, ORD, MGT, ROL, ASN, CC, CSH, SIZ, EVT, PER, PHI. The RSK domain
is retired in v2.0 — see Source Brief Appendix B for the crosswalk.

**A recommendation that cannot be mapped to a rule ID is a bug.**

---

## §3 Repository layout

```
~/Developer/wheel-engine/              git repo (NOT in iCloud — same failure class as venvs)
├── AGENTS.md                          this file
├── src/wheel/                         Layer 1 — deterministic rules engine, PROVIDER-FREE
├── src/wheel_mcp/yahoo.py             Layer 0 — ONLY place a provider import (yfinance) lives
├── src/wheel_mcp/server.py            MCP server — NOT BUILT, deferred indefinitely (§5.5)
├── tests/                             unit + golden-file tests for Layer 1
│   └── golden/live/                   BASELINE FROZEN 2026-08-07 (aa0c59e) — §4.3 is mechanical
├── commands/                          entry points: screen, enrich, render, deliver, backup
├── skills/                            SOP procedures Claude reads as instructions (screener only)
├── scripts/                           launchd agent + install/uninstall (manual step)
├── docs/                              ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md, snapshot-schema.md
├── governance/                        Constitution, Source Brief, Proposal
├── legacy/                            quarantined — UI, FMP rescue, pre-snapshot pipeline, Layer 2
└── config.yaml                        local, gitignored, ABSOLUTE paths
```

**Sibling folder (never in the repo, never in git, not even in .gitignore):**
```
~/Developer/WheelOps/                  operational data — privacy is structural, not discipline
├── snapshots/                         timestamped raw provider responses (Layer 0 writes here)
├── positions/                         trade ledger CSV
├── decisions/                         empty — Layer 2 artifact, kept for the retired record
├── enrichment/                        YYYY-MM-DD/<TICKER>.json — mechanical company detail
├── logs/                              launchd-YYYY-MM-DD.log — scheduled run output
├── weeks/                             weekly output markdown (Layer 1 + Layer 2 produce these)
└── notes/                             per-ticker thesis files: <TICKER>.md
```

**Why WheelOps is a sibling:** a folder outside the repo cannot enter git by accident.
A `.gitignore` entry can be deleted. Physical separation cannot.

---

## §4 Four-layer architecture

| Layer | What it is | Implementation | Boundary rule |
|---|---|---|---|
| **0 · Acquisition** | Fetch external data, write to snapshot storage | `src/wheel_mcp/` | **No interpretation.** Fetch and write only. The ONLY place a provider import is allowed. |
| **1 · Rules engine** | Score snapshots deterministically | `src/wheel/` | **Same input → same output.** No model inference. No provider calls. Fully testable offline. |
| **2 · Decision support** | ~~Present structured options for judgment calls~~ | `legacy/` | **RETIRED 2026-09-08** (`38a6e97`). Evaluating judgment is the operator's work, not the tool's. |
| **3 · Operator** | Approves, rejects, or overrides | Monte (thinkorswim) | **Sole execution authority.** |

The layer numbers keep the gap at 2 rather than closing up: the Constitution and
Source Brief cite these numbers, and renumbering to tidy a table would break
every citation. The screener is the sole product — it proposes, and every
recommendation still cites a rule ID.

### §4.1 Snapshot-then-score (architectural, not incidental)

Layer 0 fetches → writes timestamped JSON to `WheelOps/snapshots/` → Layer 1 reads from the
snapshot, never from a live call. This is what makes:
- Runs reproducible (same snapshot, same score, every time)
- Golden-file testing possible (frozen input + known-correct output)
- Offline development possible (no network needed for Layer 1)

**The general principle:** isolate nondeterminism at the edge and convert it into a fixed input.
MCP is the only nondeterministic boundary. Everything downstream is a pure function of the snapshot.

### §4.2 Provider isolation rule

No provider import (`yfinance`, `schwab`, or any future provider) may appear anywhere outside
`src/wheel_mcp/`. This is enforced by test — not by convention, not by code review.

### §4.3 Golden-file rule

Any change to a Layer 1 scorer regenerates and diffs golden files **in the same commit.** A commit
that changes scoring logic without updating goldens is incomplete — the CI equivalent of a test
that was never run.

### §4.4 Graceful null handling

A missing data field in a snapshot does not crash the scorer or silently drop the candidate.
- **Null ≠ zero.** Zero cash flow is a real signal (ST-SEL-01 fails). Null cash flow is missing data.
- A candidate with missing fields is scored on available fields with a `data_incomplete` flag.
- The weekly output surfaces flagged candidates so the operator can check manually.

---

## §5 Build order (dependency-sequenced)

1. **Layer 0 snapshot format** — ✅ **DONE 2026-08-06** (`02c85bf`). The JSON contract that
   `yahoo.py` writes and Layer 1 reads, specified in `docs/snapshot-schema.md`. This is the
   interface between layers and had to be right before either side was built out.
2. **Layer 1 scorers** — ✅ **DONE 2026-08-06** (`02c85bf`, `633278b`). Screening filters mapped
   to ST-SEL-01 through ST-SEL-14 + AL-SEL-02 through AL-SEL-06. Zone derivation. Sector checks.
   Each scorer has a golden-file test. AL-SEL-07, minted 2026-08-16 (`161ee87`), is enforced
   earlier — at the Stage 1 scan in `src/wheel/universe.py`, before a deep snapshot is spent.
3. **`/wheel-screen` command** — ✅ **DONE 2026-08-06** (`02f7be9`). End-to-end: fetch → snapshot
   → score → produce `weeks/YYYY-MM-DD.md`.
4. **Weekly automation — launchd schedule + delivery pipeline** — ✅ **DONE 2026-09-08**
   (`cfadc04`), hardened for an unattended run 2026-09-16 (`9e4d55d`–`56827d3`). `scripts/` holds
   the `com.adventurelabs.wheel-engine` agent and its install/uninstall scripts. Sundays at 08:00:
   screen → enrich → render → deliver → backup. A failing step stops the rest and notifies;
   backup is the exception and cannot fail the run. Installing is manual, always.
5. **`wheel_mcp/server.py`** — MCP wrapper so Claude can pull data mid-conversation.
   **DEFERRED INDEFINITELY.** It was deferred until Layer 2 was live, and Layer 2 was
   retired on 2026-09-08, so there is no longer a date it returns on. `.mcp.json` moved
   to `legacy/` rather than sit in the repo pointing at a module that does not exist.
6. **Golden-file baseline freeze** — ✅ **DONE 2026-08-07** (`87c68c3`). Five live snapshots
   from the 2026-08-06 run, every verdict frozen in `expected_scores.json`. §4.3 is now
   mechanical: regenerate with `--regenerate`, and the diff is the review artifact.

---

## §6 Tech stack

| Component | Technology | Note |
|---|---|---|
| Core (Layer 1) | Python package, `src/wheel/` | No external dependencies except stdlib + standard data libs |
| Provider (Layer 0) | yfinance | Market data. **Primary and first, always.** Schwab API is the Phase 4 upgrade. |
| Fallback (Layer 0) | FMP | **DISABLED.** `providers.fmp_enabled` defaults to false and the local config has no `providers` block, so it does not run. Code retained: readmitted 2026-08-11 as a null-fill over the four fields in `wheel_mcp.fmp.FILLABLE_FIELDS`, never parallel, never primary, key from `.env`. With it off, a null hard-gate field fails closed — ~39 names on the 2026-08-16 run. |
| Universe (Layer 0) | CBOE equity options symbol directory | **Second source, added 2026-08-11.** Enumeration only — CBOE listing is not a quality filter. ~5,300 names, published daily as CSV. Cached to `WheelOps/universe/`, fetched at most once a day, reused stale on fetch failure with a loud warning. |
| Data format | JSON snapshots, CSV positions, Markdown + static HTML output | All human-readable, all diffable |
| Testing | pytest, golden files | `PYTHONPATH=src pytest tests/` — runs in ~1s with no network |
| CLI | Python entry points or shell scripts in `commands/` | No web server, no Flask, no UI |
| PDF generation | pandoc + wkhtmltopdf (governance docs only) | Not used for operational output |

**Explicitly removed (not deferred):**
- Flask / serve.py / HTML reporting — UI doesn't converge
- Any direct API call from Layer 1 — provider isolation is structural
- **FMP as a primary or parallel source** — it is a bounded null-fill fallback and
  nothing else, and it is currently switched off. The 2026-08-03 removal was total;
  2026-08-11 readmits it under four constraints (allowlisted fields, null-only trigger,
  key in `.env`, mixed-source snapshots self-identify). Widening the allowlist is a
  governance decision, pinned by `tests/test_fmp.py::AllowlistTests`. **Turning it back
  on is a config change, not a code change** — set `providers.fmp_enabled: true`.

---

## §7 What not to do

1. **Do not add a stateful UI or web server.** Static HTML rendering from frozen data is a
   renderer (converges, pure function) — that pattern is permitted. Flask, routes, live servers,
   or any UI requiring ongoing state remain prohibited.
2. **Do not import a provider in Layer 1.** If a test needs network, it's testing the wrong layer.
3. **Do not resolve ambiguity with confidence.** When the rule set does not determine an answer,
   the correct output is a stated set of options with tradeoffs — not a recommendation.
   (Constitution §7.6)
4. **Do not invent rule IDs.** If a rule doesn't exist in the Source Brief, the behavior is either
   a gap (document it) or a judgment call (surface it). Never fabricate a citation.
5. **Do not optimize for returns.** Any parameter change adopted to raise expected return is a
   violation of the selection, entry, or sizing discipline. (Constitution §12.1)
6. **Do not put operational data in the repo.** WheelOps is a sibling folder. Snapshots, positions,
   decisions, and thesis files never enter git by any path.
7. **Do not split `git add` from `git commit`.** Always `git add -A && git commit` as one motion.
   A near-miss in v1 left 19 modified files silently unstaged.
8. **Do not trust self-reported results.** Verify against your own terminal before confirming.

---

## §8 Working conventions

- **Verify Claude Code's self-reported outcomes** against your own terminal.
- **When a prerequisite doesn't hold, that's the guardrail working.** Resolve it; don't route around.
- **Copy before delete.** Always.
- **`git add -A` immediately before every `git commit`, always as one motion.**
- **Commit messages reference the build-order step** (e.g. "§5.1: decision-record schema draft").
- **Run tests as `PYTHONPATH=src pytest tests/`.** A bare `pytest` also collects `legacy/`,
  which no longer imports cleanly, and buries real failures in collection errors.

### Where things are written down

| Need | File |
|---|---|
| How the system works | `docs/ARCHITECTURE.md` |
| Why a choice was made | `docs/DECISIONS.md` |
| How to operate the schedule | `docs/RUNBOOK.md` |
| What Layer 0 writes and Layer 1 reads | `docs/snapshot-schema.md` |
| Binding rules | `governance/` — the version of record |

---

## §9 Open gaps affecting the build

From Source Brief v2.1 Part IV. Each one bounds a claim in the code.

| Gap | What it blocks | Priority | Resolution path |
|---|---|---|---|
| **G-6** | Ex-dividend early assignment on covered calls — unspecified | High | Research; no code blocked, but CC scorers are incomplete without it |
| **G-9** | Mid-roll partial fills — undefined | Medium | Operational, not code |
| **G-11** | Sector taxonomy authority — GICS vs Yahoo labels | High | **Decision made:** Yahoo Finance sector labels are authoritative at pilot scale. Revisit at scale. |
| **G-12** | Zone boundary hysteresis | Medium | Design decision owed; blocks AL-SEL-02 edge cases |
| **G-13** | No reference universe for selection quality validation | Accepted | Structural limitation, documented |
| **G-14** | IV Rank source and definition — AL-ENT-01 unenforced | High | Start snapshotting current IV now; compute rank after ~26 weeks of history. AL-ENT-01 deferred. |

---

## §10 Decision log

Moved to [`docs/DECISIONS.md`](docs/DECISIONS.md).

It had outgrown a table — several rationales run to a paragraph, and a
four-column row is the wrong shape for a paragraph. The log is the same
content in the same order, newest first.

**Add new decisions there, not here.** A decision that changes what the code
does or what the project is, made in conversation and not yet written into
`governance/`, belongs in that file. Anything already binding in `governance/`
does not: those documents are the version of record.
