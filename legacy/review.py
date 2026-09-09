"""/wheel-review -- §5.6: reconcile outcomes to predictions, deterministically.

Walks WheelOps/decisions/decisions.jsonl, matches OUT- lines to DEC- lines by
`decision_ref`, and renders the three reports the decision-record schema
specifies: calibration, divergence, and gaps. These are the first three inputs
to the Constitution Article XIII quarterly review (§13.3). The fourth input --
regime identification -- is the operator's call and is deliberately not
produced here.

Pure core, thin IO edge: same ledger, same report, every time.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config_io import load_config, wheelops_dir


def parse_ledger(
    text: str,
) -> tuple[list[dict], list[dict], list[tuple[int, str]]]:
    """Split the JSONL into decisions, outcomes, and unparseable lines.

    Blank lines are permitted by the schema. A corrupt line is surfaced with
    its line number rather than silently skipped -- an append-only ledger
    that quietly loses records defeats its own purpose.
    """

    decisions: list[dict] = []
    outcomes: list[dict] = []
    bad_lines: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            bad_lines.append((line_number, f"not valid JSON: {error}"))
            continue
        if not isinstance(payload, Mapping):
            bad_lines.append((line_number, "not a JSON object"))
            continue
        record_id = payload.get("id")
        if isinstance(record_id, str) and record_id.startswith("DEC-"):
            decisions.append(dict(payload))
        elif isinstance(record_id, str) and record_id.startswith("OUT-"):
            outcomes.append(dict(payload))
        else:
            bad_lines.append(
                (line_number, f"id {record_id!r} is neither DEC- nor OUT-")
            )
    return decisions, outcomes, bad_lines


def match_outcomes(
    decisions: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
) -> tuple[
    list[tuple[Mapping[str, Any], Mapping[str, Any]]],
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
]:
    """(resolved decision+outcome pairs, open decisions, orphan outcomes).

    When several outcomes reference one decision, the latest by id wins for
    calibration; earlier ones are legs of the same story, not double votes.
    """

    by_ref: dict[str, list[Mapping[str, Any]]] = {}
    for outcome in outcomes:
        reference = outcome.get("decision_ref")
        if isinstance(reference, str):
            by_ref.setdefault(reference, []).append(outcome)

    resolved: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    open_decisions: list[Mapping[str, Any]] = []
    matched_refs: set[str] = set()
    for decision in decisions:
        decision_id = str(decision.get("id"))
        matches = by_ref.get(decision_id, [])
        if matches:
            matched_refs.add(decision_id)
            resolved.append(
                (decision, max(matches, key=lambda o: str(o.get("id"))))
            )
        else:
            open_decisions.append(decision)

    known_ids = {str(d.get("id")) for d in decisions}
    orphans = [
        outcome
        for outcome in outcomes
        if str(outcome.get("decision_ref")) not in known_ids
    ]
    return resolved, open_decisions, orphans


def calibration_by_type(
    resolved: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, dict[str, int]]:
    """Prediction accuracy per decision type, over resolved decisions only."""

    table: dict[str, dict[str, int]] = {}
    for decision, outcome in resolved:
        decision_type = str(decision.get("decision_type", "unknown"))
        row = table.setdefault(
            decision_type, {"count": 0, "accurate": 0, "inaccurate": 0}
        )
        row["count"] += 1
        if outcome.get("prediction_accurate") is True:
            row["accurate"] += 1
        else:
            row["inaccurate"] += 1
    return dict(sorted(table.items()))


def _decision_line(decision: Mapping[str, Any]) -> str:
    return (
        f"**{decision.get('id')}** {decision.get('ticker')} "
        f"({decision.get('decision_type')})"
    )


def render_review(
    *,
    run_date: date,
    decisions: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
    bad_lines: Sequence[tuple[int, str]],
) -> str:
    """Render the three §13.3 inputs plus the open-decision list as markdown."""

    resolved, open_decisions, orphans = match_outcomes(decisions, outcomes)
    lines: list[str] = []

    lines.append(f"# Wheel review — {run_date.isoformat()}")
    lines.append("")
    lines.append(
        f"- Ledger: {len(decisions)} decisions · {len(outcomes)} outcomes · "
        f"{len(resolved)} resolved · {len(open_decisions)} open"
    )
    lines.append(
        "- First three inputs to the Article XIII quarterly review "
        "(Constitution §13.3). The fourth — regime identification — is the "
        "operator's call and is not produced by this command."
    )
    lines.append("")

    # ---- 1. Calibration --------------------------------------------------
    lines.append("## Calibration — prediction accuracy by decision type")
    lines.append("")
    calibration = calibration_by_type(resolved)
    if calibration:
        lines.append("| Type | Resolved | Accurate | Inaccurate | Summary |")
        lines.append("|---|---|---|---|---|")
        for decision_type, row in calibration.items():
            lines.append(
                f"| {decision_type} | {row['count']} | {row['accurate']} "
                f"| {row['inaccurate']} | {row['accurate']} of {row['count']} "
                "predictions accurate |"
            )
        lines.append("")
        lines.append("Prediction notes, per resolved decision:")
        for decision, outcome in sorted(
            resolved, key=lambda pair: str(pair[0].get("id"))
        ):
            note = outcome.get("prediction_note") or "no note recorded"
            marker = "✓" if outcome.get("prediction_accurate") is True else "✗"
            lines.append(f"- {marker} {_decision_line(decision)} — {note}")
    else:
        lines.append(
            "No resolved decisions yet — calibration begins once outcomes "
            "are attached."
        )
    lines.append("")

    # ---- 2. Divergence ---------------------------------------------------
    lines.append("## Divergence — decisions against the rule-implied action")
    lines.append("")
    divergent = [d for d in decisions if d.get("divergence") is True]
    if divergent:
        outcome_by_id = {str(d.get("id")): o for d, o in resolved}
        lines.append(
            "The primary amendment signal (Constitution §9.4, §13.3): what "
            "the rule said, what was done instead, and what happened."
        )
        for decision in sorted(divergent, key=lambda d: str(d.get("id"))):
            outcome = outcome_by_id.get(str(decision.get("id")))
            happened = (
                outcome.get("outcome_detail", "no detail recorded")
                if outcome
                else "open — no outcome yet"
            )
            lines.append(f"- {_decision_line(decision)}")
            lines.append(f"  - rule cited: {decision.get('rule_id')}")
            lines.append(f"  - done instead: {decision.get('action')}")
            lines.append(f"  - what happened: {happened}")
    else:
        lines.append("None — no logged decision diverged from its rule.")
    lines.append("")

    # ---- 3. Gaps ---------------------------------------------------------
    lines.append("## Gaps — decisions with no governing rule (rule_id NONE)")
    lines.append("")
    gaps = [d for d in decisions if d.get("rule_id") == "NONE"]
    if gaps:
        lines.append(
            "Each is either a missing rule or a correctly identified "
            "judgment call under Constitution §7.6 — the classification is "
            "the operator's, made in the quarterly review:"
        )
        for decision in sorted(gaps, key=lambda d: str(d.get("id"))):
            lines.append(
                f"- [ ] {_decision_line(decision)} — "
                f"{decision.get('action')} · classify: missing rule / "
                "judgment call"
            )
    else:
        lines.append("None — every logged decision cited a governing rule.")
    lines.append("")

    # ---- Open decisions --------------------------------------------------
    lines.append("## Open decisions — logged, not yet reconciled")
    lines.append("")
    if open_decisions:
        for decision in sorted(open_decisions, key=lambda d: str(d.get("id"))):
            lines.append(
                f"- {_decision_line(decision)} — prediction: "
                f"{decision.get('prediction')}"
            )
    else:
        lines.append("None — every decision has an attached outcome.")
    lines.append("")

    # ---- Ledger integrity ------------------------------------------------
    if orphans or bad_lines:
        lines.append("## Ledger integrity")
        lines.append("")
        for outcome in orphans:
            lines.append(
                f"- orphan outcome {outcome.get('id')} references "
                f"{outcome.get('decision_ref')!r}, which is not in the ledger"
            )
        for line_number, reason in bad_lines:
            lines.append(f"- line {line_number}: {reason}")
        lines.append("")

    return "\n".join(lines)


def run_review(config: Mapping[str, Any], run_date: date) -> tuple[Path, str]:
    """Read the ledger, render the review, write weeks/review-YYYY-MM-DD.md."""

    wheelops = wheelops_dir(config)
    ledger_path = wheelops / "decisions" / "decisions.jsonl"
    text = ledger_path.read_text(encoding="utf-8") if ledger_path.is_file() else ""
    decisions, outcomes, bad_lines = parse_ledger(text)

    markdown = render_review(
        run_date=run_date,
        decisions=decisions,
        outcomes=outcomes,
        bad_lines=bad_lines,
    )
    weeks_dir = wheelops / "weeks"
    weeks_dir.mkdir(parents=True, exist_ok=True)
    path = weeks_dir / f"review-{run_date.isoformat()}.md"
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text(markdown, encoding="utf-8")
    temporary.replace(path)
    return path, markdown


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    run_date = (
        date.fromisoformat(arguments[0]) if arguments else datetime.now().date()
    )
    config = load_config("config.yaml")
    path, _ = run_review(config, run_date)
    print(f"REVIEW {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
