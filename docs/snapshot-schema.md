# Layer 0 Snapshot Contract

**Version 1.0 · 2026-08-06**
Requirements source: Source Brief v2.0 rule table (ST-SEL-01…14, AL-SEL-01…06, AL-SIZ-01…04)
Machine-readable form: `src/wheel/snapshot_schema.py` · Golden files: `tests/golden/`

---

## Purpose

A snapshot is the reproducible market state for one ticker on one date. It is the
**only** input the Layer 1 scorers read. `wheel_mcp.yahoo` produces it; the gates
and score filters consume it and nothing else.

**Format:** `YYYY-MM-DD_TICKER.json` — the exact name `snapshot_ref` points at in
the [decision record schema](decision-record-schema.md) field 11. That link is
what makes a logged decision replayable: given the decision and its snapshot, the
verdict can be recomputed without re-fetching anything.

Two rules hold the contract together:

1. **Data only, no verdicts.** A snapshot records what was observed, including
   what was absent (`null`). It never records "passes ST-SEL-01" — that is Layer 1's
   job, and keeping judgment out is what makes a snapshot replayable years later.
2. **Absence is explicit, and the contract is closed.** Every field a rule needs
   exists even when the free tier cannot fill it; a `null` with a stated reason is
   auditable, a missing key is a silent gap. Unknown keys are rejected, because an
   unexpected field means the producer and the scorers disagree about the contract.

---

## Rule traceability

### Served by the snapshot

| Rule | Requirement | Fields |
|---|---|---|
| ST-SEL-01 | Profitable, solid cash flow | `fundamentals.net_income_ttm`, `.operating_cash_flow_ttm` |
| ST-SEL-02 | Bullish analyst consensus | `analyst.recommendation_mean`, `.analyst_opinions` |
| ST-SEL-03 | Price band (derived per AL-SEL-02) | `price.current` |
| ST-SEL-04 | Hard $10 floor | `price.current` |
| ST-SEL-05 | Stable chart, no violent moves | `stability.max_single_day_move_1y`, `.realized_vol_1y` |
| ST-SEL-06 | Dividend preferred | `dividend.pays_dividend`, `.yield_percent` |
| ST-SEL-08 | ETFs are valid candidates | `identity.quote_type` |
| ST-SEL-10 | High IV disqualifies | `volatility.implied_volatility`, `.realized_vol_30d` |
| ST-SEL-12 | Not near a multi-year high | `chart_position.pct_below_two_year_high` |
| ST-ENT-05 | Earnings proximity flag | `earnings.next_earnings_date`, `.days_to_earnings` |
| AL-SEL-04 | Written thesis gate | `operator_gates.thesis_note_exists` |
| AL-SEL-06 | Market cap is a separate filter | `identity.market_cap` |
| AL-SIZ-03 | Industry concentration warning | `identity.industry` |
| AL-SIZ-04 | Earnings clustering flag | `earnings.next_earnings_date`, `.earnings_week` |

### Not answerable from a snapshot — and why

The brief's requirement was "every field the scorers need for ST-SEL-01…14 plus
AL-SEL and AL-SIZ." Eleven of those rules cannot be served by a per-ticker market-data
snapshot at any level of effort. They are declared in `UNSATISFIABLE_AT_LAYER_0`
with reasons, and a test asserts every required rule is either mapped or declared —
so the gap is visible rather than discovered later by a scorer reading a missing key.

| Rule | Why not | Where it belongs |
|---|---|---|
| ST-SEL-07 | Watchlist size and review cadence | Run level |
| ST-SEL-09 | Willingness to own 12 months is operator judgment | `operator_gates` attestation |
| ST-SEL-11 | Premium ≈1% of collateral needs an option chain | Component B |
| ST-SEL-13 | Liquidity needs bid/ask and open interest at strikes | Component B |
| ST-SEL-14 | "No ideal wheel stocks" — universe is operator-supplied | System constraint |
| AL-SEL-01 | Concurrent-position count | Portfolio state |
| AL-SEL-02 | Derived band needs account `net_liq` | Portfolio state |
| AL-SEL-03 | Zone lock needs account `net_liq` | Portfolio state |
| AL-SEL-05 | Zone exit applies to held positions | Portfolio state |
| AL-SIZ-01 | Name and sector minimums | Portfolio aggregate |
| AL-SIZ-02 | Sector collateral ceiling | Portfolio aggregate |

**The pattern:** three distinct kinds of non-market data are mixed into the
selection rules — operator attestations (ST-SEL-09, AL-SEL-04), option-chain data
(ST-SEL-11, ST-SEL-13), and account/portfolio state (all of AL-SEL-01/02/03/05,
AL-SIZ-01/02). Only the first is carried here, as attestations. The other two need
their own contracts; a per-ticker snapshot embedding account balance would stop
being reproducible the moment the balance changed.

---

## Structure

Ten sections. Full field list with types in `SNAPSHOT_SCHEMA`.

| Section | Carries | Notes |
|---|---|---|
| *(root)* | `schema_version`, `snapshot_date`, `ticker` | Ticker must be uppercase |
| `source` | `provider`, `fetched_at`, `partial` | `partial: true` when any field came from elsewhere |
| `identity` | name, `quote_type`, sector, industry, market cap | `quote_type` distinguishes ETF from equity |
| `price` | current, history window, trading days | |
| `fundamentals` | TTM net income, operating cash flow, revenue | Null for ETFs |
| `analyst` | recommendation mean/key, opinion count | Null for ETFs |
| `dividend` | pays, yield, last ex-date | |
| `stability` | 1y max single-day move, 1y realized vol | Precomputed at the edge |
| `volatility` | IV (null), 30d realized vol, `is_proxy`, `proxy_note` | See below |
| `chart_position` | two-year high, percent below it | |
| `options` | has options, expirations listed, `chain_available` + 3 null chain fields | See below |
| `earnings` | next date, days to, ISO week | Needed for **every** candidate |
| `operator_gates` | thesis note exists/path, willing-to-own | Never provider-derived |

### Three things worth knowing

**IV is a proxy and the snapshot says so.** ST-SEL-10 is the methodology's most
counterintuitive rule and wants true implied volatility. No free source has it, so
`implied_volatility` stays `null`, `realized_vol_30d` carries the proxy, and
`is_proxy`/`proxy_note` make the substitution self-describing. A scorer reading the
proxy as IV must say so in its output. Component B fills the null; nothing else changes.

**`earnings` moved into the snapshot.** The current pipeline fetches the calendar
separately and only for hard-gate survivors, which is sufficient for ST-ENT-05.
AL-SIZ-04 flags earnings clustering across open *and candidate* positions, so a
survivors-only fetch cannot answer it. Earnings data belongs on every snapshot.

**`null` is not `false`.** `operator_gates.willing_to_own_12mo: null` means
unanswered; `false` means the operator considered it and said no. ST-SEL-09 is the
precondition for the entire risk claim in ST-FRM-04 — conflating "unasked" with
"declined" would let a name pass on a question nobody put.

---

## Validation

`validate_snapshot(document)` returns a tuple of violations, empty when valid.
`assert_valid_snapshot(document)` raises `SnapshotSchemaError` listing all of them.

Pure stdlib — no `jsonschema` dependency, consistent with the approved stack — and
a pure function of (schema, document): no clock, filesystem, or network. It collects
every violation in one pass rather than raising on the first, so a malformed
snapshot is diagnosed once rather than iteratively.

**Golden files.** `2026-08-15_F.json` is a fully-populated equity and proves the
contract is satisfiable on free data: the only nulls are the four Component B
fields, asserted exactly. `2026-08-15_SPY-minimal.json` is an ETF with the whole
equity-only half null — the ST-SEL-08 case, and the one most likely to break if
someone tightens a field to non-nullable.

---

## Open items for step 3

1. **`wheel_mcp.yahoo` does not emit this yet.** It returns an in-memory
   `TickerSnapshot` whose shape predates this contract. Wiring the emitter is
   step 3; until then the golden files are hand-built and the contract is
   validated but not yet produced.
2. **Three fields have no producer:** `identity.quote_type` and the whole
   `earnings` section come from provider calls the fetch does not currently make;
   `operator_gates.thesis_note_exists` is a filesystem check against `notes/<TICKER>.md`.
3. **Portfolio and chain contracts are unwritten.** Eleven rules above are blocked
   on them. Neither is in scope for Component A.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-06 | Initial contract. Of the 24 required rules: 13 served, 11 declared unsatisfiable, 0 unaccounted. ST-ENT-05 additionally mapped. |
