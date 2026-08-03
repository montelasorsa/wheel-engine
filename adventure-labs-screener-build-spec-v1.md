# AdVenture Labs — Build Spec: The Wheel Screener

**Deliverable 4a of 8** · Module 1: The Wheel Engine
Component A of 3 (Screener → Decision Log → Positions)
Version 1.0 · July 2026

---

## 0. What this is and where it sits

The Wheel Screener is the first of three components in the AdVenture Labs trading tool. It answers one question on a fixed cadence: **which stocks currently qualify as Wheel candidates, and which held names have stopped qualifying?**

It is the operational form of ScottishTrader's watchlist discipline (`ST-SEL-07`: review every few weeks, cycle names that no longer fit) and the entry gate for everything downstream. It runs on free fundamental and price data — no options-chain feed, no paywall, no blocker.

```
   ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
   │  A. SCREENER│ ──▶ │ C. DECISION  │ ──▶ │ B. POSITIONS│
   │   (this doc)│     │     LOG      │     │  (deferred) │
   │  free data  │     │ paper trades │     │ paid options│
   └─────────────┘     └──────────────┘     └─────────────┘
        built            built next            built last
```

**Explicit non-goals for A:** no options pricing, no live position tracking, no order construction, no automated decisions. A produces a ranked candidate list and a qualify/disqualify verdict per name. That is all. Scope discipline is the point.

---

## 1. Design principles

**1.1 Show and rank; never decide.** The screener outputs candidates with scores and flags. Selection remains the operator's — this is `ST-SEL-09` and `ST-PHI-06`, the willingness-to-own test that only a human can answer. A stock topping the screen is a *candidate for research*, not a buy.

**1.2 Every score traces to a rule.** Each filter maps to a Source Brief rule ID. A stock's verdict is explainable line by line, in the same rule vocabulary as every other document. No black-box composite score.

**1.3 Free data first.** yfinance (Yahoo Finance) covers fundamentals, analyst ratings, price history, and dividends — everything the `ST-SEL` criteria need except live IV. Where a filter wants IV, we approximate from historical realized volatility and flag it as an approximation, deferring the real measure to Component B.

**1.4 Local-first, deploy-later.** Runs as a Python script producing a local HTML report, plus a lightweight local web view. Nothing hosted, no accounts, no secrets. The data layer and scoring logic are written so the eventual hosted version reuses them unchanged — only the presentation layer gets swapped.

**1.5 Deterministic and re-runnable.** Same inputs, same output. A run is timestamped and saved so week-over-week changes in a name's standing are visible — which is precisely the "has this stopped qualifying?" signal `ST-SEL-07` calls for.

---

## 2. The screening criteria (rule-mapped)

Every filter, its data source, its pass condition, and its governing rule. This table *is* the scoring engine's specification.

| # | Filter | Source Brief rule | Data source | Pass condition | Type |
|---|---|---|---|---|---|
| F1 | Profitable / solid cash flow | ST-SEL-01 | yfinance financials | Positive net income (TTM) and positive operating cash flow | Hard gate |
| F2 | Bullish analyst consensus | ST-SEL-02 | yfinance recommendations | Mean rating ≤ 2.5 (1=strong buy … 5=sell) | Hard gate |
| F3 | Price band | ST-SEL-03, SEL-13 | yfinance quote | $10 ≤ price ≤ $50; pilot bias flag if $10–30 | Hard gate |
| F4 | Sub-$10 floor | ST-SEL-04 | yfinance quote | price ≥ $10 | Hard gate |
| F5 | Chart stability | ST-SEL-05 | 1y daily history | No single-day move > 15%; realized vol below universe 75th pctile | Score |
| F6 | Dividend | ST-SEL-06 | yfinance dividends | Pays dividend → bonus; yield surfaced | Score |
| F7 | IV proxy (interim) | ST-SEL-10, SEL-11 | 30d realized vol | Realized vol < ~50% annualized → quality zone; high vol **penalized** | Score + flag |
| F8 | Chart position | ST-SEL-12 | 2y daily history | Not within 5% of 2-year high | Score |
| F9 | Options liquidity | ST-SEL (liquidity) | yfinance option meta | Options exist; open interest present at ~30–45 DTE | Hard gate (basic) |
| F10 | Earnings proximity | ST-ENT-05 | yfinance calendar | Flag if next earnings < 45 days out | Flag only |

**Hard gates** disqualify outright — one failure removes the name. **Score** filters contribute to ranking among survivors. **Flags** are surfaced for operator judgment without affecting pass/fail (an imminent earnings date doesn't disqualify a name, it just means "don't open across it," per `ST-ENT-05`).

### 2.1 The inverted-IV filter (F7) — the one that matters most

F7 encodes the counterintuitive core of the strategy: **high implied volatility is penalized, not rewarded** (`ST-SEL-10`). Because we lack a live IV feed at this stage, we proxy with 30-day annualized realized volatility. A name with realized vol above ~50% loses points; a stable name in the 20–40% range scores well. This is explicitly an approximation — flagged as such in the output — and gets replaced by true IV Rank when Component B brings the options feed online. The direction of the signal is what matters now, and the direction is correct even on the proxy.

### 2.2 Scoring

Survivors of the hard gates receive a 0–100 composite from the score filters, weighted:

| Component | Weight | Rationale |
|---|---|---|
| Stability (F5) | 30% | Gap risk is the failure mode the strategy can't manage — highest weight |
| IV proxy quality (F7) | 25% | The strategy's central selection insight |
| Chart position (F8) | 20% | Entry point materially affects assignment probability |
| Dividend (F6) | 15% | Cushions holds; proxies stability |
| Analyst strength (F2 margin) | 10% | Directional tailwind |

Weights live in a config block, not hard-coded — tuning them is a documented change, and the weighting itself is a hypothesis to revisit once paper-trading data exists.

---

## 3. Inputs and outputs

**Input:** a universe file — a list of tickers to screen. Seeded with a broad liquid US large/mid-cap set (~200–500 names); operator-editable. The screener never invents the universe; it evaluates the one it's given.

**Output, three forms:**

1. **Ranked HTML report** — candidates sorted by score, each row showing every filter's result with pass/fail/flag coloring, the composite, and the earnings flag. Human-readable, saved timestamped.
2. **CSV** — same data, machine-readable, written to `../WheelOps/`, for the eventual hand-off to Components B and C.
3. **Change log vs last run** — names that newly qualified, names that dropped out, and *why* they dropped (which gate they now fail). This is the `ST-SEL-07` cycling signal made explicit.

---

## 4. Cadence

Designed to run **weekly**, on demand, from the command line. No scheduler in v1 — you run it, you read it, you decide. (A cron/launchd schedule is a trivial later addition once the output has earned your trust; automating a run you don't yet read is premature.) The timestamped outputs accumulate a history, so "AAPL was a strong candidate three weeks ago and has since fallen out on the chart-position filter" is answerable by design.

---

## 5. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Your environment; matches the eventual rules engine |
| Data | yfinance | Free, covers all `ST-SEL` inputs except live IV |
| Compute | pandas, numpy | Screening is dataframe work |
| Vol math | numpy / pandas | Realized-vol proxy for F7 |
| Report | Jinja2 → static HTML | Clean, reusable when hosted later |
| Local view | Python http.server or a minimal Flask route | Phone-viewable on local network; no hosting |
| Config | YAML | Universe, weights, thresholds — all operator-editable |
| Persistence | Local CSV/parquet, timestamped | Run history for change detection |

**Folder placement and environment (matches `AGENTS.md`):** the repo lives in `The Wheel/Development/`;
run outputs are written to the sibling `The Wheel/WheelOps/` folder, never into the repo. Governance
docs are referenced from `../WheelGovernance/` and source material from `../Research/`. Because the
tree is inside iCloud Drive, the Python virtualenv is created **outside** the synced tree at
`~/.venvs/wheel-screener`, and `venv/`, `__pycache__/`, and local caches are gitignored. Base paths
live in the YAML config, not hard-coded.

Everything reusable when this deploys: the data layer and scoring engine are pure functions; only the Jinja template and the serve route are presentation. Deploying later means wrapping the same core in FastAPI, not rewriting it.

---

## 6. Architecture — how it maps to the three-layer model

The screener is **Layer 1 (deterministic rules engine)** from the Jane Street proposal §7, in its first concrete form. No model inference. Every output is a pure function of input data and the rule table. This matters: it means the screener is fully auditable, testable against hand-computed expectations, and never surprises you. Layer 2 (Claude-assisted judgment) enters with Component C, operating *on top of* the screener's output — reasoning about the candidates the deterministic engine surfaces, never replacing it.

---

## 7. Build sequence (the actual work)

| Step | Deliverable | Proves |
|---|---|---|
| 1 | Project scaffold: repo, folders, config YAML, seed universe | Environment works end to end |
| 2 | Data layer: fetch fundamentals, price history, dividends, analyst data for one ticker | yfinance covers what we need |
| 3 | Hard gates (F1–F4, F9): pass/fail for one ticker, then the universe | The disqualify logic is correct |
| 4 | Score filters (F5–F8) + composite | Ranking produces sensible order on names you know |
| 5 | Flags (F10) + change-vs-last-run diff | The `ST-SEL-07` cycling signal works |
| 6 | HTML report + CSV output | Human- and machine-readable results |
| 7 | Local serve route (phone-viewable) | You can check it from your couch |
| 8 | Validation: hand-check 5 names you know well against the screener's verdict | The tool agrees with informed judgment |

Step 8 is the gate. If the screener disqualifies a name you know is a solid Wheel candidate, or ranks an obvious "crap high-IV stock" highly, the rule encoding is wrong and gets fixed before we move to Component C. This is the same discipline as the proposal's validation tracks: the tool earns trust by agreeing with known-good cases before it's trusted on unknowns.

---

## 8. What this explicitly defers

| Deferred to | Item | Why |
|---|---|---|
| Component B | Live options chain, greeks, real IV Rank, bid/ask | Paywall; not needed to screen underlyings |
| Component B | Position tracking, net stock cost, moneyness columns | Needs live positions and options data |
| Component C | Roll/close/assignment recommendations with reasoning | Needs positions (B) and the judgment layer |
| Later | Automated scheduling, hosting, broker API | Automate only what you already read and trust |

---

## 9. FDE framing

This component is a clean portfolio piece: a real data pipeline, a rule-driven scoring engine, a reproducible reporting layer, and an honest treatment of a data limitation (the IV proxy) with a documented path to resolving it. It demonstrates the discipline of shipping a scoped v1 that does one thing correctly rather than a sprawling v1 that does three things unreliably — which is exactly the judgment an FDE role is hiring for. The three-component sequencing, with each earning trust before the next builds on it, is itself the story worth telling in an interview.

---

*AdVenture Labs internal build spec. The screening criteria derive from the ScottishTrader Source Brief v2.0; see that document for full rule text and provenance. Not financial advice.*
