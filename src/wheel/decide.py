"""/wheel-decide -- log one judgment call, with its prediction, append-only.

Interactive CLI over `decision_record.py`. Prompts for the operator-supplied
fields, auto-populates id / timestamp / snapshot_ref / context, prints the
full record back, and appends only after explicit confirmation. Nothing here
recommends an action -- the operator is logging a decision they already made
(AGENTS.md §4: the tool proposes; the operator decides).

Run through commands/wheel-decide, or directly:

    PYTHONPATH=src python -m wheel.decide
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .config_io import load_config, wheelops_dir
from .decision_record import (
    DECISION_TYPES,
    append_decision_record,
    next_decision_id,
    read_existing_ids,
    validate_decision_record,
)
from .screen import read_position_rows
from .snapshot_schema import resolve_field
from .week_report import open_positions

PromptFn = Callable[[str], str]
PrintFn = Callable[[str], None]


def latest_snapshot_for(snapshots_dir: Path, ticker: str) -> Path | None:
    """Newest YYYY-MM-DD_TICKER.json by filename; the stamp sorts itself."""

    candidates = sorted(snapshots_dir.glob(f"*_{ticker}.json"))
    return candidates[-1] if candidates else None


def build_context(
    snapshot_document: Mapping[str, Any] | None,
    *,
    ticker: str,
    net_liq: float | None,
    position_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Auto-populated position state; deliberately loose per the schema."""

    context: dict[str, Any] = {}
    if snapshot_document is not None:
        try:
            price = resolve_field(snapshot_document, "price.current")
        except KeyError:
            price = None
        if isinstance(price, (int, float)):
            context["stock_price"] = float(price)

    positions = open_positions(position_rows)
    if net_liq and net_liq > 0:
        deployed = sum(float(p["collateral"]) for p in positions)
        context["reserve_after"] = round(100.0 * (net_liq - deployed) / net_liq, 1)

    mine = [p for p in positions if p["ticker"] == ticker]
    if mine:
        position = mine[0]
        context["position_type"] = "csp"
        context["strike"] = position["strike"]
        context["contracts"] = position["contracts"]
        if net_liq and net_liq > 0:
            context["pct_of_net_liq"] = round(
                100.0 * position["collateral"] / net_liq, 1
            )
    return context


def _prompt_required(ask: PromptFn, say: PrintFn, label: str, *, why: str = "") -> str:
    while True:
        value = ask(f"{label}: ").strip()
        if value:
            return value
        say(f"  {label} is required." + (f" {why}" if why else ""))


def _prompt_decision_type(ask: PromptFn, say: PrintFn) -> str:
    say("decision_type — one of:")
    for index, name in enumerate(DECISION_TYPES, 1):
        say(f"  {index:2d}. {name}")
    while True:
        raw = ask("decision_type (name or number): ").strip().lower()
        if raw.isdigit() and 1 <= int(raw) <= len(DECISION_TYPES):
            return DECISION_TYPES[int(raw) - 1]
        if raw in DECISION_TYPES:
            return raw
        say(f"  {raw!r} is not in the schema enum.")


def _prompt_rule_id(ask: PromptFn, say: PrintFn) -> str:
    while True:
        raw = ask("rule_id (e.g. ST-ROL-01; empty = NONE): ").strip().upper()
        if not raw:
            say("  Logged as NONE — a gap signal, not an error (schema field 5).")
            return "NONE"
        probe = validate_decision_record({"rule_id": raw})
        if not any(error.startswith("rule_id") for error in probe):
            return raw
        say(f"  {raw!r} is neither a rule ID nor NONE.")


def _prompt_divergence(ask: PromptFn, say: PrintFn, decision_type: str) -> bool:
    while True:
        raw = ask("divergence from the rule-implied action? [y/N]: ").strip().lower()
        answer = raw in ("y", "yes")
        if decision_type == "override" and not answer:
            say(
                "  An override IS a divergence by definition "
                "(Constitution §9.4). Answer y, or pick a different type."
            )
            continue
        return answer


def run_interactive(
    config: Mapping[str, Any],
    *,
    now: datetime,
    ask: PromptFn,
    say: PrintFn,
) -> Path | None:
    """One prompted decision; returns the JSONL path, or None if aborted."""

    wheelops = wheelops_dir(config)
    decisions_path = wheelops / "decisions" / "decisions.jsonl"
    account = config.get("account") or {}
    net_liq = float(account["net_liq"]) if "net_liq" in account else None

    ticker = _prompt_required(ask, say, "ticker").upper()
    decision_type = _prompt_decision_type(ask, say)
    rule_id = _prompt_rule_id(ask, say)
    action = _prompt_required(ask, say, "action")
    alternatives = _prompt_required(
        ask, say, "alternatives", why="State at least one alternative."
    )
    prediction = _prompt_required(
        ask,
        say,
        "prediction",
        why=(
            "The most important field: without it this decision can never "
            "be scored (AL-OPS-05). Make it falsifiable."
        ),
    )
    rationale = _prompt_required(ask, say, "rationale")
    divergence = _prompt_divergence(ask, say, decision_type)

    snapshot_path = latest_snapshot_for(wheelops / "snapshots", ticker)
    snapshot_document: Mapping[str, Any] | None = None
    if snapshot_path is not None:
        snapshot_ref = snapshot_path.name
        try:
            snapshot_document = json.loads(snapshot_path.read_text())
        except (OSError, json.JSONDecodeError):
            snapshot_document = None
    else:
        say(f"No snapshot found for {ticker} in {wheelops / 'snapshots'}.")
        snapshot_ref = ask(
            "snapshot_ref (filename, e.g. 2026-08-15_F.json; empty aborts): "
        ).strip()
        if not snapshot_ref:
            say("Aborted — a decision must reference the market state it saw.")
            return None

    record: dict[str, Any] = {
        "id": next_decision_id(read_existing_ids(decisions_path), now.date()),
        "timestamp": now.isoformat(timespec="seconds"),
        "ticker": ticker,
        "decision_type": decision_type,
        "rule_id": rule_id,
        "action": action,
        "alternatives": alternatives,
        "prediction": prediction,
        "rationale": rationale,
        "divergence": divergence,
        "snapshot_ref": snapshot_ref,
        "context": build_context(
            snapshot_document,
            ticker=ticker,
            net_liq=net_liq,
            position_rows=read_position_rows(wheelops / "positions"),
        ),
    }

    errors = validate_decision_record(record)
    if errors:
        say("Record is invalid; nothing written:")
        for error in errors:
            say(f"  - {error}")
        return None

    say("")
    say(json.dumps(record, indent=2, ensure_ascii=False))
    say("")
    confirmation = ask("Append this record to decisions.jsonl? [y/N]: ").strip().lower()
    if confirmation not in ("y", "yes"):
        say("Aborted — nothing written.")
        return None

    path = append_decision_record(decisions_path, record)
    say(f"Appended {record['id']} to {path}")
    return path


def main() -> int:
    config = load_config("config.yaml")
    result = run_interactive(
        config,
        now=datetime.now().astimezone(),
        ask=input,
        say=print,
    )
    return 0 if result is not None else 1


if __name__ == "__main__":
    sys.exit(main())
