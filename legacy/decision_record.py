"""Decision records: the pure core of /wheel-decide.

Implements docs/decision-record-schema.md (AL-OPS-05, Constitution §9.3/§9.4):
twelve required fields written at decision time, append-only JSONL, outcomes
attached later as separate OUT- lines by /wheel-review (§5.6, not built here).

The prediction field is the point of the whole record. A rationale without a
prediction cannot be scored, only re-read -- so an empty prediction is refused
at validation, not merely discouraged.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

# Schema field 4 -- the full enum, in schema order.
DECISION_TYPES = (
    "entry",
    "roll",
    "close_profit",
    "close_loss",
    "assignment_accept",
    "assignment_sell",
    "cc_open",
    "cc_roll",
    "cc_exit",
    "kill_switch",
    "override",
    "thesis_update",
    "skip",
)

# Schema order matters for readability of the JSONL; python dicts preserve it.
REQUIRED_FIELDS = (
    "id",
    "timestamp",
    "ticker",
    "decision_type",
    "rule_id",
    "action",
    "alternatives",
    "prediction",
    "rationale",
    "divergence",
    "snapshot_ref",
    "context",
)

_ID_PATTERN = re.compile(r"^DEC-\d{8}-\d{3}$")
_RULE_ID_PATTERN = re.compile(r"^(?:(?:ST|AL)-[A-Z]{3}-\d{2}|NONE)$")
# Uppercase tickers; leading underscore allowed for book-level records like
# the schema's own `_BOOK` skip example.
_TICKER_PATTERN = re.compile(r"^_?[A-Z][A-Z0-9.\-]*$|^_[A-Z]+$")


def _text(record: Mapping[str, Any], field: str) -> str | None:
    value = record.get(field)
    return value if isinstance(value, str) and value.strip() else None


def validate_decision_record(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Every schema violation in one pass; empty tuple means appendable."""

    errors: list[str] = []
    if not isinstance(record, Mapping):
        return ("record: expected an object",)

    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"{field}: required field is missing")

    record_id = record.get("id")
    if isinstance(record_id, str) and not _ID_PATTERN.match(record_id):
        errors.append(f"id: {record_id!r} does not match DEC-YYYYMMDD-NNN")

    timestamp = record.get("timestamp")
    if isinstance(timestamp, str):
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            errors.append(f"timestamp: {timestamp!r} is not ISO 8601")
    elif timestamp is not None:
        errors.append("timestamp: must be an ISO 8601 string")

    ticker = record.get("ticker")
    if isinstance(ticker, str) and not _TICKER_PATTERN.match(ticker):
        errors.append(f"ticker: {ticker!r} must be uppercase")

    decision_type = record.get("decision_type")
    if decision_type is not None and decision_type not in DECISION_TYPES:
        errors.append(
            f"decision_type: {decision_type!r} is not one of the schema enum"
        )

    rule_id = record.get("rule_id")
    if isinstance(rule_id, str) and not _RULE_ID_PATTERN.match(rule_id):
        errors.append(
            f"rule_id: {rule_id!r} is neither a rule ID nor the literal NONE"
        )

    for field in ("action", "alternatives", "rationale"):
        if field in record and _text(record, field) is None:
            errors.append(f"{field}: must be a non-empty string")

    # The most important field. Refused empty, not defaulted.
    if "prediction" in record and _text(record, "prediction") is None:
        errors.append(
            "prediction: REQUIRED and must not be empty -- a decision "
            "without a prediction cannot be scored, only re-read"
        )

    divergence = record.get("divergence")
    if "divergence" in record and not isinstance(divergence, bool):
        errors.append("divergence: must be a boolean")
    # Constitution §9.4: an override IS a divergence by definition.
    if decision_type == "override" and divergence is not True:
        errors.append(
            "divergence: must be true for decision_type=override "
            "(Constitution §9.4)"
        )

    snapshot_ref = record.get("snapshot_ref")
    if isinstance(snapshot_ref, str):
        if not snapshot_ref.endswith(".json"):
            errors.append(f"snapshot_ref: {snapshot_ref!r} is not a .json filename")
    elif snapshot_ref is not None:
        errors.append("snapshot_ref: must be a snapshot filename string")

    context = record.get("context")
    if "context" in record and not isinstance(context, Mapping):
        errors.append("context: must be an object")

    unknown = [key for key in record if key not in REQUIRED_FIELDS]
    for key in unknown:
        errors.append(f"{key}: unexpected field (the schema has 12 fields)")

    return tuple(errors)


def next_decision_id(existing_ids: Sequence[str], on: date) -> str:
    """Monotonic DEC-YYYYMMDD-NNN for one day; OUT- lines never count."""

    stamp = on.strftime("%Y%m%d")
    prefix = f"DEC-{stamp}-"
    highest = 0
    for record_id in existing_ids:
        if isinstance(record_id, str) and record_id.startswith(prefix):
            tail = record_id[len(prefix):]
            if tail.isdigit():
                highest = max(highest, int(tail))
    return f"{prefix}{highest + 1:03d}"


def read_existing_ids(path: str | Path) -> tuple[str, ...]:
    """All record ids currently in the JSONL; blank lines are permitted."""

    jsonl = Path(path)
    if not jsonl.is_file():
        return ()
    ids: list[str] = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue  # a corrupt line is /wheel-review's problem to surface
        if isinstance(payload, Mapping) and isinstance(payload.get("id"), str):
            ids.append(payload["id"])
    return tuple(ids)


def append_decision_record(
    path: str | Path,
    record: Mapping[str, Any],
) -> Path:
    """Append one validated record as a single compact JSONL line.

    Append-only by construction: open mode "a", never rewrite, never reorder.
    """

    errors = validate_decision_record(record)
    if errors:
        raise ValueError(
            "Refusing to append an invalid decision record:\n  - "
            + "\n  - ".join(errors)
        )
    jsonl = Path(path)
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    with jsonl.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return jsonl
