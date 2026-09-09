# AGENTS.md — Wheel Engine

**Version 2.0 · 2026-08-04**
Supersedes: AGENTS.md v1.0

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
| Investment Proposal | **v1.1** | `governance/PROPOSAL.md` | Architecture, validation criteria, sizing logic. |
| Distilled Reddit Transcripts | v1.0 | `governance/DISTILLED-TRANSCRIPTS.md` | Primary source. Read-only reference, not cited directly by code. |
| This file | **v2.0** | repo root | Agent instructions. |

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
├── src/wheel_mcp/server.py            MCP server — NOT YET BUILT (expected, not a bug)
├── tests/                             unit + golden-file tests for Layer 1
│   └── golden/                        seeded with README, NO BASELINE FROZEN YET
├── commands/                          entry points: /wheel-screen, /wheel-enrich, /wheel-render, /wheel-deliver
├── skills/                            Layer 2 — SOP procedures, Claude reads these as instructions
├── docs/                              architecture docs, DECISIONS.md
├── governance/                        Constitution, Source Brief, Proposal, Transcripts
├── legacy/                            quarantined UI + FMP code — nothing in src/ imports this
└── config.yaml                        local, gitignored, ABSOLUTE paths
```

**Sibling folder (never in the repo, never in git, not even in .gitignore):**
```
~/Developer/WheelOps/                  operational data — privacy is structural, not discipline
├── snapshots/                         timestamped raw provider responses (Layer 0 writes here)
├── positions/                         trade ledger CSV
├── decisions/                         JSONL decision records (append-only)
├── enrichment/                        YYYY-MM-DD/<TICKER>.json — mechanical company detail
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
| **2 · Decision support** | Present structured options for judgment calls | `skills/`, `commands/` | **Proposes only. Never executes.** Every recommendation cites a rule ID. |
| **3 · Operator** | Approves, rejects, or overrides | Monte (thinkorswim) | **Sole execution authority.** Overrides logged with prediction. |

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

1. **Decision-record schema** — `docs/decision-record-schema.md` — unblocks `wheel reconcile`,
   the eval harness judgment track, and Article XIII amendment sourcing. Pure design.
2. **Layer 0 snapshot format** — define the JSON contract that `yahoo.py` writes and Layer 1 reads.
   This is the interface between layers and must be right before either side is built out.
3. **Layer 1 scorers** — screening filters mapped to ST-SEL-01 through ST-SEL-14 + AL-SEL-02
   through AL-SEL-06. Zone derivation. Sector checks. Each scorer has a golden-file test.
4. **`/wheel-screen` command** — end-to-end: fetch → snapshot → score → produce `weeks/YYYY-MM-DD.md`
5. **`wheel_mcp/server.py`** — MCP wrapper for Layer 2 use (Claude pulls data mid-conversation).
   Deferred until Layer 2 is live — the CLI path through Layer 0 is built first.
6. **Golden-file baseline freeze** — needs a real full-universe run to produce.

---

## §6 Tech stack

| Component | Technology | Note |
|---|---|---|
| Core (Layer 1) | Python package, `src/wheel/` | No external dependencies except stdlib + standard data libs |
| Provider (Layer 0) | yfinance | Market data. **Primary and first, always.** Schwab API is the Phase 4 upgrade. |
| Fallback (Layer 0) | FMP | **Null-fill only, added 2026-08-11.** Consulted only for fields yfinance returned null on, only for the four in `wheel_mcp.fmp.FILLABLE_FIELDS`, only when a key is present. ~50 requests/run. Never parallel, never primary. Key from `.env`, never from config. |
| Universe (Layer 0) | CBOE equity options symbol directory | **Second source, added 2026-08-11.** Enumeration only — CBOE listing is not a quality filter. ~5,300 names, published daily as CSV. Cached to `WheelOps/universe/`, fetched at most once a day, reused stale on fetch failure with a loud warning. |
| Data format | JSON snapshots, JSONL decisions, CSV positions, Markdown output | All human-readable, all diffable |
| Testing | pytest, golden files | Layer 1 tests run < 1s with no network |
| CLI | Python entry points or shell scripts in `commands/` | No web server, no Flask, no UI |
| PDF generation | pandoc + wkhtmltopdf (governance docs only) | Not used for operational output |

**Explicitly removed (not deferred):**
- Flask / serve.py / HTML reporting — UI doesn't converge
- Any direct API call from Layer 1 — provider isolation is structural
- **FMP as a primary or parallel source** — it is a bounded null-fill fallback and
  nothing else. The 2026-08-03 removal was total; 2026-08-11 readmits it under four
  constraints (allowlisted fields, null-only trigger, key in `.env`, mixed-source
  snapshots self-identify). Widening the allowlist is a governance decision, pinned
  by `tests/test_fmp.py::AllowlistTests`.

---

## §7 What not to do

1. **Do not add a UI.** Output is markdown files and CSV. If a presentation layer is ever wanted,
   it is a *renderer* (pure function from frozen data to document), not an application.
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

---

## §9 Open gaps affecting the build

From Source Brief v2.0 Part IV. Each one bounds a claim in the code.

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

Decisions made in conversation that aren't yet in governance docs. Newest first.

| Date | Decision | Rationale | Supersedes |
|---|---|---|---|
| 2026-08-XX | **Retired Layer 2 decision-support.** Screener is now the sole product. Constitution Article XIII removed. Article IX §9.3/§9.4 removed | The decision log and the calibration harness were built to make judgment measurable, but evaluating them is the operator's work, not the tool's. A screener that runs unattended every week is a product; a decision log that needs a quarterly sit-down to mean anything is a second product wearing the first one's clothes. `/wheel-decide`, `/wheel-review`, and their modules move to `legacy/` intact — retired, not deleted, because the audit trail is the point | AGENTS.md §1 objectives 3 and 4; §5 build-order steps 5 and 6; Constitution Article XIII and §9.3/§9.4/§9.5; AL-OPS-05 marked retired in the Source Brief. **Open item:** §13.6's annual re-examination of §11.2 went out with Article XIII and has no replacement home |
| 2026-08-16 | **AL-SEL-07 minted: ETF structural screen**, promoted into Source Brief v2.1 rather than logged here alone | The 2026-08-13 run filled all five Zone 1 slots with derivative-income ETFs (COYY 386%, TSYY 201%, YBTC 81%, BITY 57%, BAGY 38%). Option-premium distributions read to ST-SEL-06 as extraordinary dividends and structural NAV decay reads to ST-SEL-12 as a discount from the high, so the screen ranked capital destruction highest. Three Stage 1 disqualifiers — issuer pattern, 20% yield ceiling, null sector — bypassed by `universe.include`. Applied before the deep snapshot so a structured product costs zero provider calls. The ID went into the Source Brief because the code emits it as a citation, and §7.4 forbids citing a rule that has no definition | The 2026-08-11 note that "minting AL-SEL-07 would need a Source Brief amendment" — that amendment is now made |
| 2026-08-11 | **FMP readmitted as a bounded null-fill fallback** over four allowlisted fields | The 2026-08-03 removal was right about the general case and §4.4 is unchanged, but a hard gate reading CANNOT_EVALUATE fails closed — a null `net_income_ttm` rejects a name on a data gap, not on its merits. Measured residual: 17 of 1,285 names, ~50 requests/run | "FMP fully removed" (2026-08-03); "FMP removal confirmed" (2026-08-04); the FMP gap-fill argument in the 2026-08-06 null-handling row |
| 2026-08-11 | Universe comes from the **CBOE options symbol directory**, not S&P index constituents | Index membership correlates with optionability but does not decide it, and a name without listed options cannot be wheeled at all. Measured on the 2026-08-11 run: 34 screened names had no CBOE-listed options, including the top-ranked monitored name. Universe 1,506 → 5,334 | S&P 500/400/600 scraping (moved to `legacy/universe_source_wikipedia.py`) |
| 2026-08-11 | Screener sources from a broad universe, not a hand-picked watchlist | A screener that ranks a list you already chose inverts its purpose | `watchlist` config key |
| 2026-08-11 | Two-stage fetch: cheap scan then deep snapshot | A deep snapshot is 5 provider calls; spending it on names rejected on price alone costs ~20 min and learns nothing | Single-stage acquire |
| 2026-08-11 | ST-SEL-01 split: only both-negative fails; one negative flags | "Profitable company with solid cash flow" is two criteria. A write-down with cash still coming in is a question, not a rejection | Single-gate ST-SEL-01 |
| 2026-08-11 | Monitored tier replaces the thesis-required list; AL-SIZ-03/04 scoped to thesis-backed names and open positions | At 200 names every week clusters, so an unscoped flag means nothing; a full list is a phone book, not a screen | Full-list output |
| 2026-08-11 | **Continuous scoring replaces verdict buckets.** Gates stay binary; the five ranking rules emit a 0-100 score from a piecewise anchor table | Five PASS/FLAG/FAIL rules can express only a few dozen composites: the 2026-08-11 run tied 255 of 1,285 names at exactly 100 and broke ties alphabetically, so the monitored "top 5" was the alphabetically-first five of 111 equals. Now 1,171 names, 1,171 distinct scores | Verdict-bucket composite; ST-SEL-10's 50-80% flag band; ST-SEL-12's 10% near-high flag |
| 2026-08-11 | Cash-flow strength scored under **ST-SEL-01**, not a new rule ID | The rule is "profitable company with solid cash flow" -- the gate answers the sign, the score answers the degree. Minting AL-SEL-07 would need a Source Brief amendment for something already in scope (§7.4) | — |
| 2026-08-06 | ST-SEL-10 split: hard gate >80% vol, flag 50-80%, pass <50% | Proxy data too approximate for hard rejection near ~50%; 80%+ is unambiguous | Single-threshold gate — **flag band superseded 2026-08-11**: 50% is now a curve anchor, not a verdict boundary |
| 2026-08-06 | Graceful null handling in scorers: degrade, don't crash; null ≠ zero | Missing data is a scorer problem, not a source problem | FMP gap-fill argument — **partially superseded 2026-08-11**: null handling stays the rule, but the 1.3% residual is now filled rather than failed closed |
| 2026-08-06 | Legacy gates.py superseded by snapshot-contract scorers; remove in single dedicated commit after all 13 built | Two implementations during port is known state; cleanup is one atomic commit | — |
| 2026-08-04 | Yahoo sector labels authoritative at pilot scale | 3–5 names don't need GICS precision; consistency > accuracy at this n | G-11 partially closed |
| 2026-08-04 | yfinance is Layer 0 provider; Schwab API is Phase 4 upgrade | Snapshot boundary makes provider low-stakes; yfinance covers 9/10 data points | FMP removal confirmed — **amended 2026-08-11**: yfinance is primary and first; FMP fills its nulls |
| 2026-08-04 | Plugins (finance, S&P) live at Layer 2, not Layer 0 | Plugins operate inside Claude context; cannot be snapshotted or batch-run | Architecture clarified |
| 2026-08-04 | G-14 deferred; start accumulating IV snapshots now | IV Rank needs ~26 weeks of history; source doesn't use it | AL-ENT-01 unenforced |
| 2026-08-03 | UI removed, not deferred | UI doesn't converge; output is files | Flask/serve.py cut |
| 2026-08-03 | FMP fully removed | No adapter, no rescue path | FMP cut — **superseded 2026-08-11** by the bounded fallback |
| 2026-08-03 | Snapshot-then-score is architectural | Makes golden-file testing and reproducibility possible | — |
| 2026-08-03 | WheelOps as sibling to repo | Privacy by geometry, not by .gitignore | — |
| 2026-08-03 | Repo moved to ~/Developer/wheel-engine/ | iCloud sync fights git internals | — |
