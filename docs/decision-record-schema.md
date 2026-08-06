# Decision Record Schema

**Version 1.0 · 2026-08-04**
Implements: AL-OPS-05, Constitution §9.3, §9.4

---

## Purpose

Every judgment call is logged at the time of decision with a required **prediction** field.
Outcomes are attached deterministically on close. A rationale without a prediction cannot be
scored, only re-read. This is the mechanism that makes the judgment layer measurable.

**Format:** append-only JSONL at `WheelOps/decisions/decisions.jsonl` — one JSON object per line.
Append-only means: lines are added, never edited, never deleted. Outcome attachment is a NEW line
referencing the original decision ID, not a mutation of the original line.

**Why JSONL, not CSV:** decisions have variable-length fields (rationale, alternatives, prediction).
CSV would require quoting gymnastics. JSONL is one `json.dumps()` per line, trivially parseable,
diffable, and grep-friendly.

---

## Schema — 12 fields

### Written at decision time (all required)

| # | Field | Type | Description |
|---|---|---|---|
| 1 | `id` | string | Unique identifier. Format: `DEC-YYYYMMDD-NNN` (date + sequence). Monotonic, human-readable, sortable. |
| 2 | `timestamp` | ISO 8601 | When the decision was made. Not when the trade executed — when the operator committed to the action. |
| 3 | `ticker` | string | Underlying symbol. Always uppercase. |
| 4 | `decision_type` | enum | One of: `entry`, `roll`, `close_profit`, `close_loss`, `assignment_accept`, `assignment_sell`, `cc_open`, `cc_roll`, `cc_exit`, `kill_switch`, `override`, `thesis_update`, `skip` |
| 5 | `rule_id` | string | The governing rule that triggered or justified this action. `ST-ROL-01`, `AL-MGT-01`, etc. If no rule governs → `"NONE"` — this is a gap signal, not an error. |
| 6 | `action` | string | What was done, in structured shorthand. Examples: `"sold CSP 30DTE 0.28d $25 strike $0.42 credit"`, `"rolled out 2 weeks same strike net credit $0.18"`, `"closed at 52% profit"` |
| 7 | `alternatives` | string | What else was on the table. At least one alternative stated. `"could have waited — stock flirting with strike but market-wide selloff, not name-specific"` |
| 8 | `prediction` | string | **Required. The most important field.** What I expect to happen as a result of this action. Must be specific enough to be falsifiable. Good: `"expect stock recovers above $24 within 2 weeks based on sector rotation"`. Bad: `"hope it works out"`. |
| 9 | `rationale` | string | Why this action over the alternatives. Should reference the rule's underlying reasoning, not just the rule number. |
| 10 | `divergence` | boolean | `true` if this action differs from what the rule-implied action would have been. Every `true` is a data point for the quarterly divergence review (Constitution §13.3). |
| 11 | `snapshot_ref` | string | Filename of the snapshot that informed this decision. Format: `YYYY-MM-DD_TICKER.json`. Links the decision to reproducible market state. |
| 12 | `context` | object | Structured position state at decision time. See §Context below. |

### Context object (field 12)

Captures the position state so the decision can be replayed without re-deriving it.

```json
{
  "position_type": "csp",
  "strike": 25.00,
  "expiration": "2026-09-19",
  "dte": 34,
  "delta_at_entry": 0.28,
  "current_delta": 0.42,
  "credit_received": 0.42,
  "total_credits_this_name": 1.86,
  "net_stock_cost": 23.14,
  "stock_price": 24.50,
  "pct_of_net_liq": 20.8,
  "reserve_after": 52.3,
  "roll_count": 0,
  "days_in_position": 12
}
```

Fields are position-type-dependent. A `thesis_update` or `skip` decision will have a minimal
context (just `stock_price` and `reserve_after`). The schema is intentionally loose here — what
matters is that enough state is captured to replay the decision, not that every field is always
present.

---

## Outcome attachment

When a position closes (profit, loss, assignment, or kill switch), a **separate** JSONL line is
appended linking the outcome to the original decision:

| Field | Type | Description |
|---|---|---|
| `id` | string | New ID: `OUT-YYYYMMDD-NNN` |
| `decision_ref` | string | The `id` of the decision being scored |
| `timestamp` | ISO 8601 | When the outcome was determined |
| `outcome_type` | enum | `profit`, `loss`, `assignment`, `called_away`, `kill_switch`, `expired_worthless` |
| `outcome_detail` | string | What actually happened: `"closed at 51% profit after 18 days, stock never challenged strike"` |
| `prediction_accurate` | boolean | Was the prediction in the original decision roughly correct? Binary — did it happen or not. |
| `prediction_note` | string | How the prediction compared to reality. `"predicted 2-week recovery, actual was 11 days — close"` or `"predicted recovery, stock continued down — prediction wrong, but roll collected $0.34 net credit so position improved"` |
| `net_pnl` | number | Realized P&L on this leg in dollars |

**Why separate lines, not mutations:** append-only means the original decision is never altered.
The reconciliation script (`wheel reconcile`) walks the file, matches `OUT-` lines to `DEC-` lines
by `decision_ref`, and produces the calibration report. This is deterministic and testable —
a golden file with known decisions and known outcomes produces a known calibration.

---

## Decision types — when each is used

| Type | Trigger | Governing rules |
|---|---|---|
| `entry` | Opening a new CSP | ST-ENT-01…08, AL-ENT-01 (when enforced), AL-SEL-02/03 |
| `roll` | Rolling a challenged put | ST-ROL-01…09 |
| `close_profit` | Closing at ≥50% profit | ST-MGT-01, AL-MGT-01 |
| `close_loss` | Closing at a loss (kill switch or other) | AL-RSK-01, Constitution §6 |
| `assignment_accept` | Accepting assignment when credit unavailable | ST-MGT-04, ST-ROL-09 |
| `assignment_sell` | Selling assigned shares immediately | ST-ASN-02, ST-CC-10 |
| `cc_open` | Opening a covered call post-assignment | ST-CC-01…03 |
| `cc_roll` | Rolling a covered call | ST-CC-05 |
| `cc_exit` | Shares called away or sold | ST-CC-07 |
| `kill_switch` | Closing on a broken thesis | AL-RSK-01, Constitution §6 |
| `override` | Acting against the rule-implied action | Constitution §9.4 — `divergence` must be `true` |
| `thesis_update` | Updating `notes/<TICKER>.md` | AL-SEL-04 |
| `skip` | Explicitly deciding NOT to act when action was available | ST-PHI-04 (SOH) |

**The `skip` type matters.** A week where you looked at the screen, had a compliant candidate, and
chose not to trade is a decision. Not logging it means the quarterly review sees a gap rather than
a deliberate call — and gaps get investigated, costing your future self's time.

---

## Reconciliation — how this feeds Article XIII

`wheel reconcile` is a deterministic script that:

1. Walks `decisions.jsonl`
2. Matches `OUT-` lines to `DEC-` lines by `decision_ref`
3. Produces three outputs:

**Calibration report:** prediction accuracy by decision type. "Of 12 roll decisions, 8 predictions
were accurate, 4 were not. Of the 4 misses, 3 were directionally correct but timing was off."

**Divergence report:** all decisions where `divergence: true`, with what the rule said, what was
done instead, and what happened. This is the primary amendment signal.

**Gap report:** all decisions where `rule_id: "NONE"`. Each is either a missing rule or a correctly
identified judgment call under Constitution §7.6.

These three are the first three inputs to the quarterly review (Constitution §13.3). The fourth
(regime identification) is the operator's call and is not automatable.

---

## Examples

### Entry decision
```json
{"id":"DEC-20260815-001","timestamp":"2026-08-15T10:42:00-06:00","ticker":"F","decision_type":"entry","rule_id":"ST-ENT-02","action":"sold CSP 42DTE 0.29d $11 strike $0.14 credit","alternatives":"could open at $10.50 strike for $0.08 — lower delta but premium below 1% threshold; could wait for next week if CPI print is unfavorable","prediction":"expect F stays above $11 through Sept expiry — stock at $12.30 with support at $11.50, no ER until Oct","rationale":"42 DTE gives buffer past Sept FOMC; 0.29 delta within band; $0.14 on $1100 collateral is 1.27% — above the 1% sanity check (ST-SEL-11)","divergence":false,"snapshot_ref":"2026-08-15_F.json","context":{"position_type":"csp","strike":11.00,"expiration":"2026-09-26","dte":42,"delta_at_entry":0.29,"credit_received":0.14,"pct_of_net_liq":9.2,"reserve_after":54.1,"roll_count":0,"days_in_position":0}}
```

### Roll decision
```json
{"id":"DEC-20260901-003","timestamp":"2026-09-01T14:15:00-06:00","ticker":"F","decision_type":"roll","rule_id":"ST-ROL-01","action":"rolled out 2 weeks same $11 strike net credit $0.18","alternatives":"could hold — stock at $11.02 but broad market down 1.8% today, not F-specific; could roll down to $10.50 for $0.12 net credit","prediction":"expect market bounce within 1 week — F fundamentals unchanged, this is macro noise, stock returns above $11.50","rationale":"stock hit strike (condition 1) and I am convinced it stays here because auto sector is weak this week on tariff news (condition 2). Rolling same strike preserves full recovery if prediction is right. 2-week extension keeps total DTE at 28.","divergence":false,"snapshot_ref":"2026-09-01_F.json","context":{"position_type":"csp","strike":11.00,"expiration":"2026-10-10","dte":28,"delta_at_entry":0.29,"current_delta":0.51,"credit_received":0.14,"total_credits_this_name":0.32,"net_stock_cost":10.68,"stock_price":11.02,"pct_of_net_liq":9.2,"reserve_after":54.1,"roll_count":1,"days_in_position":17}}
```

### Outcome attachment
```json
{"id":"OUT-20260920-001","decision_ref":"DEC-20260901-003","timestamp":"2026-09-20T10:00:00-06:00","outcome_type":"profit","outcome_detail":"closed at 54% profit after 19 days — stock recovered to $11.85, GTC limit filled automatically","prediction_accurate":true,"prediction_note":"predicted 1-week bounce, actual was 8 days — close enough. Macro did bounce, F followed.","net_pnl":17.28}
```

### Skip decision
```json
{"id":"DEC-20260822-001","timestamp":"2026-08-22T09:45:00-06:00","ticker":"_BOOK","decision_type":"skip","rule_id":"ST-PHI-04","action":"no new positions opened this week","alternatives":"T screened compliant at 0.28 delta $0.12 credit, but ER in 18 days","prediction":"T reports Oct 8 — opening now would require closing before ER (ST-ENT-05) with only 50% of the cycle available, making 50% profit target unlikely","rationale":"sitting on hands. Reserve at 58%, no challenged positions, no urgency.","divergence":false,"snapshot_ref":"2026-08-22_SCREEN.json","context":{"stock_price":null,"reserve_after":58.0}}
```

---

## File hygiene

- One file: `WheelOps/decisions/decisions.jsonl`
- Append-only. Never edit, never delete, never reorder.
- Each line is valid JSON. No trailing commas, no comments.
- Blank lines are permitted between entries for readability but are ignored by parsers.
- Backup: the file is in iCloud via WheelOps. Git never touches it.

---

## Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-04 | Initial schema. 12 fields + outcome attachment + reconciliation spec. |
