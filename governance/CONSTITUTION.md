---
VERSION: 2.1
DATE: 2026-09-08
SUPERSEDES: Strategy Constitution v1.0 (July 2026, `adventure-labs-strategy-constitution-v1.md`)
STATUS: canonical
MODULE: 1 — The Wheel Engine
BINDING_REFERENCE: Source Brief v2.0
---

# AdVenture Labs — Strategy Constitution

**Module 1: The Wheel Engine**
Version 2.1 · Established July 2026 · Revised August 2026
Owner: Monte

---

## Preamble

This document governs every trade executed under Module 1 of AdVenture Labs. It exists for one
reason: **the strategy fails on discretion, not on math.**

The Wheel is mechanically simple. Every documented failure of it traces back to a human overriding a
rule during a moment of fear, boredom, or greed. This Constitution is the defense against that
human — specifically, against me.

Rules in this document are **binding**. They are not guidelines, heuristics, or starting points.
When a rule and an instinct conflict, the rule wins. If a rule is wrong, it gets amended under
Article X — never ignored in the moment.

**On the relationship between this document and the Source Brief.** The Source Brief is the
*reference*: it holds the methodology, the reasoning, the open conflicts, and the gaps. This
document is the *binding subset*. Where the Brief says "he does X for reason Y," this document says
"I will do X." Rule IDs are cited so every Article traces to its source. **An Article with no
citation is an AdVenture Labs invention and should be viewed with more suspicion than the rest.**

---

## Article I — Capital

**§1.1** Every put sold is fully cash-secured. No naked puts. No margin-funded assignment. Ever.
*(ST-ENT-01, ST-CSH-02)*

**§1.2** Capital is held in three separate buckets at all times: *(AL-OPS-01)*

| Bucket | Location | Rule |
|---|---|---|
| Trading reserve | Schwab taxable brokerage | Covers 100% of assignment obligation on all open positions |
| Tax reserve | HYSA (separate institution) | 35% of every realized gain, transferred within 7 days of close |
| Free cash | Checking | Only capital above trading + tax reserve. Spendable. |

**§1.3** **The 50% reserve is the load-bearing control of this program.** No more than 50% of net
liquidity is deployed as option collateral on average, with a hard ceiling of 65% and no more than
two consecutive weeks above the average. *(ST-CSH-01, AL-CSH-01)*

**§1.4** Reserve capital may be held in any instrument that is accessible before the broker would
liquidate — which in practice means accounting for two-day settlement. An instrument that cannot be
converted inside the assignment window is not reserve. *(ST-CSH-03)*

**§1.5** Performance is measured on **full net liquidity, including the reserve.** *(ST-CSH-04)*
This is not an accounting convention. Measuring on deployed capital only would flatter the result
and create a standing incentive to abandon the one control everything else depends on.

**§1.6** Capital is never added mid-drawdown to average down a losing position. New capital enters
on a schedule, not on an emotion. This does not prohibit the covered-strangle repair under §5.7,
which is a position-management decision, not a funding decision.

**§1.7** The trading account is separate from all retirement, long-term, and emergency capital.
*(ST-CSH-05)*

---

## Article II — Stock Selection

A stock is eligible only if it satisfies **every** filter below. One failure disqualifies it.

**§2.1** Profitable company with solid cash flow. *(ST-SEL-01)*

**§2.2** Bullish or very bullish analyst consensus. *(ST-SEL-02)*

**§2.3** **Share price within the current zone**, derived from account size rather than fixed:

> `max_strike = (net_liquidity × per_name_cap) ÷ 100`

The **$10 floor is absolute and does not scale.** *(ST-SEL-04)* The upper bound moves with the
account, because the band was always a capital-efficiency constraint and the source confirms his own
band moved up as his account grew. *(ST-SEL-03, AL-SEL-02)*

Candidates outside the current zone are **displayed but locked.** Opening one requires an explicit
override, a logged prediction, and the concentration figure displayed at the moment of decision.
*(AL-SEL-03)*

**§2.4** **Market cap floor: mid-cap or above** at pilot scale. Market cap and share price are
separate filters answering separate questions — price governs sizing, market cap governs quality,
liquidity, and gap risk. *(AL-SEL-06)*

**§2.5** Stable price chart. No history of violent gaps driven by single-personality risk, narrative
cycles, or social-media catalysts. *(ST-SEL-05)*

**§2.6** **Not at or near a multi-year high.** Entry point materially affects assignment probability
independent of every other filter. *(ST-SEL-12)*

**§2.7** **High implied volatility disqualifies.** Raw IV materially above ~50% is a rejection
signal. Realistic premium on a compliant name is approximately 1% of collateral per cycle; anything
substantially richer is pricing a risk this strategy cannot absorb. *(ST-SEL-10, ST-SEL-11)*

**§2.8** Pays a dividend where possible. Preferred, not mandatory. *(ST-SEL-06)*

**§2.9** Options liquidity sufficient for tight bid/ask fills at target strikes. *(ST-SEL-13)*

**§2.10** **I am willing to own 100 shares of this company for twelve months without distress.** If
the honest answer is no, it is not a candidate. *(ST-SEL-09)* This is the precondition for the
entire risk argument, not one filter among ten.

**§2.11** **A name is not tradeable until its thesis is written.** `notes/<TICKER>.md` must exist
and must state the business case and the name-specific kill-switch conditions. *(AL-SEL-04)* An
unwritten thesis is an unexamined one, and §2.10 cannot be honestly answered without it.

**§2.12** The watchlist holds roughly 10 monitored names and is reviewed on a fixed cadence — never
reactively. *(ST-SEL-07, ST-SEL-14)* Of those, 3–5 carry written theses and are tradeable.

---

## Article III — Entry

**§3.1** Sell cash-secured puts at **30–45 DTE**. Not weeklies. Not LEAPS. *(ST-ENT-02, ST-ENT-08)*

**§3.2** Target **~0.30 delta** (≈70% probability OTM) or lower. *(ST-ENT-03)*

**§3.3** Contract count is determined by assignment capacity, not premium appetite. The question is
never "how much can I collect" — it is "how many hundred shares can I comfortably own." *(ST-ENT-04)*

**§3.4** **Assignment capacity is computed and displayed before every entry:** total obligation if
every open position were assigned, against available reserve. *(AL-CSH-02)* A control that is not
displayed at the moment of the decision is not operating.

**§3.5** No position is open through an earnings report or other known binary event. Close before,
re-enter after. This extends to CPI prints and Fed meetings. *(ST-ENT-05)*

**§3.6** Ladder into positions rather than opening the full intended size at once. *(ST-ENT-07)*

**§3.7** No new position is opened on a stock that has failed any Article II filter since the last
review.

**§3.8** A GTC limit order at 50% of credit is entered **immediately on fill**, and a broker alert is
set at the strike price. *(ST-ORD-01, ST-ORD-04)* These are automations, not intentions.

**§3.9** **Never a market order on an option.** Limit orders only, worked by a penny or two.
*(ST-ORD-02, ST-ORD-03)*

**§3.10** No trade within 30 minutes of market open. *(AL-OPS-02)*

---

## Article IV — Management

**§4.1** Close or roll at **50% of maximum profit** when meaningful time remains. Capital freed is
capital redeployed. *(ST-MGT-01, AL-MGT-01)*

**§4.2** **The roll trigger is two-conditional.** Roll when the underlying reaches the strike **and**
I am convinced it will remain at or below that level. A name at the strike during a broad market
decline, where the business is unaffected, is a hold. *(ST-ROL-01)*

**§4.3** Roll **out one to two weeks, same strike**, for a net credit. Improve the strike only if a
net credit still results. Total tenor stays inside approximately 60 DTE. *(ST-ROL-02, -04, -06)*

**§4.4** **After a roll, the objective changes.** The position is no longer targeting 50% profit; it
is targeting exit at scratch or any small net profit as soon as available, to free capital.
*(ST-ROL-05)*

**§4.5** **A challenged name is frozen.** No new positions open on an underlying already under
management. *(ST-ROL-08)*

**§4.6** Rolling continues while a meaningful net credit is obtainable. A credit of approximately
$0.01 is the signal that rolling has stopped being productive. *(ST-ROL-09)*

**§4.7** **If a credit cannot be obtained, take assignment.** Do not pay a debit to escape. Do not
close early at a loss to stop the bleeding. This is the single most expensive mistake available and
it is prohibited. *(ST-MGT-04)*

**§4.8** Where a roll must span an earnings report, extend approximately 30 days past the report
date. *(ST-ROL-07)*

**§4.9** Every open position has a defined next action before it is opened. No position is ever
managed by improvisation.

**§4.10** **Positions are never managed by DTE.** Management is triggered by price relative to
strike. A day count cannot indicate an adjustment without knowing where the stock is. *(ST-PHI-02)*

**§4.11** P&L is evaluated **per name over time**, not per trade. *(ST-MGT-06)*

**§4.12** Re-entry after a profitable close is conditional, not automatic. Freed capital goes to the
best available compliant trade, which is frequently a different name. *(ST-MGT-07)*

---

## Article V — Assignment Protocol

**§5.1** Assignment is an expected outcome at a rate of roughly **2–3 per year across the book**,
not a failure. It is Phase 2 of the strategy. A materially higher rate indicates a selection or
roll-discipline failure, not bad luck. *(ST-FRM-02, ST-FRM-03)*

**§5.2** On assignment, compute **net stock cost** = strike paid − all premium collected on that
position. This number, not the strike and not market price, is the reference for everything that
follows. *(ST-ASN-01)*

**§5.3** Where net stock cost is **below** market, exit quickly — sell the shares, or sell an ATM or
ITM call for one additional premium on the way out, and return to Phase 1. *(ST-ASN-02, -03,
ST-CC-10)*

**§5.4** Sell covered calls at a strike **above net stock cost.** Selling below net stock cost locks
in a loss and is prohibited. Where no workable strike exists above cost, **sit on hands.**
*(ST-CC-01, ST-CC-08)*

**§5.5** Covered calls follow the same parameters as puts: 30–45 DTE, ~0.30 delta or lower, close or
roll at 50% profit. *(ST-CC-03, ST-CC-04)*

**§5.6** If a covered call is challenged, roll for a credit. If no credit is available and the
strike sits above net stock cost, **let the shares be called away.** Do not chase the stock. Do not
buy back a winning call at a loss to keep shares. *(ST-CC-05, ST-CC-11)*

**§5.7** Where no strike exists above net cost and the name remains fundamentally sound, additional
puts may be sold below market — the covered strangle repair. **Prohibited on any name with a
fundamental change**, and always subject to the concentration ceiling in Article XI. *(ST-CC-09)*

**§5.8** Continue selling covered calls until net stock cost falls below market price, at which
point the position may be exited and the cycle restarted. *(ST-CC-07)*

**§5.9** Early assignment is rare and concentrates in one condition: extrinsic value near zero with
little time remaining. The 50% rule and active rolling keep positions out of that state. *(ST-ASN-04,
-05, -06)* Concern about early assignment is a symptom of oversizing, and the remedy is smaller size.

---

## Article VI — The Kill Switch

**§6.1** A position is closed for a loss only when the **investment thesis is broken** — not when
the price is down. *(AL-RSK-01)*

**§6.2** Thesis-broken triggers, any one sufficient:
- Material deterioration in cash flow or profitability
- Dividend suspended or cut
- Analyst consensus flips from bullish to bearish
- Accounting irregularity, fraud investigation, or going-concern disclosure
- Any development that would make me answer "no" to §2.10
- **Any name-specific trigger written in that name's `notes/<TICKER>.md`** *(AL-SEL-04)*

**§6.3** When the kill switch fires, the position is closed **in full, promptly, without
negotiation.** Premium already collected offsets the loss. Capital redeploys to a compliant name.

**§6.4** Price decline alone is never a kill-switch trigger. That is what Article V exists to manage.

**§6.5** Kill-switch calibration is an open question (Brief C-5). Every firing is logged with the
trigger and the subsequent price path, so false-positive rate becomes measurable rather than argued.

---

## Article VII — The Patience Clause

The largest documented source of loss in this strategy is impatience. *(ST-PHI-01)* These rules
exist because the instinct to act is the thing most likely to cost money.

**§7.1** If a put cannot be rolled for a credit, **let it play out.** Closing early at a debit
converts a manageable assignment into a realized loss. *(ST-MGT-04, ST-PHI-01)*

**§7.2** After assignment, do not attempt to rescue the stock by buying back a call at an inflated
price. *(ST-CC-11)*

**§7.3** Recovering net stock cost through covered calls may take **months.** That is the strategy
working as designed. *(ST-PHI-01)*

**§7.4** **Boredom is not a signal.** A week with no compliant entry is a normal week. Sitting in
cash is a position. *(ST-PHI-04)*

**§7.5** **If I am worried about a position, I am trading too large.** The remedy is size, not
willpower. *(ST-PHI-05)*

**§7.6** Adjustments are judgment and few hard rules exist. *(ST-PHI-03)* Where this Constitution
does not determine an answer, the correct output is a stated set of options with tradeoffs and a
logged decision — never a confident invention.

---

## Article VIII — Cash, Tax, and Withdrawal Discipline

**§8.1** Options premium on individual equities is **short-term capital gain**, taxed as ordinary
income. The 60/40 treatment for broad index options does not apply. *(AL-OPS-01)*

**§8.2** 35% of every realized gain moves to the tax reserve within 7 days. This money is not mine.

**§8.3** Quarterly estimated payments on schedule: April 15, June 15, September 15, January 15.

**§8.4** No withdrawals to free cash until the account clears **$30,000 deployed.** Before that
threshold, 100% of gains are reinvested.

**§8.5** Assignment converts cash into shares. Shares are not free capital. Buying power is not
income.

---

## Article IX — Record Keeping

**§9.1** Every trade event is logged at the time it occurs: date, ticker, structure, strike,
expiration, delta at entry, credit received, debit paid, net stock cost, and the rule ID that
triggered the action. *(ST-ENT-06, ST-CC-06)*

**§9.2** **A trade that is not logged did not happen** and cannot be evaluated. Logging is a
precondition of the trade, not an afterthought.

*Removed in v2.1: §9.3 (prediction field), §9.4 (divergence logging), and §9.5 (decisions
reference a snapshot) went out with Article XIII and the decision log. AL-OPS-06 still governs the
screener — market data is snapshotted before it is scored — but it now binds the tool's own
pipeline rather than a decision record. See the v2.1 Change Log entry.*

---

## Article X — Amendment

**§10.1** This Constitution may be amended only:
- In writing, with the change and its rationale documented
- On a **fixed quarterly cadence**, never on the day a change is wanted
- **Never** while any position is in an unrealized loss
- **Never** within 72 hours of a losing outcome

*(AL-OPS-03)*

**§10.2** **The prohibition in §10.1 is the most important rule in this document.** Rules rewritten
under emotional pressure are how systematic strategies become discretionary ones.

**§10.3** Amendments require a stated hypothesis and a defined way to evaluate whether the change
helped. "It feels better" is not a rationale.

The evaluation is now external to the tool. v2.0 expected a decision log and a calibration report to
supply it; v2.1 retires both, and the hypothesis is written, tested, and judged by the operator
against the trade ledger and the record of the amendment itself. **What is required is unchanged —
a hypothesis and a way to tell whether it held. Only the mechanism that was going to check it is
gone**, and an amendment offered without one is still refused.

**§10.4** An amendment that loosens a rule requires evidence that the rule was wrong. An amendment
that tightens a rule requires only that it not conflict with an existing Article. **The asymmetry is
deliberate.**

**§10.5** Amendments to Articles I §1.3 (the reserve), IV §4.7 (the debit prohibition), or II §2.10
(willingness to own) require a full quarter's notice — proposed in one review, adopted in the next.
These three carry the program's risk argument. *(Brief Appendix A)*

---

## Article XI — Portfolio Construction

*New in v2.0. Governs the book as a whole rather than any single position.*

**§11.1** Target exposure per name is **5% of the account**, with 10% permitted for a name of
exceptional quality. *(ST-SIZ-01)*

**§11.2** **At pilot scale this policy is not honoured and cannot be.** At $12,000 a single contract
on a $25 name is roughly 21% of the account. This is arithmetic, not a choice, and it resolves as
the account grows toward $60,000. It is stated here rather than buried because a policy limit
silently breached is worse than one openly suspended. *(Proposal §4.3, §9.1)*

**§11.3** Pilot-scale mitigations, binding until the 5% policy becomes achievable: *(AL-SIZ-01)*
- Minimum **3 names** carrying written theses
- Minimum **2 sectors**
- Maximum **1 contract per name**
- Maximum **2–3 concurrent open positions** below $20K *(AL-SEL-01)*

**§11.4** **Sector ceiling: no more than 50% of deployed collateral in any one sector.**
*(AL-SIZ-02)* Sector-wide selloffs are the correlation that per-name limits do not see.

**§11.5** **Industry concentration produces a warning, not a block.** *(AL-SIZ-03)* Sub-industry
taxonomies are noisy and a hard rule on noisy data produces false blocks. The warning is logged and
answered, not dismissed silently.

**§11.6** **Earnings clustering is flagged** when two or more open or candidate positions report in
the same week. *(AL-SIZ-04)* This is a correlation the sector view does not catch.

**§11.7** No new position opens on a name already under management. *(ST-ROL-08)*

**§11.8** A held name that appreciates out of its zone is **flagged, not force-exited.** No new
position opens on it until it re-enters band or the account grows into the next zone. *(AL-SEL-05)*

**§11.9** The concurrent-position ceiling is the reserve arithmetic in §1.3, not a fixed count.
*(ST-SIZ-03)*

---

## Article XII — Return Expectations

*New in v2.0. Cited by Proposal §5 and Appendix A.*

**§12.1** **This program has no annual return target.** A target is an input to decision-making, and
any rule adopted in order to reach a number is a violation of the selection, entry, or sizing
discipline. Return is an *output* of correct execution under a given regime. *(ST-PER-01, ST-PER-03)*

**§12.2** **Regime-conditional expectations.** The planning case is **Base, 15–25%**, and all capital
planning, income projection, and validation criteria assume that column and no higher.

| Regime | Expected annual | Mechanism |
|---|---|---|
| Bear | 8–14% | Smaller positions, wider laddering, stricter selection; 30–45 DTE absorbs shorter shocks; dividends contribute |
| **Base** | **15–25%** | Standard cycle: sell, close at 50%, redeploy; occasional roll; rare assignment |
| Bull (post-correction) | 30–40% | Reserve deployed into reset prices; elevated IV on quality names; rapid turnover |

**§12.3** **A Bear-column year is not underperformance.** A +10% return in a market that fell 18% is
the program working. Judging a bear year against Base expectations is the specific error that
produces rule-tampering. **The regime is identified and recorded in writing before performance is
evaluated** — not afterward, when the number is already known. *(ST-PER-02)*

**§12.4** **The upside column is unlocked by the reserve, not by risk-taking.** Every mechanism
producing the Bull scenario is a *defensive* mechanism operating in a favourable regime. There is no
posture available within this strategy that raises expected return; there are only postures that
raise variance. **Any proposal to reach the Bull column deliberately is a proposal to abandon the
strategy.** *(ST-CSH-01, ST-EVT-02)*

**§12.5** At 3–5 names, dispersion around any scenario is materially wider than at the 10–20 name
book the methodology assumes. Fewer positions produce higher variance, not higher return. **Early
results, favourable or otherwise, carry low information content.** *(ST-PER-03)*

**§12.6** Performance is compared against three benchmarks and no others: **prior-year own
execution**, **cash and short-duration fixed income** as income instruments, and the **mechanical
floor** simulation. Comparison to a passive equity index in a bull market is not informative — the
covered call leg caps upside by construction. *(ST-PER-05)*

**§12.7** All figures in §12.2 are gross. At an assumed 35% effective rate, a 20% gross return is
approximately 13% net. **The after-tax number is the honest one.** *(AL-OPS-01)*

---

## Article XIV — Scope

**§14.1** This Constitution governs Module 1 (equity Wheel) only. Module 2 and subsequent AdVenture
Labs modules require their own governing documents.

**§14.2** No capital crosses between modules without a documented decision.

**§14.3** Where this document and the Source Brief conflict, **this document binds** and the conflict
is recorded as an amendment candidate. Where this document is silent and the Brief is not, the Brief
is advisory, not binding.

---

## Signature

By operating under this document, I acknowledge that the rules above supersede my judgment in the
moment, and that the purpose of writing them down in advance is precisely so that the version of me
under pressure does not get a vote.

**Adopted:** _______________
**Next scheduled quarterly review:** _______________

---

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | Jul 2026 | Initial draft. Articles I–XI. No rule ID citations. |
| **2.1** | **2026-09-08** | **Article XIII (Review Cadence) removed in full. Article IX §9.3 (prediction field), §9.4 (divergence logging) and §9.5 (snapshot reference for decisions) removed.** The decision log and the calibration harness that scored it are retired; the screener is the sole product. §10.1's cadence survives as a bare quarterly constraint, no longer pointing at a deleted Article. §10.3 keeps its requirement of a stated hypothesis and softens the mechanism — evaluation is the operator's work, external to the tool. Source Brief AL-OPS-05 marked retired, text preserved for the audit trail. **§13.6's annual re-examination of §11.2 is lost with Article XIII and is not replaced here** — see the open item in AGENTS.md §10. |
| **2.0** | **2026-08-03** | Added Article XI (Portfolio Construction), XII (Return Expectations), XIII (Review Cadence); Scope moved to XIV. **Amendment retained at Article X.** Every Article now cites Source Brief v2.0 rule IDs. §2.3 fixed price band replaced with derived zones. Added §2.4 market cap, §2.6 chart position, §2.7 IV disqualifier, §2.11 thesis gate, §3.4 assignment capacity display, §4.10 no-DTE-management, §9.3 prediction field, §10.4/§10.5 amendment asymmetry and notice period. |

---

*This is a personal planning document, not financial advice. Options trading involves substantial
risk of loss, including loss of principal. Tax treatment described here is general and should be
confirmed with a qualified tax professional.*
