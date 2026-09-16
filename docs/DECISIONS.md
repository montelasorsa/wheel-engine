# Decision log — Wheel Engine

Decisions made in conversation that aren't yet in governance docs. **Newest first.**

This log was extracted from AGENTS.md §10, which had outgrown a table: several
rationales run to a paragraph, and a four-column row is the wrong shape for a
paragraph. Content is unchanged from the table it came from, with one
correction noted below.

**What belongs here:** a decision that changes what the code does or what the
project is, made in conversation, not yet written into the Constitution, Source
Brief or Proposal. When a decision is promoted into a governance document, the
entry stays and says so — AL-SEL-07 below is the worked example.

**What does not:** anything already binding in `governance/`. Those documents
are the version of record and this log never overrides them.

**Dates corrected on extraction.** Three entries below were dated `2026-08-XX`
in the table. All three were committed **2026-09-08** — `b81c1fe` (realign),
`d51e607` (schedule), `c0d43ec` (Layer 2 retirement) — and are dated and
ordered accordingly here. Nothing else was changed.

---

## 2026-09-16 — Weekly schedule moved to Sunday 08:00 and hardened for an unattended run

**Decision.** Failure notification, `wheel-backup` appended non-fatally, `caffeinate -i` for the duration.

**Rationale.** Three things stood between the committed schedule and a run that could survive unsupervised. A cold-cache run is ~5 hours (4h45m on 2026-08-16), so an 18:00 start finished near 23:00 against a machine about to be shut for the night — 08:00 gives the run the whole day and puts the report in hand before Sunday evening rather than after it. launchd does not keep the Mac awake for its own job, so idle sleep paused every fetch until someone walked past. And a failure was entirely silent: no report arriving is the slowest possible signal, so a step that fails now names itself in the log and in Notification Center. Backup runs outside the fail-stop wrapper because by then the report is already delivered, and an unreachable iCloud folder is not a failed week.

**Supersedes.** The Sunday 18:00 schedule (2026-09-08); §5 build-order step 4's time and pipeline.

---

## 2026-09-08 — AGENTS.md realigned to post-retirement scope

**Decision.** §5 build-order step 1 removed, §7.1 rewritten to permit a renderer.

**Rationale.** Two rules had outlived what they described. §5 step 1 named `docs/decision-record-schema.md` and cited Article XIII amendment sourcing — a design step for code that now lives in `legacy/`, so it does not lead a build order it no longer belongs to; the Layer 0 snapshot contract is the genuine first step, being the interface both sides are built against. §7.1 said "do not add a UI" while `src/wheel/render_html.py` had been shipping HTML for weeks, which makes the rule unenforceable and every other rule in §7 cheaper to ignore. The convergence test is what actually separates the two cases and is already written down in Proposal §7.2: a renderer is a pure function from frozen data with a checkable finish line, an application reopens on taste every time it is examined.

**Supersedes.** §5 build-order step 1 (decision-record schema); §7.1 "Do not add a UI".

---

## 2026-09-08 — Added Sunday 6pm launchd schedule

**Decision.** Pipeline is: screen → enrich → render → deliver (file + email via Apple Mail). All steps deterministic; no LLM in the automated loop.

**Rationale.** A weekly tool the operator has to remember to run is a weekly tool that gets run for three weeks. launchd rather than cron because a cron job due while the Mac is asleep is simply missed, and missing one firing costs a whole week. Mail via `osascript` rather than SMTP because the account is already configured there and the alternative is a password in a repo that has spent real effort keeping secrets out. Installing is manual — `scripts/install-schedule.sh` is never invoked by the build.

**Supersedes.** Manual invocation of each command.

---

## 2026-09-08 — Retired Layer 2 decision-support

**Decision.** Screener is now the sole product. Constitution Article XIII removed. Article IX §9.3/§9.4 removed.

**Rationale.** The decision log and the calibration harness were built to make judgment measurable, but evaluating them is the operator's work, not the tool's. A screener that runs unattended every week is a product; a decision log that needs a quarterly sit-down to mean anything is a second product wearing the first one's clothes. `/wheel-decide`, `/wheel-review`, and their modules move to `legacy/` intact — retired, not deleted, because the audit trail is the point.

**Supersedes.** AGENTS.md §1 objectives 3 and 4; §5 build-order steps 5 and 6; Constitution Article XIII and §9.3/§9.4/§9.5; AL-OPS-05 marked retired in the Source Brief.

**Open item.** §13.6's annual re-examination of §11.2 went out with Article XIII and has no replacement home.

---

## 2026-08-16 — AL-SEL-07 minted: ETF structural screen

**Decision.** Promoted into Source Brief v2.1 rather than logged here alone.

**Rationale.** The 2026-08-13 run filled all five Zone 1 slots with derivative-income ETFs (COYY 386%, TSYY 201%, YBTC 81%, BITY 57%, BAGY 38%). Option-premium distributions read to ST-SEL-06 as extraordinary dividends and structural NAV decay reads to ST-SEL-12 as a discount from the high, so the screen ranked capital destruction highest. Three Stage 1 disqualifiers — issuer pattern, 20% yield ceiling, null sector — bypassed by `universe.include`. Applied before the deep snapshot so a structured product costs zero provider calls. The ID went into the Source Brief because the code emits it as a citation, and §7.4 forbids citing a rule that has no definition.

**Supersedes.** The 2026-08-11 note that "minting AL-SEL-07 would need a Source Brief amendment" — that amendment is now made.

---

## 2026-08-11 — FMP readmitted as a bounded null-fill fallback

**Decision.** Over four allowlisted fields.

**Rationale.** The 2026-08-03 removal was right about the general case and §4.4 is unchanged, but a hard gate reading CANNOT_EVALUATE fails closed — a null `net_income_ttm` rejects a name on a data gap, not on its merits. Measured residual: 17 of 1,285 names, ~50 requests/run.

**Supersedes.** "FMP fully removed" (2026-08-03); "FMP removal confirmed" (2026-08-04); the FMP gap-fill argument in the 2026-08-06 null-handling row.

---

## 2026-08-11 — Universe comes from the CBOE options symbol directory

**Decision.** Not S&P index constituents.

**Rationale.** Index membership correlates with optionability but does not decide it, and a name without listed options cannot be wheeled at all. Measured on the 2026-08-11 run: 34 screened names had no CBOE-listed options, including the top-ranked monitored name. Universe 1,506 → 5,334.

**Supersedes.** S&P 500/400/600 scraping (moved to `legacy/universe_source_wikipedia.py`).

---

## 2026-08-11 — Screener sources from a broad universe, not a hand-picked watchlist

**Rationale.** A screener that ranks a list you already chose inverts its purpose.

**Supersedes.** `watchlist` config key.

---

## 2026-08-11 — Two-stage fetch: cheap scan then deep snapshot

**Rationale.** A deep snapshot is 5 provider calls; spending it on names rejected on price alone costs ~20 min and learns nothing.

**Supersedes.** Single-stage acquire.

---

## 2026-08-11 — ST-SEL-01 split: only both-negative fails; one negative flags

**Rationale.** "Profitable company with solid cash flow" is two criteria. A write-down with cash still coming in is a question, not a rejection.

**Supersedes.** Single-gate ST-SEL-01.

---

## 2026-08-11 — Monitored tier replaces the thesis-required list

**Decision.** AL-SIZ-03/04 scoped to thesis-backed names and open positions.

**Rationale.** At 200 names every week clusters, so an unscoped flag means nothing; a full list is a phone book, not a screen.

**Supersedes.** Full-list output.

---

## 2026-08-11 — Continuous scoring replaces verdict buckets

**Decision.** Gates stay binary; the five ranking rules emit a 0-100 score from a piecewise anchor table.

**Rationale.** Five PASS/FLAG/FAIL rules can express only a few dozen composites: the 2026-08-11 run tied 255 of 1,285 names at exactly 100 and broke ties alphabetically, so the monitored "top 5" was the alphabetically-first five of 111 equals. Now 1,171 names, 1,171 distinct scores.

**Supersedes.** Verdict-bucket composite; ST-SEL-10's 50-80% flag band; ST-SEL-12's 10% near-high flag.

---

## 2026-08-11 — Cash-flow strength scored under ST-SEL-01, not a new rule ID

**Rationale.** The rule is "profitable company with solid cash flow" — the gate answers the sign, the score answers the degree. Minting AL-SEL-07 would need a Source Brief amendment for something already in scope (§7.4).

**Supersedes.** —

---

## 2026-08-06 — ST-SEL-10 split: hard gate >80% vol, flag 50-80%, pass <50%

**Rationale.** Proxy data too approximate for hard rejection near ~50%; 80%+ is unambiguous.

**Supersedes.** Single-threshold gate — **flag band superseded 2026-08-11**: 50% is now a curve anchor, not a verdict boundary.

---

## 2026-08-06 — Graceful null handling in scorers: degrade, don't crash; null ≠ zero

**Rationale.** Missing data is a scorer problem, not a source problem.

**Supersedes.** FMP gap-fill argument — **partially superseded 2026-08-11**: null handling stays the rule, but the 1.3% residual is now filled rather than failed closed.

---

## 2026-08-06 — Legacy gates.py superseded by snapshot-contract scorers

**Decision.** Remove in a single dedicated commit after all 13 built.

**Rationale.** Two implementations during port is known state; cleanup is one atomic commit.

**Supersedes.** —

---

## 2026-08-04 — Yahoo sector labels authoritative at pilot scale

**Rationale.** 3–5 names don't need GICS precision; consistency > accuracy at this n.

**Supersedes.** G-11 partially closed.

---

## 2026-08-04 — yfinance is Layer 0 provider; Schwab API is Phase 4 upgrade

**Rationale.** Snapshot boundary makes provider low-stakes; yfinance covers 9/10 data points.

**Supersedes.** FMP removal confirmed — **amended 2026-08-11**: yfinance is primary and first; FMP fills its nulls.

---

## 2026-08-04 — Plugins (finance, S&P) live at Layer 2, not Layer 0

**Rationale.** Plugins operate inside Claude context; cannot be snapshotted or batch-run.

**Supersedes.** Architecture clarified.

---

## 2026-08-04 — G-14 deferred; start accumulating IV snapshots now

**Rationale.** IV Rank needs ~26 weeks of history; source doesn't use it.

**Supersedes.** AL-ENT-01 unenforced.

---

## 2026-08-03 — UI removed, not deferred

**Rationale.** UI doesn't converge; output is files.

**Supersedes.** Flask/serve.py cut.

---

## 2026-08-03 — FMP fully removed

**Decision.** No adapter, no rescue path.

**Rationale.** FMP cut — **superseded 2026-08-11** by the bounded fallback.

---

## 2026-08-03 — Snapshot-then-score is architectural

**Rationale.** Makes golden-file testing and reproducibility possible.

**Supersedes.** —

---

## 2026-08-03 — WheelOps as sibling to repo

**Rationale.** Privacy by geometry, not by .gitignore.

**Supersedes.** —

---

## 2026-08-03 — Repo moved to ~/Developer/wheel-engine/

**Rationale.** iCloud sync fights git internals.

**Supersedes.** —
