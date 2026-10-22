---
VERSION: 2.1
DATE: 2026-08-16
SUPERSEDES: Source Brief v1.0 (July 2026, `adventure-labs-scottishtrader-source-brief-v1.md`)
STATUS: canonical
DELIVERABLE: 2 of 8
MODULE: 1 — The Wheel Engine
---

# AdVenture Labs — Source Brief: ScottishTrader Wheel Methodology

**Status: Substantially complete.** 8 of 10 v1.0 gaps closed by promotion from the Distilled
Reddit Transcripts. 2 remain open, 4 new gaps opened by the v2.0 scope expansion.

---

## 0. Purpose and Provenance

### 0.1 What this document is

A structured extraction of the Wheel methodology as articulated by the Reddit user
**ScottishTrader**, restated as discrete, referenceable rules with the reasoning behind each one
preserved.

This is the primary rule reference for Module 1. Every downstream artifact — the Investment
Proposal, the mechanical floor simulation, the Wheel Engine tooling — traces its logic back to a
rule ID in this brief. When something in the system behaves unexpectedly, this is where we come to
audit whether the behavior was specified or invented.

### 0.2 Why rationale is captured, not just rules

Two reasons.

First, the operator and any decision-support layer must reason about novel situations. A rule alone
states what to do in the anticipated case. The rationale states what the rule was *protecting
against*, which is what generalizes when the case is unanticipated. A system that knows "roll for a
credit" behaves differently from one that knows "roll for a credit because paying a debit to escape
converts a recoverable position into a realized loss."

Second, rules without reasoning cannot be amended intelligently. Amendment requires knowing which
rules are load-bearing and which are conventions.

### 0.3 Source integrity

**What we now have.** His comprehensive written guide, plus his thread-level commentary across
r/Optionswheel, r/thetagang, and r/options, collected manually in July 2026 and condensed into the
**Distilled Reddit Transcripts**. The Q&A material is where edge cases get resolved and is the
source of most v2.0 promotions.

**What we still do not have.** His position-level trade log, his actual ticker list (declined
by policy — see G-13), and any quantitative record of outcomes. All performance figures attributed
to him are self-reported.

**Attribution discipline.** Part I contains methodology attributable to ScottishTrader. Part II
contains AdVenture Labs additions and modifications, flagged separately. Part III contains
unresolved conflicts. Part IV is the gap register. Nothing migrates between sections without a
documented decision, because when the strategy underperforms we must be able to answer *"is this
his rule or ours?"*

**Single-source rule.** Only ScottishTrader's own words are primary. The rolling contribution by
u/OptionsTraining that he appended to his own post with attribution is **endorsed-secondary** and
is not promoted to a `ST-` rule ID.

### 0.4 Rule ID convention

`ST-[DOMAIN]-[NN]` — source methodology · `AL-[DOMAIN]-[NN]` — AdVenture Labs additions

| Domain | Scope | Domain | Scope |
|---|---|---|---|
| `FRM` | Strategic frame | `CC` | Covered calls |
| `SEL` | Stock selection | `CSH` | Cash and reserve |
| `ENT` | Entry parameters | `SIZ` | Position sizing |
| `ORD` | Order mechanics | `EVT` | Market events |
| `MGT` | Put management | `PER` | Performance expectations |
| `ROL` | Rolling | `PHI` | Discipline and philosophy |
| `ASN` | Assignment | `RSK` | *(retired in v2.0 — see Appendix B)* |

**v2.0 renumbering notice.** v1.0's `RSK` domain conflated three unrelated concerns (impatience,
decline management, appreciation management). v2.0 distributes them to `PHI`, `CC`, and `ROL`
respectively, and promotes rolling out of `MGT` into its own domain because it is the methodology's
primary risk control and warrants first-class addressing. **Appendix B is the complete v1→v2
crosswalk.** No v1.0 ID should appear in any document after this version.

---

# PART I — Methodology (ScottishTrader)

## 1. Strategic Frame

| ID | Rule | Rationale |
|---|---|---|
| **ST-FRM-01** | A repeating two-phase cycle: sell cash-secured puts on a stock you would willingly own; if assigned, sell covered calls against the shares until called away; return to Phase 1 | The full instrument set is CSPs and post-assignment covered calls. Nothing else. |
| **ST-FRM-02** | The goal is **premium, not assignment**. Assignment is to be avoided, not sought | His most emphatic correction, added to the top of his main post after widespread misreading. Traders who wheel *in order to* acquire shares are running a different strategy. |
| **ST-FRM-03** | Expected assignment frequency with active rolling: **2–3 per year across the book**, seldom two open at once | Stated from his own practice. This is the calibration number — assignment materially above this rate indicates a selection or roll-discipline failure, not bad luck. |
| **ST-FRM-04** | The primary risk is a significant decline in the underlying, and that risk is **no greater than owning the stock outright** | The load-bearing argument of the entire methodology. It does not claim low absolute risk; it claims the risk is equity-ownership risk already accepted at selection. Premium collected makes the position strictly better than ownership at the same effective entry. **The claim holds only if ST-SEL-09 was answered honestly.** |

---

## 2. Stock Selection

His stated position: most bad experiences with the Wheel trace to poor stock selection. Highest-
leverage decision in the strategy.

| ID | Rule | Rationale |
|---|---|---|
| **ST-SEL-01** | Profitable company with solid cash flow | Assignment may become a multi-month hold. Fundamental solvency is what makes waiting survivable rather than catastrophic. |
| **ST-SEL-02** | Bullish or very bullish analyst consensus | Directional tailwind. Cheap filter against selecting into a deteriorating name. |
| **ST-SEL-03** | Share price approximately **$10–$50** | Capital efficiency, **not a quality judgment**. At $30/share one contract requires $3,000 secured, permitting multiple positions and roll flexibility. He states the band moved up as his account grew — confirming it scales with capital. See **AL-SEL-02**, which replaces the fixed band with a derived one. |
| **ST-SEL-04** | Hard floor: **no sub-$10 stocks** | Categorical. Elevated distress risk, thinner options liquidity, wider spreads. Unlike ST-SEL-03, this floor does not scale. |
| **ST-SEL-05** | Stable chart without violent movement, explicitly including moves driven by executive social media | Gap risk is the failure mode the strategy cannot manage. Rolling requires an orderly market; a 30% overnight gap removes the option. Single-personality risk named as a disqualifier. |
| **ST-SEL-06** | Dividend preferred, not required | Collected while holding assigned shares, improving effective basis; also proxies for the stability profile the strategy needs. |
| **ST-SEL-07** | Maintain a watchlist of roughly **10 names**; review every few weeks | Ensures a compliant candidate exists without forcing entry into a marginal name. Cadence is deliberate — selection happens on a schedule, away from the pressure of an open position. |
| **ST-SEL-08** | Lower-priced ETFs are valid candidates | No earnings events, no single-company headline risk, steadier movement. Tradeoff is thinner premium. |
| **ST-SEL-09** | The operator must **genuinely be willing to own the stock for twelve months** without distress | Precondition for the entire risk argument in ST-FRM-04. If false, the strategy's risk model does not apply to the position. |
| **ST-SEL-10** *(new v2.0)* | **High implied volatility disqualifies.** Raw IV materially above ~50% is a rejection signal, not an attraction | Promoted from his worked comparison: F at ~0.21 and T at ~0.40 premium versus APLD at 1.35 on comparable delta and DTE. The premium differential *is* the risk differential. He states he pays almost no attention to IV when selecting, precisely to avoid the trap. This is the single most counterintuitive rule in the methodology. |
| **ST-SEL-11** *(new v2.0)* | Realistic premium on a compliant name is **≈1% of collateral per cycle** (~11% annualized) | Calibration anchor from his KO-style worked example: 32 DTE, 0.30 delta, $79 strike, ~$0.85 credit. Any screen producing materially more than 1% per cycle is surfacing risk, not opportunity. Pairs with ST-SEL-10 as its quantitative test. |
| **ST-SEL-12** *(new v2.0)* | **Chart position matters.** Do not open at or near a multi-year high | Promoted from the Ford exchange: a trader assigned at $16 had opened near a 3-year high on a name that spent most of three years between $8.50 and $14. Entry point materially affects assignment probability independent of every other filter. |
| **ST-SEL-13** *(new v2.0)* | **Options liquidity** sufficient for tight bid/ask fills at target strikes | Roll execution quality depends entirely on it. A name that cannot be rolled cheaply has defeated the primary risk control before the trade is opened. |
| **ST-SEL-14** *(new v2.0)* | There are **no "ideal" wheel stocks**. The universe is the operator's own work | Explicit and repeated: it is up to each trader to select names they are good holding. He declines to publish his list (G-13). A screener produces candidates; it cannot produce a universe. |

---

## 3. Put Entry

| ID | Rule | Rationale |
|---|---|---|
| **ST-ENT-01** | Puts are **cash-secured** — the account can fund assignment | Definitional. Removes forced-liquidation and margin-call risk, which is what makes assignment an inconvenience rather than a crisis. |
| **ST-ENT-02** | **30–45 DTE** | Time decay accelerates in this window. Shorter tenors offer poor premium against gamma; longer tenors decay too slowly to be capital-efficient. |
| **ST-ENT-03** | **~0.30 delta (≈70% probability OTM) or lower** | Balances premium against assignment probability. Lower delta lifts win rate but thins premium below the point of meaningful return. |
| **ST-ENT-04** | Contract count sized to **assignment capacity** | The binding question is "how many hundred-share lots can I absorb," never "how much premium can I collect." Prevents catastrophic oversizing. |
| **ST-ENT-05** | Avoid holding through earnings or other known binary events; close or expire before, resume after | Binary events produce gaps; gaps defeat rolling. The strategy steps aside rather than pricing the event. Extended by him to CPI prints and Fed meetings. |
| **ST-ENT-06** | Log every credit and debit at the time of the trade | Net stock cost — the reference price for the entire assignment phase — is only knowable from an accurate ledger. |
| **ST-ENT-07** *(new v2.0)* | **Ladder into positions.** Open 1–2 contracts, add later in the week, up to the intended maximum on that name | Spreads entry risk across price and time within the tenor band. Explicitly his practice, always at the same 0.30 delta. |
| **ST-ENT-08** *(new v2.0)* | **No weeklies.** 7–10 DTE is rejected | A single assigned weekly — assigned because there was no time to roll — erases most of the perceived incremental profit from higher frequency. More trades, more risk, more complication, questionable additional return. Selecting tenor within 30–45 is judgment based on premium and event calendar; going below 30 is not. |

---

## 4. Order Mechanics

| ID | Rule | Rationale |
|---|---|---|
| **ST-ORD-01** *(new v2.0)* | Enter a **GTC limit order at 50% of credit immediately on fill** | This is automation, not a monitoring discipline. The position closes itself with the operator absent. His example: the order can fill while he is at the store. |
| **ST-ORD-02** *(new v2.0)* | Work the price by a penny or two on open and close | Each penny is $1 per contract; across thousands of trades this compounds materially. |
| **ST-ORD-03** *(new v2.0)* | **Never use market orders on options** | Options fills are unpredictable; a market order in a wide spread is an unbounded cost. |
| **ST-ORD-04** *(new v2.0)* | Set a broker alert at the **strike price** of every open put | The alert is the roll trigger's first condition (ST-ROL-01). This is what replaces continuous monitoring. |

---

## 5. Put Management

| ID | Rule | Rationale |
|---|---|---|
| **ST-MGT-01** | Close or roll at **50% of maximum profit** when meaningful time remains | The final 50% of premium decays slowest while carrying the most risk. Redeploying raises cycles per year. He frames it as permitted rather than mandatory; letting it expire is acceptable to him. See AL-MGT-01. |
| **ST-MGT-02** | When challenged, **roll for a credit** while a credit is obtainable | See Section 6 — rolling is promoted to its own domain in v2.0. |
| **ST-MGT-03** | Rolling may continue **indefinitely** while credits remain available | The constraint is economic, not temporal. |
| **ST-MGT-04** | **If a credit cannot be obtained, take assignment** | The critical exit rule. Paying a debit to escape converts a position that could still recover through covered calls into a realized loss. |
| **ST-MGT-05** | If fundamentals change, close at an overall net profit and move on | The clean exit path, distinct from the distressed exit under a kill switch. |
| **ST-MGT-06** *(new v2.0)* | Evaluate **P&L per name over time**, not per trade | He looks at year-to-date by ticker. A rolled position that closes at a scratch, viewed in isolation, looks like failure; viewed across the name's full history it is usually a win preserved. This framing is what makes the patience rules psychologically executable. |
| **ST-MGT-07** *(new v2.0)* | **Re-entry after a profitable close is conditional, not automatic.** Re-open on the same name only if it remains compliant, has no upcoming ER, and is not the better trade elsewhere in the watchlist | *Closes G-7.* Freed capital goes to the best available compliant trade, which is frequently a different name. |

---

## 6. Rolling — the primary risk control

Promoted to its own domain in v2.0. This is the mechanism that makes assignment rare, and it
contains the least automatable rule in the methodology.

| ID | Rule | Rationale |
|---|---|---|
| **ST-ROL-01** | **Two-conditional trigger.** Roll when (a) the underlying reaches the strike (ATM) **and** (b) the operator is convinced it will remain at or below that level | Both conditions are required. A stock at the strike during a broad market decline, where analysis says the business is unaffected, is a **hold** — he explicitly hesitates when a name is "flirting with the strike." The conviction clause is judgment and cannot be automated without becoming a different rule. |
| **ST-ROL-02** | Roll **out one to two weeks, same strike** | Short extensions preserve the ability to exit quickly when the underlying recovers. Long rolls collect more credit but lock capital and cannot be reversed. |
| **ST-ROL-03** | The best net credit occurs **at the money** | The debit to close rises as the option goes deeper ITM, while the extrinsic value available on the new put falls. The spread between them is widest precisely at the strike. Operationally: display the extrinsic value column on the chain. |
| **ST-ROL-04** | Improve the strike **only if a net credit still results** | Strike improvement is a bonus, never a reason to pay. |
| **ST-ROL-05** | **After a roll the objective changes** — exit at scratch or any small net profit as soon as available | A rolled position is a "problem child." It is no longer targeting 50%; it is targeting release of capital into untroubled trades. |
| **ST-ROL-06** | Total tenor bounded at approximately **60 DTE** | Beyond 60 days theta flattens and the position becomes unproductive against the collateral it consumes. Rolling 1–2 weeks at a time is ideal; 3–4 acceptable; past 60 days total is capital locked in an inefficient position. |
| **ST-ROL-07** | Earnings inside a roll chain: extend approximately **30 days past the report date** | Collects elevated pre-event premium and gives the underlying time to establish a post-event trend. If it gaps up, quick net profit; if not, the extra premium reduces net stock cost at eventual assignment. |
| **ST-ROL-08** | **The challenged name is frozen.** No new positions on an underlying already under management | Adding to a challenged name is doubling down. "When you find yourself in a hole the first thing to do is stop digging." Recycle capital into names unlikely to be challenged. |
| **ST-ROL-09** *(new v2.0)* | **The productivity floor is the credit itself.** Roll while a meaningful net credit exists; a credit of approximately **$0.01** is the signal to stop and accept assignment | *Closes G-2.* He states there is no surprise and no need to monitor constantly: a net credit cannot be collected forever, and when the put is deep enough ITM that only a penny is available, that is the clearly defined decision point. He has rolled chains for 6+ months before reaching it. Late-chain rolls are executed nearer expiry, around **7–10 DTE**, out one to two weeks. |

---

## 7. Assignment

| ID | Rule | Rationale |
|---|---|---|
| **ST-ASN-01** | On assignment compute **net stock cost** = strike paid − all premium collected on the position | Net stock cost, not the strike and not market price, is the reference for every subsequent decision. After a credit-positive roll chain it is frequently already below market. |
| **ST-ASN-02** | Selling the shares immediately and returning to puts is legitimate | Put-selling is generally the more profitable and more capital-efficient phase. Shares cannot be rolled. |
| **ST-ASN-03** | Selling a deep ITM call certain to be exercised is a valid accelerated exit | Same result as an outright sale, plus one more premium. |
| **ST-ASN-04** *(new v2.0)* | **Early assignment is rare, and rarer still with time remaining** | *Closes G-1.* Assignment two weeks out would be very unusual; the option would need to be ITM by roughly $10 or more to carry real risk. The overwhelming majority of assignments occur on expiration Friday, with notification the following day. |
| **ST-ASN-05** *(new v2.0)* | Early assignment concentrates in one identifiable condition: **extrinsic value near zero with little time to expiration** | At that point exercising is more efficient for the holder than selling to close. This is the only state that materially elevates the risk. |
| **ST-ASN-06** *(new v2.0)* | The **50% profit rule and active rolling together** keep positions out of that state | Closing at partial profit virtually eliminates the exposure. Corollary, stated bluntly: an operator worried about assignment is trading too large — the remedy is smaller size, not vigilance. |

---

## 8. Covered Calls

| ID | Rule | Rationale |
|---|---|---|
| **ST-CC-01** | Sell calls **above net stock cost** whenever possible | A call struck below net stock cost locks in a loss on exercise. |
| **ST-CC-02** | Where a below-cost strike appears unavoidable, prefer a **more distant expiration** at lower premium | Reduces early-assignment risk and buys time. Explicitly trading premium for optionality. |
| **ST-CC-03** | Same parameters as puts: 30–45 DTE, ~0.30 delta or lower | Consistency across phases. |
| **ST-CC-04** | Close or roll at **50% profit** | Same logic as ST-MGT-01. |
| **ST-CC-05** | Roll for a credit where possible; otherwise **allow exercise**, particularly when the strike sits above net stock cost | Above net cost, exercise is a profitable outcome. There is nothing to defend. |
| **ST-CC-06** | Log credits, debits, and dividends captured | Dividends reduce net stock cost and materially accelerate recovery on an underwater position. |
| **ST-CC-07** | Continue until net stock cost falls below the strike, then allow the shares to be called away | Exit condition for Phase 2. Closing the call and selling outright achieves the same result, sometimes at lower cost. |
| **ST-CC-08** *(new v2.0)* | **His actual practice is never to sell below net stock cost.** Sit on hands and wait | Stated directly: he hates losing money and will SOH rather than lock a loss. This supersedes the permissive reading of ST-CC-02 — the distant-expiration variant is the fallback, not the default. |
| **ST-CC-09** *(new v2.0)* | Where no workable strike exists above net cost, the repair is **selling additional puts below market** — the covered strangle — but only if fresh analysis confirms the name is still sound | *Closes G-5.* Averaging down through assignment lowers the blended basis quickly, which restores the ability to sell calls above cost. **Prohibited on a name with a fundamental change** — that is doubling down on a troubled position. Governed by the concentration ceiling (ST-SIZ-01). |
| **ST-CC-10** *(new v2.0)* | Where net stock cost is **below** market, exit quickly — sell shares, or sell an ATM/ITM call for one more premium on the way out | The objective in Phase 2 is to get called away for a net profit as soon as possible and return to Phase 1, not to maximize calls collected. |
| **ST-CC-11** *(new v2.0)* | **Do not chase a rallying stock** by closing the call | The call's loss generally exceeds the shares' incremental gain. Regret over foregone upside is a named psychological hazard, and executed properly the position still profits. |

---

## 9. Cash and Reserve

| ID | Rule | Rationale |
|---|---|---|
| **ST-CSH-01** | Maintain **50% of buying power in reserve** | Measured as options BP against net liquidity: at $100K net liq, work to keep $50K of options BP. **This is the load-bearing risk control of the program.** His own account: he did *not* hold it at small account size, and the direct consequence was being unable to roll, which forced closing at losses. He notes 60%+ deployment is acceptable for short periods against specific opportunities. |
| **ST-CSH-02** | **No margin as buying power.** Margin availability is for emergencies only | Traders running 90%+ deployed are the ones taken out by market events, through forced losses rather than chosen ones. |
| **ST-CSH-03** *(new v2.0)* | Where the reserve is held does not matter provided it is **accessible before the broker liquidates** | Settlement is the constraint: most funds take two days, so an assignment on Tuesday against a fund sale leaves the account short until Thursday. Also flagged: a money-market proxy he used (ICSH) fell with the market in March 2020, so "safe" instruments are not reliably safe at the exact moment the reserve is needed. |
| **ST-CSH-04** *(new v2.0)* | Returns are measured on **full net liquidity**, including the reserve | Capital is constantly turning over and options are already leveraged. The reserve is not idle — it prevents losses, which is a return contribution. Measuring on deployed capital only would flatter the result and quietly incentivize abandoning the reserve. |
| **ST-CSH-05** | Trade from a **dedicated account**, separated from retirement, long-term, and emergency capital | Prevents convoluting performance measurement and makes contribution and withdrawal legible. |

---

## 10. Position Sizing

| ID | Rule | Rationale |
|---|---|---|
| **ST-SIZ-01** | **≈5% of the account per name**, up to 10% for a name of exceptional quality | *Closes G-4 in combination with ST-CSH-01 and ST-ENT-04.* Prevents a single name's news or movement from damaging the account. The 10% ceiling is stated as an exception he has used, not a second tier. |
| **ST-SIZ-02** | Prefer **one contract across ten names** to ten contracts in one | Explicit: the attraction of a large single-name premium is exactly the trap. Diversification is what makes the crash math work (ST-EVT-04). |
| **ST-SIZ-03** *(new v2.0)* | The concurrent-position ceiling is set by the **reserve policy**, not by a position count | *Closes G-10.* Total collateral committed must leave the reserve intact; that arithmetic, not a fixed number, is the ceiling. |

---

## 11. Market Events

| ID | Rule | Rationale |
|---|---|---|
| **ST-EVT-01** *(new v2.0)* | In a broad drawdown: **do not panic; triage position by position** | *Closes G-3.* Close what can be closed at modest loss, roll what can be rolled, accept assignment where indicated. Written live during March 2020, not reconstructed afterward. |
| **ST-EVT-02** *(new v2.0)* | **Cap the assignments taken** during a dislocation | The binding constraint in a crash is not any single position — it is that each assignment consumes reserve, and consuming it all removes every management option and forecloses participation in the recovery, where much of the profit is made. Taking too many assignments "handcuffs" the account. |
| **ST-EVT-03** *(new v2.0)* | Reduce size, widen laddering, tighten selection; shorter tenors (15–20 DTE) are acceptable **only in a fast-moving market** | His documented adaptation, not a general permission. Also documented: defined-risk spreads used during the crash specifically because IV was extreme and downside protection was wanted — explicitly not recommended in normal conditions, where they profit less and are harder to roll. |
| **ST-EVT-04** *(new v2.0)* | **Simultaneous assignment of an entire book is a misconception** — for a diversified book | Put holders in a falling market overwhelmingly sell to close rather than exercise, because closing captures remaining extrinsic value. Drops are also dispersed: some names crash, some fall modestly, some rise. **The fable becomes true for single-underlying books** — and he names traders holding only SPY as the most exposed, not the least. |
| **ST-EVT-05** *(new v2.0)* | **Do not hedge with long puts** | The cumulative cost across thousands of trades exceeds what is lost in downturns; black swans are by definition unhedgeable in advance. Holding high-quality names that fall less and recover faster *is* the hedge. |

---

## 12. Performance Expectations

| ID | Rule | Rationale |
|---|---|---|
| **ST-PER-01** | Stated envelope: **10–20%+**, slow and boring, driven by selection, management experience, and patience | A constraint on strategy design, not merely an expectation. A rule set engineered above this envelope is a higher-risk variant wearing the same name. See C-1. |
| **ST-PER-02** *(new v2.0)* | Personal benchmark: **15%**, against the ~10% S&P long-run average | Below 15% sustained, either execution is wrong or options are the wrong instrument for that operator. His own reported range is 15–40% depending on year; 2022 was among his worst at +12% against S&P −18%. |
| **ST-PER-03** *(new v2.0)* | **Returns are trader-dependent, not strategy-dependent** | The dispersion comes from stock quality, roll aggressiveness, entry delta, premature closing, and patience. The question is never whether the wheel beats the index but whether *this operator* does. |
| **ST-PER-04** *(new v2.0)* | **The wheel cannot be fully backtested; backtest results are not proof** | The roll trigger's conviction clause (ST-ROL-01) does not exist as a historical data field. A backtest necessarily tests a mechanical shadow — the rules with the judgment removed. Worth measuring; not validation. **This is why the validation gate is paper trading with logged reasoning.** |
| **ST-PER-05** *(new v2.0)* | Options are for **short-term income**; index investing is for **long-term appreciation** | Different instruments for different objectives. An operator seeking maximum long-horizon appreciation should hold an index fund. |

---

## 13. Discipline and Philosophy

He ranks the failure modes explicitly, and the ordering is itself a finding: he does not rank
crashes, assignment, or drawdowns at the top. He ranks **the operator's response** to them.

| ID | Rule | Rationale |
|---|---|---|
| **ST-PHI-01** | **Impatience is the largest single source of loss** in the strategy | Named directly and repeatedly. Three concrete manifestations: closing a CSP early at a debit when it cannot be rolled; buying back a call at an inflated price to "save" the stock; abandoning a covered-call recovery that was working but slow. Recovery may take months — that is the strategy working, not failing. |
| **ST-PHI-02** | **Managing by DTE is rejected.** Manage by price relative to strike | A day count cannot indicate an adjustment without knowing where the stock is. If the price stays above the strike the position reaches 50% eventually. Rolling on an arbitrary DTE while the trade is unchallenged converts noise into transaction costs. He states his live experience does not match the backtests that recommend it. |
| **ST-PHI-03** | **Adjustments are an art. Few hard rules exist and none work in all situations** | Direct: do not overthink; most of what is asked about is judgment learned over a year or two of trading. This rule is the boundary condition on the entire project — it defines what may be automated and what may not. |
| **ST-PHI-04** *(new v2.0)* | **SOH — sit on hands.** "Don't do something, just stand there" | Inaction is a position. A week with no compliant entry is a normal week. |
| **ST-PHI-05** *(new v2.0)* | Treat trading as a **business**; remove emotion | Corollary and diagnostic: if you are worried about a position, you are trading with too much risk. The remedy is size, not willpower. |
| **ST-PHI-06** *(new v2.0)* | **The plan must be the operator's own.** He did not invent the wheel; he refined and documented it his way, and instructs others to do the same | The methodology is a starting point to be modified deliberately and documented, not a system to be adopted verbatim. This is the rule that authorizes Part II to exist — and requires every entry in it to be justified. |

---

# PART II — AdVenture Labs Modifications

Everything below is **ours**, not his. Each entry states what it adds, why, and what it costs.

## 14. Selection Additions

| ID | Addition | Rationale | Cost / Risk |
|---|---|---|---|
| **AL-SEL-01** *(rewritten v2.0)* | Below $20K net liquidity, **2–3 concurrent open positions maximum** — a constraint on *positions*, not on *names* | v1.0 stated "1–2 tickers maximum," which read as a universe constraint and contradicted AL-SIZ-01's three-name minimum. The binding constraint was always collateral, never ticker count. **Resolves C-3.** | None over v1.0. This is a clarification of intent, not a loosening. |
| **AL-SEL-02** *(new v2.0)* | **Zones are derived from account size, not fixed.** `max_strike = (net_liq × per_name_cap) ÷ 100`, with the ST-SEL-04 floor of $10 applying absolutely | ST-SEL-03's $10–50 band is a capital-efficiency constraint, and he confirms it moved up as his account grew. Hard-coding it freezes a rule whose author explicitly unfroze it. Derivation makes the band correct at every account size and turns the growth path into arithmetic rather than a future amendment. | Zone boundaries move as the account moves, which requires hysteresis to prevent flapping. See G-12. |
| **AL-SEL-03** *(new v2.0)* | Out-of-zone candidates are **displayed but locked.** Entry requires an explicit override with logged rationale and a displayed concentration figure | Visibility without permission. Hiding higher zones removes the growth ladder; unlocking them removes the sizing discipline. A locked row that shows *"if assigned: 41% of net liq — Zone 2, unlocks at ~$60K"* does both jobs. | An override path exists, and overrides get used. Mitigated by AL-OPS-05: every override is a logged prediction that gets scored. |
| **AL-SEL-04** *(new v2.0)* | **Written thesis gate.** A name is not tradeable until a `notes/<TICKER>.md` exists containing the business case and the name-specific kill-switch conditions | Implements the Proposal's §8.3 Stage 4 as a hard precondition rather than a research step. ST-SEL-09 requires willingness to own for twelve months; an unwritten thesis is an unexamined one. It also makes AL-RSK-01 name-specific instead of generic. | Friction on adding names — which is the intent. Adding a name is meant to be harder than trading one. |
| **AL-SEL-05** *(new v2.0)* | **Zone exit while held.** A held name that appreciates out of band is not force-exited; it is flagged, and no *new* position opens on it until it re-enters band or the account grows into the next zone | *Closes G-8.* Appreciation is a profitable outcome (ST-CC-11) and forcing an exit to satisfy a sizing rule would convert a win into a tax event. The rule constrains new commitments, not existing ones. | A held name may sit outside policy for an extended period. Bounded by the fact that Phase 2 ends in the shares being called away. |
| **AL-SEL-06** *(new v2.0)* | **Market cap is a separate filter from share price.** Price governs sizing; market cap governs quality, liquidity, and gap risk. Floor: mid-cap or above at pilot scale | Conflating the two is how a screen rejects a sound $15 large-cap and accepts an unsound $45 micro-cap. ST-SEL-05 (gap risk) and ST-SEL-13 (liquidity) are both really market-cap proxies. | Narrows the universe. Acceptable — breadth is not scarce. |
| **AL-SEL-07** *(new v2.1)* | **ETF structural screen.** An ETF is admissible only where it represents passive ownership of an index, sector, or asset class. Derivative-income products are excluded. Three disqualifiers, applied at Stage 1: issuer/strategy name pattern; distribution yield above a 20% ceiling; null sector classification on a fund not named in `universe.include` | The 2026-08-13 run filled **every Zone 1 slot** — the only immediately tradeable zone — with derivative-income ETFs: COYY 386%, TSYY 201%, YBTC 81%, BITY 57%, BAGY 38%. Their distributions are written option premium, not earnings, so ST-SEL-06 reads them as extraordinary dividends; their structural NAV decay reads to ST-SEL-12 as a deep discount from the two-year high. The screen was rewarding capital destruction. Selling puts on a fund that already sells calls also inverts the strategy — the premium the Wheel exists to collect has been sold twice. ST-SEL-08 admits conventional ETFs; this bounds that exception to what "conventional" was always meant to mean | A conventional fund with an unusually high distribution can be caught by the ceiling. The `universe.include` list bypasses all three filters and is the documented escape hatch — SPY and QQQ pass through it, being themselves unclassified by sector. |

## 15. Sizing and Portfolio Additions

| ID | Addition | Rationale | Cost / Risk |
|---|---|---|---|
| **AL-SIZ-01** | Minimum **3 names across at least 2 sectors**; maximum **1 contract per name** at pilot scale | Partial mitigation of unavoidable pilot concentration. Not a claim that the 5% policy is honoured — it is not, and §4.3 of the Proposal states so plainly. | Concentration remains the program's principal structural weakness until roughly $60K. |
| **AL-SIZ-02** *(new v2.0)* | **Sector ceiling: no more than 50% of deployed collateral in one GICS sector** | Sector-wide selloffs are the correlation the name-level 5% rule does not see. Three regional banks at 5% each is a 15% position in one shock. | At pilot scale with 2–3 positions the ceiling binds almost immediately, which effectively enforces AL-SIZ-01's two-sector minimum. Intended. |
| **AL-SIZ-03** *(new v2.0)* | **Industry concentration is a warning, not a block** | Two semiconductor names in different GICS sub-industries are not diversified in any way that matters during a semiconductor selloff. But sub-industry taxonomies are noisy, and a hard rule on noisy data produces false blocks. Warn and log. | Warnings get dismissed. Accepted — this is deliberately the softer of the two. |
| **AL-SIZ-04** *(new v2.0)* | **Flag earnings clustering:** two or more open or candidate positions reporting in the same week | A hidden correlation the sector view misses entirely. Names in unrelated sectors reporting the same week produce a concentrated event risk that no diversification rule catches. Data already retrieved for ST-ENT-05. | Low cost — this is a display, not a constraint. |

## 16. Cash Additions

| ID | Addition | Rationale | Cost / Risk |
|---|---|---|---|
| **AL-CSH-01** | Hard deployment ceiling of **65%**, with no more than **two consecutive weeks** above the 50% average | Operationalizes his "60%+ for short periods" as a bounded, checkable rule. Without a duration limit, "short periods" drifts. | May force declining a good entry. That is the rule working. |
| **AL-CSH-02** *(new v2.0)* | **Assignment capacity must be computed and displayed before every entry:** total collateral obligation if every open position were assigned, against available reserve | ST-CSH-01 is the load-bearing control, and a control that is not displayed is not operating. This makes the reserve visible at the moment of the decision that would breach it, rather than in a monthly review. | None. This is the single highest-value output in the tool. |

## 17. Management and Operations Additions

| ID | Addition | Rationale | Cost / Risk |
|---|---|---|---|
| **AL-ENT-01** | Entry gated on **IV Rank > 30** | Selling when IV is historically elevated improves premium per unit of risk. | Reduces trade frequency; may idle capital in low-IV regimes. In direct tension with his continuous-selling cadence — **C-2 remains open**, and v2.0 does not resolve it. |
| **AL-MGT-01** | 50% close is **mandatory**, not permitted | Compresses cycle length; lifts annualized return. | Removes discretion where holding to expiry would have been optimal. Adds transaction cost. **C-4 open.** |
| **AL-RSK-01** | Formalized **kill switch** with enumerated triggers: dividend cut, consensus flip, cash-flow deterioration, accounting irregularity, going-concern disclosure, or any development reversing the ST-SEL-09 answer | His non-viability standard is directionally clear but not operationally specific. Now name-specific via AL-SEL-04. | False positives exiting recoverable positions. **C-5 open.** |
| **AL-OPS-01** | **Three-bucket cash architecture** — trading reserve, tax reserve at 35% of realized gains within 7 days, free cash | Premium on individual equities is short-term capital gain, taxed as ordinary income, unwithheld. Segregating on realization prevents the April shortfall. | Reduces compounding capital. Operational overhead. |
| **AL-OPS-02** | No trade within **30 minutes of market open** | Opening auction imbalances produce unrepresentative pricing and wider spreads. | Marginal. |
| **AL-OPS-03** | **Amendment freeze** — no rule changes while any position is at an unrealized loss, or within 72 hours of a losing outcome | Operationalizes ST-PHI-01 and ST-PHI-05 as a structural constraint rather than an instruction to a human. | None identified. |
| **AL-OPS-04** | Explicit **rationale capture** on every rule (this document) | Rules without reasoning cannot generalize and cannot be intelligently amended. | Documentation overhead. |
| **AL-OPS-05** *(new v2.0 — **RETIRED 2026-09-08**, see Constitution v2.1 Change Log; rule text preserved below as audit trail, not as a live requirement)* | **Append-only decision record.** Every judgment call is logged at the time of decision with a required **prediction** field and the governing rule ID; outcomes are attached deterministically on close | This is the mechanism that makes the judgment layer measurable. A rationale without a prediction cannot be scored, only re-read. Divergence between rule-implied action and operator action is the primary amendment signal under Constitution Article XIII. | Discipline cost at the moment of decision. Non-negotiable — Proposal criterion 4. |
| **AL-OPS-06** *(new v2.0)* | **Snapshot-then-score.** Market data is fetched, written timestamped to durable storage, and scored from the snapshot — never scored from a live call | Makes every run reproducible and makes golden-file regression testing possible at all. Isolates the only nondeterministic boundary in the system at its edge. | Storage growth. Negligible. |

## 18. Modifications to Stated Parameters

| Parameter | Source | AdVenture Labs | Basis |
|---|---|---|---|
| Target annual return | 10–20%+ | **15–25%**, planning case only | Positioned inside his envelope; upper bound above his midpoint. **C-1 open.** |
| Price range | $10–$50 fixed | **Derived from account size**, $10 floor absolute | AL-SEL-02. Adopts his stated intent rather than his stated number. |
| Market cap | Not specified | **Mid-cap or above** at pilot scale | AL-SEL-06. |
| DTE | 30–45 | **Unchanged** | — |
| Delta | ~0.30 | **Unchanged** | — |
| Profit-take | 50%, permitted | 50%, **mandatory** | AL-MGT-01. |
| Watchlist size | ~10 names | **~10 monitored, 3–5 with written theses, 2–3 concurrent positions** below $20K | AL-SEL-01 + AL-SEL-04. Three distinct tiers, previously conflated. |
| Sector policy | Not specified | **≥2 sectors, ≤50% per sector** | AL-SIZ-01/02. |

---

# PART III — Unresolved Conflicts

Documented, not resolved. Resolution requires evidence, and this document is not where evidence
is produced.

**C-1 — Return target.** His envelope tops out near 20% and he is emphatic the strategy is slow.
Our planning case is 15–25%. The overlap is genuine but our upper bound sits above his midpoint,
and the mechanism we rely on to reach it (mandatory 50% close, IVR gating) is our addition.
*Resolution: mechanical floor simulation must show cycle compression delivers the increment without
a corresponding rise in drawdown.*

**C-2 — IVR gating versus continuous selling.** His model is persistent premium-selling. Our IVR
filter deliberately introduces idle periods. Higher premium per trade, fewer trades. *Resolution:
simulate both variants; compare annualized return and drawdown. Note that AL-ENT-01 also now depends
on an IV Rank data source we have not specified — see G-14.*

**C-3 — Watchlist breadth versus concentration.** ~~He maintains roughly ten tradeable names; we
proposed one to two.~~ **RESOLVED in v2.0.** The conflict was terminological. He maintains ~10
*watched* names and holds a small number of *concurrent positions*; our v1.0 rule constrained the
wrong noun. AL-SEL-01 now constrains concurrent positions, AL-SEL-04 constrains thesis-backed names,
and ST-SEL-07 governs the watchlist. Three tiers, no conflict.

**C-4 — Mandatory versus discretionary profit-taking.** He permits expiry. We mandate closing at
50%. In low-IV conditions round-trip cost may exceed the benefit of freed capital. *Resolution: model
transaction costs explicitly; consider a minimum-premium threshold below which the mandate suspends.*

**C-5 — Kill switch calibration.** His standard is judgment-based; ours is rule-based. Rule-based
triggers are codeable and will produce false positives. *Resolution: test triggers against historical
events to measure false-positive rate. Partially mitigated by AL-SEL-04, which makes triggers
name-specific rather than generic.*

**C-6 — Zone locking versus operator sovereignty** *(new v2.0)*. AL-SEL-03 locks out-of-zone
candidates, but ST-SEL-14 and ST-PHI-06 both state the universe and the plan are the operator's own
work. A tool that blocks is asserting authority the source explicitly reserves to the trader.
*Current resolution: lock is soft — display, warn, require an override with a logged prediction.
Revisit if override frequency exceeds ~1 per quarter, which would indicate the zone math is wrong
rather than the operator undisciplined.*

---

# PART IV — Gap Register

## Closed in v2.0

| # | Question | Resolution |
|---|---|---|
| **G-1** | Early assignment — frequency, conditions, response | **Closed** → ST-ASN-04, -05, -06 |
| **G-2** | The point at which rolling stops being productive | **Closed** → ST-ROL-09 (~$0.01 net credit is the stated decision point) |
| **G-3** | Behavior during a broad market drawdown | **Closed** → ST-EVT-01 through -05 |
| **G-4** | Contract sizing formula | **Closed** → ST-SIZ-01 (5%/10%) + ST-CSH-01 (50% reserve) + AL-CSH-02 (capacity display) |
| **G-5** | Covered calls when net stock cost is far above market | **Closed** → ST-CC-08 (SOH, never below cost) + ST-CC-09 (covered strangle repair, conditional) |
| **G-7** | Re-entry timing after a completed cycle | **Closed** → ST-MGT-07 (conditional, not automatic) |
| **G-8** | A held name that exits the price band | **Closed** → AL-SEL-05 (flag, freeze new entries, do not force exit) |
| **G-10** | Position count ceiling relative to account size | **Closed** → ST-SIZ-03 (ceiling is reserve arithmetic, not a count) |

## Open

| # | Question | Why it matters | Priority |
|---|---|---|---|
| **G-6** | **Ex-dividend early assignment risk on covered calls** | ITM calls face elevated early exercise before ex-dividend. ST-SEL-06 favours dividend payers, making this recurring rather than an edge case. ST-ASN-04/05 address puts only — his early-assignment material is put-specific and does not transfer. | **High** |
| **G-9** | **Assignment during a roll; partial fills** | Operational edge case with real consequences: a roll is two legs, and a state where one leg fills and the other does not is undefined. | Medium |
| **G-11** *(new)* | **Sector taxonomy authority** | AL-SIZ-02/03 require a classification scheme. GICS, the data provider's own labels, and common usage disagree — materially, for conglomerates and for anything adjacent to technology. Which is authoritative, and what happens when a name is reclassified? | **High — blocks AL-SIZ-02** |
| **G-12** *(new)* | **Zone boundary hysteresis** | AL-SEL-02 derives zones from a moving account balance. Without a hysteresis band a name near a boundary flips eligibility week to week, and week-over-week diffs become noise. | Medium — blocks AL-SEL-02 |
| **G-13** *(new)* | **Universe derivation without a reference list** | He declines to publish his own names by policy (ST-SEL-14), so there is no ground truth against which to validate the screen. The screen can be checked for rule compliance but not for selection quality. | Medium — accepted limitation, documented rather than solved |
| **G-14** *(new)* | **IV Rank source and definition** | AL-ENT-01 gates on IV Rank > 30, but IV Rank is a derived metric with no standard definition (lookback window, IV series used). Under the current data architecture it may not be directly available and may require computing from a stored IV history we do not yet keep. | **High — blocks AL-ENT-01** |

### Sourcing protocol

Reddit is not machine-retrievable. Material is collected manually and condensed into the Distilled
Reddit Transcripts before promotion.

On ingestion, each answered gap is promoted into Part I with a rule ID and rationale, and moved to
the Closed table above with its resolution recorded. **Document version increments on every
promotion.** G-11, G-12, and G-14 are *not* sourcing gaps — they are design decisions we owe
ourselves, and no amount of additional Reddit material will close them.

---

## Appendix A — Load-Bearing Rules

If any of these fail, the program's risk argument fails with them. Everything else degrades
gracefully.

| Rule | What it holds up |
|---|---|
| **ST-CSH-01** | Everything. An account without reserve in a crash has no management options at all. |
| **ST-ROL-01** | The primary risk control, including its unautomatable conviction clause. |
| **ST-SEL-09** | The entire risk claim in ST-FRM-04. If false, the strategy's risk model does not apply. |
| **ST-MGT-04** | The prohibition on paying a debit to escape — the most expensive available mistake. |
| **ST-SIZ-01** | The defense against selection error. Not honoured at pilot scale; see Proposal §4.3. |
| **ST-PER-04** | Why validation is paper trading with logged reasoning rather than a backtest. |
| **AL-OPS-05** | The only mechanism by which any of the above becomes measurable. |

## Appendix B — v1.0 → v2.0 Crosswalk

Every v1.0 identifier and its v2.0 successor. No v1.0 ID should appear in any document after this
version.

| v1.0 | v2.0 | Note |
|---|---|---|
| ST-SEL-01…09 | **unchanged** | SEL-10 through -14 are new |
| ST-ENT-01…06 | **unchanged** | ENT-07, -08 are new |
| ST-MGT-01 | ST-MGT-01 | unchanged |
| ST-MGT-02 | **ST-ROL-01** | promoted to ROL domain and expanded to the two-conditional form |
| ST-MGT-03 | **ST-ROL-09** | now bounded by the productivity floor |
| ST-MGT-04 | ST-MGT-04 | unchanged |
| ST-MGT-05 | ST-MGT-05 | unchanged |
| ST-ASN-01…03 | **unchanged** | ASN-04, -05, -06 are new |
| ST-CC-01…07 | **unchanged** | CC-08 through -11 are new |
| ST-RSK-01 | **ST-PHI-01** | domain retired |
| ST-RSK-02 | **ST-PHI-01** | merged — same failure mode |
| ST-RSK-03 | **ST-PHI-01** | merged — same failure mode |
| ST-RSK-04 | **AL-RSK-01** | was always closer to our kill switch than to his practice |
| ST-RSK-05 | **ST-ASN-01** | net stock cost mechanics |
| ST-RSK-06 | **ST-CC-07** | covered call recovery |
| ST-RSK-07 | **ST-CC-05** | exercise above net cost is profitable |
| ST-RSK-08 | **ST-CC-11** | do not chase |
| ST-RSK-09 | **ST-CC-11** | merged |
| ST-OPS-01 | **ST-ENT-06** | ledger discipline |
| ST-OPS-02 | **ST-MGT-07** | review before redeployment |
| ST-OPS-03 | **ST-FRM-01** | the cycle is the strategy |
| AL-SEL-01 | **AL-SEL-01 (rewritten)** | constrains positions, not tickers |
| AL-ENT-01, AL-MGT-01, AL-RSK-01, AL-OPS-01…04 | **unchanged** | — |

---

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | Jul 2026 | Initial draft from core guide. 10 gaps open. |
| **2.1** | **2026-08-16** | Added **AL-SEL-07** (ETF structural screen). Promoted from a live-run failure rather than from the Transcripts: the 2026-08-13 screen returned an all-derivative-income Zone 1, exposing that ST-SEL-08's conventional-ETF exception had no stated bound. No existing rule amended; ST-SEL-06 and ST-SEL-12 are unchanged and now see a universe those products cannot enter. |
| **2.0** | **2026-08-03** | Promoted 8 gaps from Distilled Transcripts. Added domains FRM, ORD, ROL, CSH, SIZ, EVT, PER, PHI; retired RSK with full crosswalk. 34 new ST- rules, 12 new AL- rules. Resolved C-3; opened C-6. Opened G-11, G-12, G-13, G-14. Zone derivation (AL-SEL-02/03), thesis gate (AL-SEL-04), sector governance (AL-SIZ-02/03/04), assignment capacity display (AL-CSH-02), decision record (AL-OPS-05), snapshot discipline (AL-OPS-06). |

---

*Methodology in Part I is attributed to ScottishTrader and restated in AdVenture Labs' own words for
internal specification use; he retains all rights to his words and has no association with this
document. Parts II–IV are AdVenture Labs work product. This is a personal planning document, not
financial advice. Options trading involves substantial risk of loss, including loss of principal.*
