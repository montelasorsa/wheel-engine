# AGENTS.md — AdVenture Labs / Wheel Strategy

> Persistent context for coding agents (Codex, Claude Code, or any assistant) working in this repo.
> Read this fully before writing or changing code. It encodes decisions made across weeks of design
> work; deviating from it silently is the primary failure mode to avoid.

---

## Repo location, folder layout, and environment (READ BEFORE ANYTHING)

This repo lives inside an iCloud-synced Documents tree. The project is organized into sibling
folders under `.../Projects/Active/The Wheel/`:

```
The Wheel/
├── WheelGovernance/   ← BINDING strategy docs (Source Brief, Constitution, Engine Proposal)
├── Research/          ← source synthesis / brainstorming (Distilled Transcripts)
├── Development/       ← THIS REPO lives here (code, AGENTS.md, screener spec)
└── WheelOps/          ← runtime OUTPUT folder (screener runs, logs, CSV/HTML history)
```

**Path references from code:**
- Governance docs (binding rules): `../WheelGovernance/`
- Research (source material): `../Research/`
- Run outputs the code writes: `../WheelOps/` (never write outputs into the repo itself)

Use a config value for these base paths (see §5) rather than hard-coding absolute paths, so the
repo stays portable. Relative-to-repo-root defaults should match the tree above.

### iCloud + Python virtualenv — mandatory rule

Because this repo sits in iCloud Drive, **never create the Python virtual environment inside the
repo or anywhere under the iCloud-synced Documents tree.** venv/dependency folders churn thousands
of small files that iCloud will fight to sync, causing corruption and "file in use" errors.

- **Create and use the venv at a non-synced location: `~/.venvs/wheel-screener`.**
  - Create: `python3 -m venv ~/.venvs/wheel-screener`
  - Activate: `source ~/.venvs/wheel-screener/bin/activate`
- Add `venv/`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, and any local data caches to
  `.gitignore`.
- If you ever find a venv or `node_modules` inside the repo, stop and flag it — it should be moved
  out, not committed.

---

## 0. Read this first — how to behave in this repo

- **Do exactly what the current task asks. Do not expand scope.** If a task says "build the screener," do not also build position tracking, options pricing, or a recommendation engine because they seem useful. Scope creep here breaks a deliberate build sequence. If you think something out-of-scope is needed, **say so and ask** — do not build it.
- **When a rule below conflicts with what seems locally convenient, the rule wins.** These rules encode hard-won trading-strategy constraints, not coding preferences. Ask before overriding.
- **Cite the rule.** This project runs on a rule-ID system (`ST-*`, `AL-*`). When code implements a trading rule, reference the rule ID in a comment. Traceability is a core requirement, not a nicety.
- **The tools show and recommend. They never decide or execute.** No component in this project auto-selects tickers, auto-rolls positions, auto-places orders, or takes any irreversible trading action. Every such decision is surfaced to the human operator with reasoning attached. This is non-negotiable and explained in §4.
- **Ask before adding dependencies, hitting paid APIs, or introducing scheduling/automation.** Especially: **do not integrate any live options-data provider or broker API** unless the current task explicitly says to. Component A uses free data only (§5).

---

## 1. What this project is

AdVenture Labs is a personal venture studio. **Module 1** is "The Wheel Engine": a tooling suite
that supports running the **Wheel options strategy** (cash-secured puts → covered calls on
assignment) on US equities, as a systematic personal income sleeve.

The owner (Monte) is deploying $9–15K of his own capital after a validation period. The immediate
job of this repo is **not to trade** — it is to build the tools that let him **paper trade the
strategy with discipline**, prove it works, and only then connect to a live brokerage (Charles
Schwab). Building the tools and learning the strategy happen in parallel by design.

**This is also an FDE portfolio project.** Code quality, clean scoping, and honest handling of
data limitations matter here beyond just "does it run."

---

## 2. The three-component build — and where we are

The tool is three components, built in strict sequence. **Each earns trust before the next builds
on it.** Do not jump ahead.

```
A. SCREENER        →   C. DECISION LOG      →   B. POSITIONS
(free data)            (paper trades,           (live options data,
which stocks           reasoning + rule-        paywalled — DEFERRED)
qualify?               tagged scenarios)
─────────────          ───────────────          ──────────────
BUILD FIRST            build next               build last
```

- **Component A — Screener (CURRENT FOCUS).** Runs on free fundamental + price data (yfinance).
  Answers: which stocks currently qualify as Wheel candidates, and which held names have stopped
  qualifying? Full spec: `screener-build-spec.md` in this repo. **This is the only component to work on
  unless told otherwise.**
- **Component C — Decision Log (NEXT, not yet).** Sits on paper positions. Surfaces
  scenarios/recommendations with rule IDs and reasoning for the operator to judge. This is where
  the "judgment layer" lives.
- **Component B — Positions (LAST, deferred).** Needs a live options-chain feed (Polygon/ORATS —
  paywalled). Position tracking, net stock cost, moneyness/extrinsic columns. **Do not build or
  scaffold B until A and C are proven and the task explicitly calls for it.** Do not add options
  data providers "to get ready."

---

## 3. The strategy in brief (so code decisions make sense)

The Wheel, as documented by Reddit user ScottishTrader and adapted in our governing docs:

1. Sell cash-secured puts (30–45 DTE, ~0.30 delta) on stocks you'd genuinely be fine owning.
2. Collect premium. Close at 50% of max profit (GTC limit set on fill). Repeat.
3. If a put is challenged (stock hits strike), **roll for a credit** — but only when convinced
   the stock will keep dropping. Rolling is the primary risk control.
4. If a roll can no longer net a credit, take assignment. Then sell covered calls above net stock
   cost until shares are called away. Return to step 1.

**Central truths that shape the tooling:**
- The goal is collecting premium, **not** being assigned. Assignment is rare (2–3/yr) and a last
  resort, not a routine phase.
- **High implied volatility is a RED FLAG, not an opportunity.** Fat premium prices real risk of
  the one failure mode this strategy can't survive: a stock that drops and stays down. The
  screener must *penalize* high volatility, not reward it. (This is counterintuitive; do not
  "fix" it.)
- Hold ~50% of the account in cash reserve at all times. It enables rolling, absorbs assignment,
  and buys recoveries.
- The roll decision depends on operator *conviction* about the stock's path. **This cannot be
  automated** and must not be. Code surfaces the situation; the human decides.

---

## 4. The show/recommend/never-decide boundary (hard rule)

This project has a three-layer architecture. Respect the layer boundaries in all code:

| Layer | What it is | What it may do | What it must NOT do |
|-------|-----------|----------------|---------------------|
| **1. Rules engine** | Deterministic Python, no model inference | Screen, score, compute, filter, flag, construct (unsent) order params | Decide which stock to trade; place orders |
| **2. Decision support** | (Component C) Claude/LLM-assisted, grounded in our rules | Present options + scenarios, each tagged with a rule ID and reasoning | Execute anything; auto-choose; hide its reasoning |
| **3. Operator** | The human | Approve, reject, override (with logged reason) | — |

- **Component A is pure Layer 1.** No LLM calls, no inference — deterministic functions of input
  data and the rule table. Fully auditable, testable against hand-computed expectations.
- Any recommendation surfaced anywhere in the system **must cite a rule ID**. A recommendation
  that can't be mapped to a rule is a bug (it signals drift) and should be flagged as such.
- **Never** write code that selects a ticker, opens/closes/rolls a position, or places/cancels an
  order automatically. Not even behind a flag. Not even "for testing." If a task seems to ask for
  this, stop and confirm with the operator.

---

## 5. Component A — build constraints

Full spec in `screener-build-spec.md` (this repo); that spec is the source of truth. Key guardrails:

- **Free data only.** yfinance for fundamentals, price history, dividends, analyst ratings. **No
  paid options data. No broker API.**
- **IV is proxied, not real, in A.** We lack a live IV feed at this stage, so filter F7
  (volatility quality) uses ~30-day annualized *realized* volatility as a proxy and **must flag
  it as an approximation** wherever it appears in output. The signal direction (penalize high vol)
  is correct; the true IV Rank swaps in only when Component B exists. Do not pull options data to
  "do it properly" — that's B's job.
- **Every filter maps to a rule ID** (F1→`ST-SEL-01`, etc. — see the spec's criteria table).
  Encode the rule ID in code comments and in output.
- **Hard gates vs score filters vs flags** are distinct: gates disqualify, scores rank survivors,
  flags inform without disqualifying (e.g. imminent earnings is a flag, per `ST-ENT-05`, not a
  disqualifier). Keep them cleanly separated in code.
- **Config-driven, not hard-coded.** Universe list, scoring weights, and thresholds live in a YAML
  config the operator edits. Changing a weight must not require touching logic.
- **Deterministic + timestamped.** Same input → same output. **Write all run outputs to `../WheelOps/` (never into the repo).** Save each run timestamped so
  week-over-week changes ("X newly qualified / Y dropped out and why") are computable. That diff is
  the whole point of the screener (operationalizes `ST-SEL-07`).
- **Local-first.** Produces static HTML + CSV, plus a minimal local serve route (phone-viewable on
  LAN). No hosting, no auth, no secrets. Write the data + scoring layers as pure functions so a
  future hosted version reuses them unchanged.

**Validation gate (spec Step 8):** before the screener is trusted, it must agree with the
operator's judgment on ~5 well-known names. If it disqualifies an obviously-good Wheel candidate
or ranks an obvious junk-high-IV stock highly, the rule encoding is wrong — fix it before moving
on.

---

## 6. Tech stack (Component A)

- Python 3.11+
- yfinance (data), pandas + numpy (screening, vol math)
- Financial Modeling Prep (FMP) — Gap-filler for Component A hard-gate fields when yfinance returns null. Never primary. Never cross-validation.
- `RESCUE_ENABLED` defaults to `false`: the initial universe missing-data rate was 2.1% (1.6% after throttling), below the threshold for a paid source. Keep FMP dormant unless a deliberate data-source change enables it.
- lxml — required by yfinance's `get_earnings_dates()` for historical announcement dates; used by Step 8's F5-vs-earnings audit script and (pending C1 refinement decision) potentially by the main pipeline. Not imported by pipeline code until C1 is decided.
- Jinja2 → static HTML report; CSV output
- Minimal Flask route OR `python -m http.server` for local viewing
- YAML config (universe, weights, thresholds, and base paths for governance/research/output folders)
- Local timestamped CSV/parquet for run history

Ask before adding anything beyond this list.

---

## 7. Repo conventions

- Keep the data layer and scoring engine as **pure, testable functions**. Presentation (HTML/serve)
  is a thin separate layer.
- Write a quick test/hand-check for the hard gates and the scoring on at least a couple of known
  tickers as you go — don't wait until the end.
- Comments should explain *why* (and cite the rule ID), not just *what*.
- Prefer clarity over cleverness. This is a portfolio piece; readable beats terse.
- Do not commit secrets or API keys (there shouldn't be any in Component A anyway).

---

## 8. Governing documents (context, not code)

These live in the sibling folders `../WheelGovernance/` (binding) and `../Research/` (source synthesis) and define the strategy the code serves. If a code decision touches a
trading rule, it should be consistent with these:

- **Strategy Constitution v2.1** (`../WheelGovernance/`) — the binding trading rules (return
  regimes, reserve policy, sizing, kill switch, amendment discipline).
- **ScottishTrader Source Brief v2.0** (`../WheelGovernance/`) — every rule with its ID,
  rationale, and provenance. The `ST-*` / `AL-*` vocabulary lives here.
- **Distilled Reddit Transcripts** (`../Research/`) — primary source material.
- **Wheel Engine Proposal v1** (`../WheelGovernance/`) — the strategy's rationale, risk
  framework, and the three-layer architecture this repo implements.
- **Screener Build Spec v1** — `screener-build-spec.md` (this repo root), the source of truth for Component A.

If these documents and this file ever conflict, **stop and ask the operator** — do not silently
pick one.

---

## 9. Quick "don't do this" list

- ❌ Don't build Components B or C while working on A.
- ❌ Don't add options-data providers or broker APIs to Component A.
- ❌ Don't reward high IV / high premium in the screener. Penalize it.
- ❌ Don't write anything that auto-selects, auto-trades, or auto-rolls.
- ❌ Don't hard-code the universe, weights, or thresholds — use config.
- ❌ Don't expand scope because something "seems useful." Ask first.
- ❌ Don't treat the realized-vol IV proxy as the real thing — flag it.
- ✅ Do cite rule IDs. Do keep layers clean. Do ask when unsure.

---

*This file is the durable memory of the AdVenture Labs Wheel project for any coding agent. Keep it
updated as components ship: when Component A is proven, update §2 to point work at Component C.*
