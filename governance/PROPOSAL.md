---
VERSION: 1.2
DATE: 2026-09-08
SUPERSEDES: Investment Proposal v1.0 (July 2026, `adventure-labs-wheel-engine-proposal-v1.pdf`)
STATUS: canonical
DELIVERABLE: 3 of 8
MODULE: 1 — The Wheel Engine
REISSUE_TRIGGER: v2.0 issues when §8.3 Stage 4 completes and the underlying universe is named
---

# AdVenture Labs · Module 1 — The Wheel Engine

### A Systematic Volatility-Risk-Premium Income Sleeve

**Investment Proposal · Deliverable 3 of 8**

---

**Framing note to the reader.** This document is written to institutional standards because the
discipline of that format is useful, not because the strategy is an institutional product. It is
not. This is a personal systematic income sleeve deploying $9,000–$15,000 of the author's own
capital. At that size the strategy would not clear any professional hurdle rate on a risk-adjusted
basis, does not scale into an institutional capital base, and captures a well-documented premium
available to any retail participant with sufficient discipline. Nothing here is proprietary. The
value of writing it this way is that a proposal which must survive adversarial review is a proposal
whose assumptions have been made explicit — which is precisely what protects the capital when the
market makes them uncomfortable.

**Governing documents.** Strategy Constitution **v2.0** (binding rules) · ScottishTrader Source
Brief **v2.0** (methodology provenance) · Distilled Reddit Transcripts (primary source). Rule
identifiers throughout (`ST-`, `AL-`) reference the Source Brief; Article and § references reference
the Constitution.

> **v1.1 note on citations.** v1.0 of this document cited Source Brief v2.0 and Constitution v2.1
> before either existed — roughly forty rule IDs across eight domains that had no referent. Those
> documents now exist as Source Brief v2.0 and Constitution **v2.0**, and every citation in this
> version has been checked against them. Where v1.0's forward-reference was wrong rather than merely
> early, the change is flagged inline.

---

## Executive Summary

**The proposal.** Deploy $9,000–$15,000 into a systematic cash-secured put and covered call program
on 3–5 fundamentally sound, moderate-volatility US equities. The program harvests the structural gap
between implied and realized volatility, governed by a written rule set that removes discretion from
the decisions where discretion historically destroys the strategy.

**What is being claimed.** Disciplined capture of the volatility risk premium, inside a defined risk
framework, with a documented set of conditions under which the program stops. The edge is entirely
in execution consistency and capital reserve policy — not in information, speed, or security
selection.

**What is explicitly not being claimed.** No alpha. No informational advantage. No market-timing
capability. No claim that this strategy outperforms a passive equity index on a risk-adjusted basis
in a rising market — it does not, and the covered call leg guarantees it will not. The proposal
argues that a capped-upside, premium-generating, cash-collateralized position is a legitimate income
instrument, not that it is a superior growth instrument.

### The core economics in one paragraph

An option seller is an insurer. Implied volatility — the price of the insurance — persistently
exceeds subsequently realized volatility across liquid US equities. This gap is not a market
inefficiency; it is compensation for accepting a genuinely unpleasant payoff profile: small,
frequent gains punctuated by rare, large losses. The strategy accepts that profile deliberately, and
manages the tail with three mechanisms: (1) collateralization, which eliminates forced liquidation;
(2) underlying selection restricted to businesses the operator will hold through a drawdown, which
converts a loss event into a holding period; and (3) a 50% capital reserve, which preserves the
ability to roll, absorb assignment, and buy the recovery.

### Headline parameters

| Parameter | Specification | Governing rule |
|---|---|---|
| Instruments | Cash-secured puts; covered calls post-assignment | ST-FRM-01 |
| Underlyings | 3–5 US equities, **within the derived zone** for account size | ST-SEL-01…14, **AL-SEL-02** |
| Market cap | Mid-cap or above at pilot scale | **AL-SEL-06** |
| Tenor | 30–45 DTE; no weeklies | ST-ENT-02, ST-ENT-08 |
| Strike | ~0.30 delta (≈70% probability OTM) | ST-ENT-03 |
| Profit exit | GTC limit at 50% of credit, entered on fill | ST-ORD-01, AL-MGT-01 |
| Deployment ceiling | 50% of net liquidity average; 65% hard cap | ST-CSH-01, AL-CSH-01 |
| Sector policy | ≥2 sectors; ≤50% of collateral per sector | **AL-SIZ-01, AL-SIZ-02** |
| Leverage | None. Fully collateralized, no margin as buying power | ST-CSH-02 |
| Expected assignment | 2–3 per year across the book, not per position | **ST-FRM-03** *(v1.0 cited ST-FRM-01)* |
| Base-case return | 15–25% on full account, regime-conditional | Const. §12.2 |
| Validation gate | Paper trading with logged reasoning — not backtest | ST-PER-04 |

### Capital request and structure

$9,000–$15,000, self-funded, held in a dedicated brokerage account separated from all long-term,
retirement, and emergency capital (ST-CSH-05). Of that, no more than half is deployed as option
collateral at any time. Effective at-risk capital in the base case is therefore $4,500–$7,500,
against which the reserve stands as both risk control and opportunity capital.

---

## 1. Investment Thesis

### 1.1 The premium being harvested

Across liquid US equity options, implied volatility embedded in option prices exceeds the volatility
subsequently realized by the underlying, on average and over time. The seller is paid the
difference. This is the volatility risk premium, and it is among the most extensively documented
return sources in the literature — a fact which is itself the point: **a well-known premium
available to anyone is not an edge, it is a job.** The return accrues to whoever is willing and
structurally able to hold the position through the conditions that make it uncomfortable.

The premium exists because the payoff is unattractive. Selling puts produces many small wins and
occasional large losses. Institutions face mark-to-market and redemption pressure that makes this
profile hard to hold; retail participants face psychological pressure that does the same. The
premium compensates structural and behavioural capacity to endure the shape of the return — not
insight.

### 1.2 Why a small, self-funded, unlevered account is a legitimate holder

The constraints that make institutions poor holders of this exposure are largely absent here:

— **No redemption risk.** There is no outside capital that can withdraw at the bottom.
— **No mark-to-market reporting.** No quarter-end pressure to close a position that is temporarily
underwater but structurally sound.
— **No leverage.** Every position is fully cash-collateralized, so an adverse move cannot produce a
margin call or a broker-initiated liquidation. **This is the single most important structural
feature of the program** (ST-CSH-02).
— **Long horizon.** Positions can be held to recovery over months. Assignment converts an option
loss into an equity holding period, which is only survivable if the operator can wait.

**The honest counterweight.** The account also carries constraints institutions do not: at $9–15K,
per-name concentration runs three to six times the target policy limit (AL-SIZ-01), diversification
is limited to 3–5 names, and a single selection failure has material portfolio impact. This is the
principal weakness of the proposal and is treated as such throughout — see §4.3 and §9.1.

### 1.3 What this strategy is not

**Not alpha.** Security selection is a risk filter, not a return driver — its purpose is to ensure
that assignment produces a holdable asset, not to identify undervaluation.

**Not an index substitute.** The covered call leg caps upside by construction. In a strong bull
market this program underperforms simply holding the underlying, and that is a designed property,
not a flaw (Const. §12.6).

**Not scalable.** The methodology caps single-name exposure at 5% of the account (ST-SIZ-01), which
at institutional scale would require a book far wider than the selection discipline can support.
The strategy works because it is small.

**Not automatable end-to-end.** The central management decision — whether to roll a challenged
position — is explicitly conditioned on operator conviction about the underlying's forward path
(ST-ROL-01). This is judgment, and the source is emphatic that adjustments are an art that firm
rules cannot fully cover (ST-PHI-03). The architecture in §7 is designed around this constraint
rather than pretending to solve it.

---

## 2. Strategy Mechanics

This section is deliberately detailed. The program's risk is concentrated in the management
decisions, not the entry, and those decisions cannot be evaluated without understanding the
instrument-level cash flows.

### 2.1 Phase 1 — the cash-secured put

The account sells a put at a strike below market, receiving premium immediately. Full assignment
value — strike × 100 — is held in cash against the obligation. Three outcomes:

| Outcome | Mechanics | Action |
|---|---|---|
| Premium decays to 50% of credit | Underlying flat or rising; time decay reduces the option's value. A resting GTC limit closes the position automatically. | Capital freed; redeploy per ST-MGT-07 |
| Underlying falls to the strike (ATM) | Position is challenged. Extrinsic value — and therefore roll credit — is at maximum precisely at the money, and decays as the option moves deeper ITM. | Roll if conviction says the decline continues (§2.3) |
| Roll credit no longer obtainable | The put is deep enough ITM that closing and reopening cannot net a credit. The threshold is approximately $0.01 (ST-ROL-09). | Accept assignment; proceed to Phase 2 (§2.4) |

**Why 30–45 days and ~0.30 delta.** The 30–45 day window sits where theta decay accelerates while
gamma exposure remains manageable. Shorter tenors offer poor premium relative to the risk of adverse
moves and, critically, leave insufficient time to execute a roll before expiration — the source's
explicit argument against weeklies is that a single unrollable assignment erases the additional
premium from higher-frequency trading (ST-ENT-08). Longer tenors decay too slowly to be
capital-efficient and lock collateral unproductively.

The ~0.30 delta strike corresponds to roughly a 70% probability of expiring worthless. Lower delta
raises win rate but thins premium below the level at which the program generates meaningful return;
higher delta increases assignment frequency, which the strategy is specifically designed to minimize.

### 2.2 The 50% profit rule

Positions are closed at half of maximum profit rather than held to expiration. The remaining premium
decays most slowly while carrying the greatest proportional risk — the final increment of profit
requires holding through the period of highest gamma exposure. Closing early and redeploying
compresses the effective cycle and, materially, removes the position from the window in which early
assignment risk concentrates (§2.5).

The order is entered immediately on fill, as a GTC limit. **This is not a monitoring discipline; it
is an automation.** The position closes itself without the operator present.

### 2.3 The roll — the program's primary risk control

A roll closes the challenged put and simultaneously opens a new one, further out in time at the same
strike, for a net credit. Each successful roll collects additional premium, lowers eventual net stock
cost, extends time for recovery, and occasionally improves the strike.

**The trigger is two-conditional (ST-ROL-01).** A roll is indicated only when the underlying has
reached the strike **and** the operator is convinced it will remain at or below that level. An
underlying at the strike during a broad market decline, where analysis says the business is
unaffected, is a hold — not a roll. This conviction clause is the single most important and least
automatable rule in the methodology. Mechanical rolling on price alone converts market noise into
transaction costs and premature capital lockup.

**Roll parameters and their reasoning**

— **Out one to two weeks, same strike.** Short extensions preserve the ability to exit quickly when
the underlying recovers. Long rolls collect more credit but lock capital and cannot be reversed.
— **Total tenor bounded at ~60 DTE.** Beyond 60 days theta decay flattens and the position becomes
unproductive relative to the collateral it consumes (ST-ROL-06).
— **The productivity floor is the credit itself.** Rolling continues while a meaningful credit
exists; approximately $0.01 is the stated stopping point (ST-ROL-09). Late-chain rolls execute
nearer expiry, around 7–10 DTE.
— **Post-roll objective changes.** A rolled position is no longer targeting 50% profit. The
objective becomes exit at scratch or any small net profit as soon as available, freeing capital for
untroubled positions (ST-ROL-05).
— **The challenged name is frozen.** No new positions open on an underlying under management
(ST-ROL-08).
— **Earnings inside a roll chain:** extend approximately 30 days past the report date, collecting
elevated premium and allowing the underlying to establish a post-event trend (ST-ROL-07).

### 2.4 Phase 2 — assignment and covered calls

When a roll can no longer produce a net credit, the position expires and shares are assigned. This
is a designed exit, not a failure state: after a chain of credit-positive rolls, net stock cost —
strike paid less all premium collected — is frequently at or below prevailing market price.

Net stock cost, not the strike and not market price, governs every subsequent decision:

— **Net cost below market:** the position is profitable. Exit quickly — sell the shares, or sell an
at- or in-the-money call for one additional premium on the way out. Return to Phase 1 (ST-CC-10).
— **Net cost above market:** sell calls above net cost only. A call struck below net cost locks in a
loss on exercise and is prohibited while the thesis holds (ST-CC-01, ST-CC-08).
— **No workable strike above net cost:** hold. Collect dividends. Wait. Optionally sell an
additional put below market — the covered strangle repair — but only if fresh analysis confirms
stability, and never on a deteriorating name (ST-CC-09).

### 2.5 Assignment risk, correctly characterised

Early assignment on a short put is rare and concentrates in a specific, identifiable condition: when
extrinsic value approaches zero near expiration, at which point exercising becomes more efficient for
the holder than selling. The 50% profit rule and active rolling together mean positions in this
program almost never occupy that state (ST-ASN-06).

The frequently cited risk that a market crash assigns an entire book simultaneously is largely a
misconception. Put holders in a falling market overwhelmingly prefer to sell to close rather than
exercise, because closing captures remaining extrinsic value. Sector dispersion further reduces
correlation of assignment events. **The genuine version of this risk applies to single-underlying
books** — which is one reason the program requires a minimum of three names even at pilot scale
(ST-EVT-04, AL-SIZ-01).

> **Open specification gap.** The above is put-specific. **Ex-dividend early assignment risk on
> covered calls is not yet specified** (Brief G-6), and it is a recurring condition rather than an
> edge case because ST-SEL-06 biases the universe toward dividend payers. This is the highest-
> priority open gap in the program.

---

## 3. Risk Framework

### 3.1 Primary risk

The dominant risk is a significant, sustained decline in a held underlying. The methodology's
central claim about this risk is precise: **it is no greater than owning the stock outright**, and is
cushioned by all premium collected prior to assignment (ST-FRM-04). The claim holds only if the
underlying was genuinely one the operator was willing to own — which is why security selection is
treated as a risk control rather than a return driver.

### 3.2 Risk register

| Risk | Manifestation | Control | Residual |
|---|---|---|---|
| Underlying decline | Assignment at above-market prices; extended holding period | Quality selection (ST-SEL-01…14); roll chain lowering net cost; covered call recovery | Real. Recovery measured in months. Accepted. |
| Thesis break | Business deteriorates fundamentally; no recovery expected | Enumerated kill switch (AL-RSK-01), now name-specific via written thesis (AL-SEL-04) | False positives possible; calibration open (Brief C-5) |
| Concentration | 3–5 names at pilot scale; single failure is material | Minimum 3 names, ≥2 sectors, 1 contract per name (AL-SIZ-01) | **Highest residual risk in the program. Structural until ~$60K.** |
| **Sector correlation** *(new v1.1)* | Multiple names in one sector fall together; per-name limits do not see it | ≤50% collateral per sector (AL-SIZ-02); industry warning (AL-SIZ-03) | Taxonomy authority unresolved (Brief G-11) |
| **Event clustering** *(new v1.1)* | Two or more positions reporting the same week | Flag at screen and at entry (AL-SIZ-04) | Display only, not a block. Low. |
| Broad market crash | Multiple positions challenged simultaneously; reserve consumed | 50% reserve; position-by-position triage; explicit cap on assignments taken (ST-EVT-01/02/03) | Managed, not eliminated. Drawdown expected. |
| Capped upside | Underlying rallies past covered call strike | None — this is the premium being sold | Designed property. Opportunity cost, not loss. |
| Operator error | Panic close, premature exit, rule override under stress | Written Constitution; amendment freeze during unrealized losses (AL-OPS-03); every trade event logged as it happens, with the rule ID that triggered it (Const. §9.1, §9.2) | The source identifies impatience as the largest single loss source (ST-PHI-01). Residual is higher than v1.1 claimed: the prediction log that was to measure override quality is retired, and logging records a decision without scoring it. |
| Liquidity | Wide spreads degrade fills, particularly on rolls | Open-interest screening (ST-SEL-13); limit orders only; never market orders (ST-ORD-03) | Low at selected names; monitored. |
| Tax drag | Premium is short-term capital gain, taxed as ordinary income, unwithheld | 35% of realized gains segregated within 7 days; quarterly estimates (AL-OPS-01) | Material — see §5.3. |

### 3.3 Capital reserve policy

No more than 50% of net liquidity is deployed as option collateral on average, with a hard ceiling of
65% and no more than two consecutive weeks above the average (ST-CSH-01, AL-CSH-01). The reserve is
not idle capital awaiting deployment. It performs three functions simultaneously:

— **It enables rolling.** A challenged position cannot be rolled without available buying power. The
source's own account: he did not hold the reserve at small account size, and the consequence was
being forced to close challenged positions at a loss rather than roll them.
— **It absorbs assignment.** Shares consume collateral. Without reserve, an assignment cascade forces
liquidation of other positions.
— **It buys the recovery.** Corrections reset prices on quality underlyings. The reserve is what
converts a drawdown into an opportunity — and is the sole mechanism by which the program's upside
scenario is reached (Const. §12.4).

**Reserve policy is the load-bearing risk control of the entire program.** Every other rule degrades
gracefully under stress. This one does not: an account without reserve in a crash has no management
options at all.

Performance is measured on full net liquidity including the reserve (ST-CSH-04), precisely so that
the reserve is never mistaken for drag.

**New in v1.1:** the reserve is now *displayed at the point of decision* rather than reviewed after
the fact. Assignment capacity — total obligation if every open position were assigned, against
available reserve — is computed and shown before every entry (AL-CSH-02, Const. §3.4). A control
that is not visible at the moment it would be breached is not operating.

### 3.4 Kill switch

A position is closed for a loss when the investment thesis breaks — not when the price falls. Price
decline is what the roll chain and covered call phase exist to manage. Triggers are enumerated:
material deterioration in cash flow or profitability, dividend suspension or cut, analyst consensus
flip to bearish, accounting irregularity or going-concern disclosure, or any development reversing
the willingness-to-own test. **In v1.1 the trigger set becomes name-specific:** each name's written
thesis (AL-SEL-04) states the conditions that would break *that* business, which is a materially
sharper instrument than a generic list.

---

## 4. Capital and Position Sizing

### 4.1 Sizing logic

Contract count is determined by assignment capacity, never by premium appetite. The operative
question at every entry is not *how much premium can this collect* but *how many hundred-share lots
can this account absorb while remaining inside the reserve policy* (ST-ENT-04).

### 4.2 Pilot-scale allocation

Illustrative at $12,000 net liquidity, mid-range of the request, using a $25 underlying:

| Line | Calculation | Value |
|---|---|---|
| Net liquidity | Account total | $12,000 |
| Deployment ceiling | 50% average (ST-CSH-01) | $6,000 |
| Collateral per contract | $25 strike × 100 shares | $2,500 |
| Concurrent positions | $6,000 ÷ $2,500, rounded down | **2 open** |
| Names with written theses | Minimum 3, ≥2 sectors (AL-SIZ-01, AL-SEL-04) | **3–5** |
| Names monitored | Watchlist (ST-SEL-07) | **~10** |
| Per-name exposure at assignment | $2,500 ÷ $12,000 | 20.8% |
| Policy target per name | 5% of account (ST-SIZ-01) | 5.0% |
| Premium per cycle, ~1% of collateral | Quality-name realistic (ST-SEL-11) | ~$25/contract |

> **v1.1 terminology correction.** v1.0 collapsed three distinct quantities into "names."
> They are now separated: **monitored** (~10), **tradeable with a written thesis** (3–5), and
> **concurrently open** (2 at this account size). The apparent contradiction between AL-SEL-01 and
> AL-SIZ-01 in the v1.0 governance set was an artifact of this collapse and is resolved in Source
> Brief v2.0 (Conflict C-3, closed).

### 4.3 Zones — sizing bands derived, not fixed *(new in v1.1)*

The methodology states a $10–$50 price band, and also states that the author's own band moved up as
his account grew. The band is therefore a capital-efficiency constraint that scales, not a quality
constraint that is fixed. v1.1 replaces the literal band with its generating formula:

> `max_strike = (net_liquidity × per_name_cap) ÷ 100`

| Account | Zone ceiling @ 5% policy | Zone ceiling @ pilot reality (~20%) |
|---|---|---|
| $12,000 | $6 — below the $10 floor; policy unreachable | **$24** |
| $30,000 | $15 | $60 |
| $60,000 | **$30** — 5% policy becomes operative | $120 |
| $120,000 | $60 | — |

Two properties matter more than the numbers:

**The $10 floor does not scale** (ST-SEL-04). It is a quality threshold, unlike the ceiling.

**Out-of-zone names are displayed, not hidden** (AL-SEL-03). A candidate above the zone ceiling
appears in output with its concentration figure and the account size at which it unlocks. Hiding
higher zones removes the growth ladder; unlocking them removes the sizing discipline. Displaying and
locking does both. Entry requires an explicit override, logged at the time of the trade with the
rule ID it departs from (Const. §9.1), so the exception is recorded rather than merely permitted.

**Share price and market cap are separate filters** (AL-SEL-06). Price governs sizing; market cap
governs quality, liquidity, and gap risk. Conflating them is how a screen rejects a sound $15
large-cap and accepts an unsound $45 micro-cap.

### 4.4 Sector construction *(new in v1.1)*

Per-name limits do not see sector correlation. Three regional banks at 5% each is a 15% position in
a single shock. v1.1 adds:

— **Hard: ≤50% of deployed collateral in any one sector** (AL-SIZ-02). At pilot scale with two
positions this binds immediately, which is what enforces the two-sector minimum in practice.
— **Soft: industry concentration warns rather than blocks** (AL-SIZ-03). Sub-industry taxonomies are
noisy; a hard rule on noisy data produces false blocks.
— **Flag: earnings clustering** (AL-SIZ-04). Two positions reporting in the same week is a
correlation the sector view does not catch.

**Open item:** the sector taxonomy itself is unresolved (Brief G-11). GICS, provider labels, and
common usage disagree materially for conglomerates and for anything adjacent to technology. AL-SIZ-02
cannot be enforced until one is designated authoritative.

### 4.5 The concentration problem, stated plainly

At $12,000, a single contract represents roughly four times the methodology's per-name policy limit.
This is not a rule the program is choosing to relax; it is arithmetically unavoidable at pilot scale.
The mitigations are partial and are stated as such:

— Maximum one contract per name — no doubling into a single underlying.
— Minimum three thesis-backed names across at least two sectors, rotating rather than concentrating.
— Zone ceiling biased low, maximising the number of distinct names the deployed capital can span.
— Selection standard held higher at pilot scale than at target scale, precisely because a single
error is less diluted.

**Assessment.** Concentration is the program's principal structural weakness and the most likely
source of a materially disappointing outcome. It resolves arithmetically as the account grows toward
$60,000, at which point the 5% policy becomes achievable. It does not resolve through cleverness, and
no rule in the Constitution claims otherwise (Const. §11.2).

### 4.6 Growth path

All gains net of the tax reserve compound until the account reaches $30,000; no withdrawals occur
before that threshold. Between $30,000 and $60,000 the position count rises and per-name exposure
falls toward policy. Above $60,000 the full 5% discipline becomes operative and the program reaches
its designed risk profile. **The zone formula in §4.3 makes this a continuous function of account
size rather than a series of future amendments** — and the pilot-scale mitigations are retired by
explicit amendment under Const. Article X rather than allowed to lapse. The annual prompt that used
to schedule that review went out with Article XIII; nothing now raises the question on a timer.

---

## 5. Return Expectations

Full treatment is Constitution Article XII, which binds. This section summarises.

### 5.1 Regime-conditional scenarios

The program has no annual return target. A target is an input to decision-making, and any rule
adopted in order to reach a number is a violation of the selection, entry, or sizing discipline.
Return is an output of correct execution under a given market regime (Const. §12.1).

| Scenario | Regime | Expected annual | Mechanism | Precedent |
|---|---|---|---|---|
| Bear | Sustained decline | 8–14% | Smaller positions, wider laddering, stricter selection; 30–45 DTE absorbs shorter shocks; dividends contribute | Source's 2022: +12% against S&P −18% |
| **Base** | Normal to mildly bullish | **15–25%** | Standard cycle: sell, close at 50%, redeploy; occasional roll; rare assignment | Source's stated guide range |
| Bull | Post-correction recovery | 30–40% | Reserve deployed into reset prices; elevated IV on quality names; rapid cycle turnover | Source's 2009–10 recovery years |

**The planning case is Base.** All capital planning, income projection, and validation criteria in
this document assume 15–25% and no higher.

**The critical structural point.** The Bull scenario is unlocked by the capital reserve, not by
increased risk-taking. Every mechanism producing the upside column is a defensive mechanism operating
in a favourable regime. **There is no posture available within this strategy that raises expected
return — there are only postures that raise variance.** Any proposal to reach the Bull column
deliberately is a proposal to abandon the strategy (Const. §12.4).

### 5.2 Interpreting results

A Bear-column year is not underperformance. A +10% return in a market that fell 18% is the program
working as designed. Judging a bear year against base expectations is the specific error that
produces rule-tampering, and the Constitution therefore requires the regime to be identified and
recorded **before** performance is evaluated (Const. §12.3).

**Variance disclosure:** at three to five names, dispersion around any scenario is materially wider
than at the ten-to-twenty-name book the methodology assumes. Fewer positions produce higher variance,
not higher return. Early results — favourable or otherwise — carry low information content about the
strategy (Const. §12.5).

### 5.3 After-tax reality

Premium income on individual equity options is short-term capital gain, taxed as ordinary income,
with no withholding. The 60/40 treatment applicable to broad-based index options does not apply. At
an assumed 35% effective marginal rate, a 20% gross return is approximately 13% net.

| Comparison at $12,000, one year | Gross | Net of tax | Effort / risk |
|---|---|---|---|
| High-yield savings (~4.5%) | $540 | ~$351 | None / none |
| Short-duration Treasuries (~4.5%) | $540 | ~$351 | None / none |
| This program, Bear scenario | $960–1,680 | ~$624–1,092 | Moderate / real |
| This program, Base scenario | $1,800–3,000 | ~$1,170–1,950 | Moderate / real |

The incremental after-tax return over a risk-free alternative in the base case is approximately
**$800–$1,600 annually.** That figure — not the headline percentage — is the honest measure of what
the program's risk and operator time are purchasing at pilot scale.

---

## 6. Validation Methodology

Criteria in this section are written **before any results exist.** This is deliberate. Thresholds set
after observing outcomes are not validation; they are curve-fitting with extra steps. The criteria
below are binding on the decision to deploy capital.

### 6.1 Why backtesting cannot validate this strategy

The methodology's central management decision — the roll — is conditioned on operator conviction
about an underlying's forward path (ST-ROL-01). That input does not exist as a historical data field.
Neither does crash triage: the decision about which positions to close, roll, or accept assignment on
during a dislocation is judgment applied to incomplete information in real time.

The source states this directly: the wheel cannot be fully backtested, and backtest results are not
proof (ST-PER-04). **A backtest of this strategy necessarily tests a mechanical shadow of it — the
rules with the judgment removed.** That shadow is worth measuring, but it is not the strategy, and a
proposal presenting backtested returns as validation would be misrepresenting what had been tested.

### 6.2 The three-track validation program

**Track A — Mechanical floor simulation**
*Question:* what does the rule-only shadow produce with zero judgment applied? Rolls executed
mechanically on price alone, no conviction filter, no crash triage.
*Method:* historical options chain data across 2019–2025, deliberately spanning the March 2020
dislocation and the 2022 bear market. Quality-screened universe consistent with ST-SEL criteria.
*Interpretation:* this establishes a **floor, not an expectation.** Live execution should exceed it
if the judgment layer adds value; materially underperforming it in live trading is a strong signal
that operator discretion is destroying rather than creating value.

**Track B — Risk envelope characterisation**
*Question:* what does the loss distribution look like, independent of central tendency? Assignment
frequency by regime, maximum peak-to-trough drawdown, duration from assignment to position closure,
reserve utilisation at peak stress.
*Why this matters more than return estimation:* the program's failure mode is not insufficient return
— it is an operator abandoning the strategy mid-recovery because the drawdown exceeded what they
prepared for. Characterising the envelope in advance is what makes it survivable.

**Track C — Paper trading with logged reasoning**
**This is the actual validation gate.** Minimum 60 days, live market prices, full position logging,
and a written rationale for every judgment call: tenor selection within the 30–45 band, roll
conviction, triage decisions. Each names the rule ID it acted under (Const. §9.1).
*What it validates:* whether the operator executes the rule set consistently under live conditions.
The reasoning log is the validation artifact. It is no longer also an evaluation set — the tooling
that would have scored predictions against outcomes is retired, and reading the log back is the
operator's work rather than the tool's.

### 6.3 Pass / fail criteria for capital deployment

| # | Criterion | Threshold | Consequence if failed |
|---|---|---|---|
| 1 | Track A mechanical floor positive across full period including 2020 and 2022 | Positive annualised return, both stress windows | Do not deploy. Strategy assumptions are wrong. |
| 2 | Track A maximum drawdown | ≤ 25% peak-to-trough | Deploy at reduced size; re-examine sizing policy. |
| 3 | Track C rule compliance | ≥ 90% of decisions traceable to a rule ID | Extend paper trading. Operator is improvising. |
| 4 | Track C trade-log completeness | 100% of trade events logged **at the time they occur**, each carrying the rule ID that triggered the action (Const. §9.1, §9.2) | Extend paper trading. **Non-negotiable** — §9.2 holds that an unlogged trade did not happen. |
| 5 | Track C reserve discipline | Deployment never exceeds 65%; average ≤ 50% | Extend paper trading. This is the load-bearing control. |
| 6 | Track C assignment frequency | Consistent with 2–3/yr book rate, regime-adjusted | Investigate selection or roll execution before deploying. |
| 7 | Track B envelope documented and accepted | Operator has stated in writing the drawdown they will hold through | Do not deploy. Unprepared operators exit at the bottom. |
| **8** *(new v1.1)* | **Written thesis on every tradeable name** | 100% of names have `notes/<TICKER>.md` with business case and kill-switch conditions | **Do not deploy.** §2.10 cannot be honestly answered without it. |

**Deployment sequence on passing:** micro-live at $5,000 for 30 days, then scale to full pilot
allocation. Criteria 3 through 6 remain in force as ongoing monitoring thresholds, not merely gates.

---

## 7. Technical Architecture

*Substantially revised in v1.1. Full build specification is Deliverable 6 and is deliberately not
drafted until this section is settled.*

### 7.1 The constraint that determines the design

The strategy contains a deterministic layer and a judgment layer, and **conflating them is the
primary technical risk.** Automating the judgment layer would not produce a faster version of the
strategy; it would produce a different and worse strategy — one that rolls mechanically on price,
which the methodology explicitly warns against (ST-ROL-01, ST-PHI-02).

### 7.2 The second constraint, added in v1.1: convergence

An artifact that **converges** has a verifiable finish line — it reaches a state that can be checked
and then stops changing. An artifact that does not converge reopens on taste every time it is
examined.

Rule-scored, file-based output converges: a screen either applied the rules correctly or it did not,
and the answer is checkable against a frozen input. An interactive interface does not: there is
always a better layout. v1.0 specified a reporting surface; **v1.1 removes it.** The deliverable is
files. If a presentation layer is later wanted, it is a *renderer* — a pure function from frozen data
to a document — which converges, rather than an application, which does not.

### 7.3 Four-layer design

v1.0 specified three layers and omitted acquisition, which v1.1 corrects. Acquisition is a distinct
layer because it is the only nondeterministic boundary in the system.

| Layer | Implementation | Scope | Authority |
|---|---|---|---|
| **0 · Acquisition** | Provider-isolated fetch; raw response written timestamped to durable snapshot storage | Fetch and write. **No interpretation whatsoever.** | Records. Never scores. |
| **1 · Rules engine** | Deterministic code; no model inference | Selection screening against the ST-SEL set, zone derivation, sector and clustering checks, contract sizing against reserve, net stock cost arithmetic, GTC order construction, DTE and delta filters, roll productivity floor at ≈$0.01, compliance monitoring | Executes. Fully auditable. |
| **2 · Decision support** | Model inference, Constitution-grounded | Presents structured options for ambiguous calls — roll conviction, crash triage, thesis-break assessment — each mapped to a governing rule ID with reasoning stated | **Proposes only. Never executes.** |
| **3 · Operator** | Human | Approves, rejects, or overrides. Overrides logged with the rule ID they depart from. | **Sole execution authority.** |

### 7.4 Snapshot-then-score

**Layer 0 never hands live data to Layer 1.** Market data is fetched, written timestamped to durable
storage, and scored *from the snapshot* (AL-OPS-06).

This is architectural rather than incidental, and it buys three things that are otherwise
unavailable:

1. **Reproducibility.** A decision made last Tuesday can be re-derived exactly, because the input
   still exists.
2. **Regression testing.** A frozen snapshot with a known-correct output is a golden file. Without
   snapshots there is nothing stable to test a scorer against, and scorer drift becomes undetectable.
3. **Offline development.** Layer 1 can be built and tested with no network at all.

The general form: **isolate nondeterminism at the edge and convert it into a fixed input.** Market
data changes every second; the snapshot converts that boundary into something everything downstream
can be tested against.

### 7.5 Design rules for Layer 2

— **Every recommendation must cite a rule ID.** A recommendation that cannot be mapped to a
Constitution Article or Source Brief rule is a drift signal and is surfaced as such.
— **The layer applies the Constitution; it does not reason freshly about strategy.** Consistency is
the product. Novel strategic reasoning at the position level is the failure mode, not the feature.
— **Ambiguity is surfaced, not resolved.** Where the rule set genuinely does not determine an answer,
the correct output is a stated set of options with tradeoffs — not a recommendation with false
confidence (Const. §7.6).
### 7.6 The learning loop, correctly scoped

At roughly 30 closed positions a year, **statistical outcome-tuning is curve-fitting.** The learning
mechanism is therefore qualitative rule amendment, not parameter optimization (ST-PER-04).

**Article X is the learning loop.** v1.1 named it and then proposed to feed it: a calibration report
of predicted against actual, a divergence tally, and rule-gap detection, all scored on the Article
XIII quarterly cadence. That machinery is retired and Article XIII with it. What remains is the
trade ledger, the amendment discipline in Article X, and an operator reading one against the other.
This is a smaller claim than v1.1 made and a more honest one — the tool never did the judging, and
it no longer pretends to schedule it either.

### 7.7 Evaluation is two tracks, not one

Conflating them is a category error, and the distinction outlives the tooling that once sat on both
sides of it:

— **Tool evaluation** — does the deterministic layer still produce the correct output for a known
input? Golden files against frozen snapshots. Catches scorer drift. Automatable, and automated.
— **Judgment evaluation** — was the decision good? Not automatable, not statistically powered at
this n, and **no longer inside the tool.** v1.1 proposed replaying logged decisions against
outcomes; at 30 closed positions a year that never earned the machinery it needed. Judgment
evaluation is the operator's work, done against the trade ledger, and it yields amendment
candidates rather than p-values.

### 7.8 Data and infrastructure

**Broker:** Charles Schwab, Level 3 options approval, dedicated account. Execution remains manual
through the pilot; broker API integration is deferred until Track C compliance thresholds are met in
live trading, not merely in paper.

**Screening data:** provider-isolated behind Layer 0, snapshotted before scoring. **No provider
import appears anywhere outside the acquisition layer** — this is what makes the provider
replaceable, and it is the only reason the v1.0 data-source change was a small edit rather than a
rewrite.

**Validation data:** free options-chain history is inadequate for the greeks and implied-volatility
series required by Tracks A and B. **A paid historical source remains a prerequisite for validation
and is the principal non-capital cost of the program.** This is unchanged from v1.0 and is
independent of the screening data path — the two should not be conflated because one is now solved.

**Open item:** AL-ENT-01 gates entry on IV Rank > 30, but IV Rank has no standard definition and may
not be directly available under the current data path (Brief G-14). It may require computing from a
stored IV history the snapshot layer does not yet keep. **Until resolved, AL-ENT-01 is not
enforceable** and Conflict C-2 cannot be tested.

---

## 8. Underlying Universe

**Section status: criteria defined, names pending.** Ticker selection is deliberately deferred to a
separate research phase. The methodology is emphatic that the selection list must be the operator's
own work, derived from businesses the operator actually understands and would hold — and the source
consistently declines to publish his own list for exactly this reason (ST-SEL-14, Brief G-13). A
proposal that named underlyings before that research was done would be presenting the least
defensible part of the program as the most settled.

### 8.1 Screening criteria

| # | Filter | Threshold | Purpose |
|---|---|---|---|
| 1 | Profitability and cash flow | Sustained positive; no going-concern flags | Assignment may become a multi-month hold; solvency makes waiting survivable |
| 2 | Analyst consensus | Bullish or very bullish | Cheap filter against selecting into deterioration |
| 3 | **Share price — zone** | Within derived zone; hard floor at $10 | Capital efficiency and diversification breadth *(revised v1.1 — AL-SEL-02)* |
| 4 | **Market cap** | Mid-cap or above at pilot scale | Quality, liquidity, gap risk — a separate question from price *(new v1.1 — AL-SEL-06)* |
| 5 | Price stability | No violent gap history; no single-personality or narrative risk | Gap risk defeats the roll mechanism — the program's primary control |
| 6 | Implied volatility | Raw IV below ~50%; high IV disqualifies | Fat premium prices real risk of the exact failure mode the strategy cannot absorb |
| 7 | Premium sanity check | ~1% of collateral per cycle at 0.30 delta | Quantitative test of filter 6 *(new v1.1 — ST-SEL-11)* |
| 8 | Dividend | Preferred, not required | Reduces net stock cost during holding; proxies for stability |
| 9 | Options liquidity | Sufficient open interest for tight fills at target strikes | Roll execution quality depends on it |
| 10 | Chart position | Not at or near multi-year highs | Entry point materially affects assignment probability |
| 11 | **Sector** | Contributes to ≥2 sectors; ≤50% collateral per sector | Correlation the per-name limit does not see *(new v1.1 — AL-SIZ-02)* |
| 12 | Willingness to own | Operator holds 100 shares twelve months without distress | **The precondition for the entire risk argument** |
| 13 | **Written thesis** | `notes/<TICKER>.md` exists with business case and kill-switch conditions | Filter 12 cannot be honestly answered without it *(new v1.1 — AL-SEL-04)* |

### 8.2 The counterintuitive filter

Criterion 6 inverts the instinct that draws most participants to this strategy. Elevated implied
volatility produces larger premiums, and larger premiums appear to be the objective. **They are
not.** The premium is compensation for risk, and on a low-quality underlying the risk being
compensated is precisely the one the program cannot manage: a decline that does not recover. A
stable business paying roughly 1% per cycle is the intended trade. An unstable one paying five times
that is the trade that produces the losses the strategy is otherwise designed to avoid.

### 8.3 Research protocol

— **Stage 1 — Screen.** Apply criteria 1 through 11 mechanically across the eligible universe.
Output: ranked candidate list with supporting data, zone status, and sector attribution.
— **Stage 2 — Operator filter.** Criterion 12 applied by the operator to businesses actually
understood. Names that pass the screen but fail comprehension are excluded regardless of metrics.
— **Stage 3 — Portfolio construction.** Final 3–5 names selected across a minimum of two sectors,
with concentration, sector exposure, and earnings clustering explicitly assessed.
— **Stage 4 — Documented rationale.** One `notes/<TICKER>.md` per name stating the business case and
the specific conditions that would trigger the kill switch for that name.

> **v1.1 change: Stage 4 is now a gate, not a step** (AL-SEL-04, Const. §2.11, criterion 8 in §6.3).
> A name without a written thesis is not tradeable, and the screening tool enforces this by checking
> for the file's existence rather than by trusting that the research was done.

**This section is completed and the proposal reissued as v2.0 once Stage 4 is finished.** Until then,
the program is not deployable regardless of validation results.

---

## 9. Principal Objections and Responses

### 9.1 "Concentration at this size makes the risk framework decorative."

**Substantially conceded.** At $12,000, per-name exposure at assignment runs near 21% against a 5%
policy target. The 5% rule is the methodology's primary defense against selection error, and the
program cannot honour it at pilot scale. The mitigations in §4.5 reduce but do not resolve this. The
honest position: the pilot accepts elevated single-name risk as the cost of learning the strategy
with real capital at a size where a total loss on one name is survivable in absolute terms, and the
condition resolves arithmetically as the account grows. Const. §11.2 states this in the binding
document rather than only here.

### 9.2 "The volatility risk premium has compressed and may not persist."

**Partially conceded.** The premium varies across regimes and compresses in sustained low-volatility
periods. Two responses. Return expectations here are already regime-conditional, with the Bear column
assuming a substantially degraded environment. And the failure mode of a compressed premium is lower
return, not loss: thin premium produces fewer attractive entries and more time in cash, which reserve
policy already accommodates. **This risk degrades the program; it does not break it.**

### 9.3 "Judgment-dependence makes results unattributable."

**Conceded, and partly addressed.** If the roll decision depends on operator conviction, outcomes
cannot be cleanly attributed to the rule set. Two things narrow the gap: every trade event is logged
as it happens with the rule ID that triggered it (Const. §9.1, §9.2), and the mechanical floor in
Track A stands as a comparison baseline. v1.1 claimed more — a required prediction on every judgment
call, making the judgment layer's contribution measurable over time. That mechanism is retired and
the claim retires with it. The program cannot eliminate judgment dependence and no longer claims to
measure it; **it can make it auditable.**

### 9.4 "The returns don't justify the operator time."

**Not conceded, but the framing is accepted.** At pilot scale the incremental after-tax return over a
risk-free alternative is roughly $800–$1,600 annually — modest against the hours required,
particularly in year one. The justification is not the pilot's cash flow. It is that **the pilot is
how the operator acquires the execution discipline the strategy requires, at a capital size where
errors are affordable.** The strategy becomes economically meaningful above $40,000, and survivable
at that size only if the discipline was built first.

### 9.5 "A bull market makes this strictly worse than holding the index."

**Fully conceded, and by design.** The covered call leg caps upside. In a strong bull market this
program underperforms a passive long position and no argument is offered to the contrary. The
program's claim is to income generation with defined risk, not to growth. An operator whose objective
is maximum long-horizon appreciation should hold an index fund; the source says as much explicitly
(ST-PER-05).

### 9.6 "The tooling is over-engineered for thirty trades a year." *(new in v1.1)*

**Partially conceded.** At this volume the deterministic layer could be a spreadsheet, and the
learning loop will never be statistically powered. Two responses. First, the tooling's purpose is
not throughput but **consistency** — the failure mode is operator drift under stress, and a system
that produces the same screen the same way every week is the countermeasure. Second, the decision
record is not built to enable statistical learning; it is built so that the ≥90% compliance threshold
in §6.3 is measurable at all. Without it, criterion 3 is unfalsifiable and the validation program is
decorative.

**What is conceded:** any component that does not serve consistency or measurability is over-
engineering, and v1.1 removed one such component (§7.2).

### 9.7 What would falsify the thesis

— Track A mechanical floor negative across 2019–2025 → the rule set is wrong, not the execution.
— Live assignment frequency materially exceeding the 2–3 per year book rate in a normal regime →
selection criteria or roll discipline are failing.
— Rule compliance below 90% after 60 days of paper trading → the operator, not the strategy, is the
binding constraint.
— Sustained Base-regime returns below 15% across a full year with high compliance → the strategy does
not deliver its claimed premium at this scale and should be abandoned in favour of a passive
alternative.

---

## 10. Implementation Roadmap

| Phase | Window | Activities | Exit criteria |
|---|---|---|---|
| **0 · Foundation** | Weeks 1–3 | Schwab Level 3 approval; dedicated account funded; three-bucket cash structure; **Constitution v2.0 adopted and signed**; Deliverable 6 build spec drafted *after* §7 is settled | Account live; rules signed; spec complete |
| **1 · Universe research** | Weeks 2–5 | Four-stage protocol (§8.3); `notes/<TICKER>.md` per name; proposal reissued as **v2.0** with §8 completed | 3–5 names with written business cases and kill-switch conditions |
| **2 · Track A + B** | Weeks 4–10 | Paid historical source procured; mechanical floor simulation across 2019–2025; risk envelope characterisation; drawdown tolerance stated in writing | Criteria 1, 2, 7 assessed |
| **3 · Track C** | Weeks 6–16 | 60+ days live-price paper trading; full position and reasoning logs; Layer 1 rules engine running in monitoring mode alongside | Criteria 3–6, 8 met |
| **4 · Micro-live** | Weeks 16–20 | $5,000 deployed; 1–2 concurrent positions; manual execution; Layer 2 decision support introduced in advisory mode | 30 days at ≥90% compliance with real capital |
| **5 · Full pilot** | Week 20+ | Scale to $9–15K; 3–5 names in rotation; monthly reconciliation; **quarterly amendment window under Constitution Article X** | Ongoing — compliance thresholds remain live |

Phases 1 and 2 run concurrently; Phase 3 requires a named universe from Phase 1. **The gating
discipline that matters: no capital deploys until Track C compliance thresholds are met, regardless
of how favourable Track A results appear.** A strong backtest on a strategy whose central decision
cannot be backtested is not evidence the operator can execute it.

---

## Appendix A — Rule Reference

Every parameter and control in this document traces to a rule identifier in **Source Brief v2.1**
(`ST-` for source methodology, `AL-` for AdVenture Labs additions) or to an Article of **Strategy
Constitution v2.1**. Identifiers are cited inline throughout. Deliverable 6 maps each identifier to
its implementation in the rules engine.

**Load-bearing rules for this proposal:**

| Rule | Governs |
|---|---|
| ST-CSH-01 | 50% reserve — the load-bearing control |
| ST-ROL-01 | Two-conditional roll trigger, including the unautomatable conviction clause |
| ST-SIZ-01 | 5% per-name cap — not honoured at pilot scale, §4.5 |
| ST-SEL-10 | High IV disqualifies |
| ST-PER-04 | Backtest limitation — why validation is paper trading |
| ST-SEL-09 | Willingness to own — precondition for the entire risk argument |
| Const. Article XII | Regime-conditional returns |
| Const. Article X | Amendment — in writing, with a stated hypothesis, on a fixed quarterly cadence |
| Const. Article IX §9.1–§9.2 | Trade logging as a precondition of the trade — what makes any of the above auditable |

## Appendix B — Open Gaps Affecting This Proposal

Carried from Source Brief v2.0, Part IV. Listed here because each one bounds a claim made above.

| Gap | Bounds | Priority |
|---|---|---|
| **G-6** | §2.5 — ex-dividend early assignment on covered calls is unspecified, and ST-SEL-06 makes it recurring | **High** |
| **G-11** | §4.4 — AL-SIZ-02 cannot be enforced without a designated sector taxonomy | **High** |
| **G-14** | §7.8 — AL-ENT-01 is not enforceable and Conflict C-2 cannot be tested | **High** |
| G-9 | §2.3 — mid-roll assignment and partial fills undefined | Medium |
| G-12 | §4.3 — zone boundary hysteresis unspecified; week-over-week diffs may report noise | Medium |
| G-13 | §8 — no reference universe exists against which to validate selection *quality*, only rule compliance | Accepted limitation |

---

## Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | Jul 2026 | Initial proposal. Cited governance documents that did not yet exist. |
| **1.2** | **2026-09-08** | Realigned to Constitution v2.1 and the retirement of Layer 2 decision-support. Every reference to Article XIII, §13.3, §13.4, §13.6, §9.3 and §9.5 resolved: retired features deleted (§7.5 override-evaluation bullet, §7.6 calibration/divergence/rule-gap components, Appendix A's AL-OPS-05 row), surviving concepts rewritten without the retired mechanism (§6.2 Track C, §6.3 criterion 4, §7.3 Layer 3, §9.3 objection, §10 Phase 3), and surviving governance recited against what exists — Article X for the amendment cadence, Article IX §9.1–§9.2 for trade logging (§3.2, §4.3, §4.6, §10 Phase 5). **Two claims are deliberately weaker than in v1.1:** §9.3 no longer says the judgment layer's contribution is measurable, only auditable; §7.6 no longer promises a scheduled learning loop. §7 architecture, §4 sizing, §5 returns and §8 universe are otherwise unchanged. |
| **1.1** | **2026-08-03** | All citations realigned to Source Brief v2.0 and Constitution v2.0 (corrected from v2.1). §7 rewritten: four-layer design with acquisition layer, snapshot-then-score, convergence constraint, reporting surface removed, learning loop and two-track evaluation added. §4.3 zones and §4.4 sector construction added. §4.2 terminology corrected (monitored / thesis-backed / concurrent). §8.1 expanded to 13 criteria; §8.3 Stage 4 promoted to a gate. §6.3 criterion 8 added. §9.6 objection added. Appendix B added. Reissue trigger for v2.0 restated. |

---

*AdVenture Labs internal planning document. Not financial advice, not an offer, and not a
solicitation. Options trading involves substantial risk of loss including loss of principal. The
methodology underlying Part I of the referenced Source Brief is the published public writing of
Reddit user ScottishTrader, restated for internal specification use; he retains all rights to his
words and has no association with this document. Tax treatment described is general and requires
confirmation from a qualified professional.*
