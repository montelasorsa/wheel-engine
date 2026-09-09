"""Tests for /wheel-review: matching, calibration, and the three reports.

A temp ledger covers every report type: one accurate prediction, one
inaccurate, one divergence, one gap, one open decision, plus an orphan
outcome and a corrupt line for the integrity section. No network.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from wheel.review import (
    calibration_by_type,
    match_outcomes,
    parse_ledger,
    render_review,
    run_review,
)

RUN_DATE = date(2026, 9, 30)


def decision(record_id: str, **overrides) -> dict:
    base = {
        "id": record_id,
        "timestamp": "2026-08-15T10:00:00-06:00",
        "ticker": "F",
        "decision_type": "entry",
        "rule_id": "ST-ENT-02",
        "action": "sold CSP $11 strike",
        "alternatives": "waited",
        "prediction": "stays above $11",
        "rationale": "in band",
        "divergence": False,
        "snapshot_ref": "2026-08-15_F.json",
        "context": {"stock_price": 12.30},
    }
    base.update(overrides)
    return base


def outcome(record_id: str, ref: str, **overrides) -> dict:
    base = {
        "id": record_id,
        "decision_ref": ref,
        "timestamp": "2026-09-20T10:00:00-06:00",
        "outcome_type": "profit",
        "outcome_detail": "closed at 52% profit after 19 days",
        "prediction_accurate": True,
        "prediction_note": "predicted recovery, got it in 11 days",
        "net_pnl": 17.28,
    }
    base.update(overrides)
    return base


LEDGER_RECORDS = [
    # 1. entry, resolved, prediction accurate
    decision("DEC-20260815-001"),
    # 2. roll, resolved, prediction WRONG
    decision(
        "DEC-20260815-002",
        ticker="T",
        decision_type="roll",
        rule_id="ST-ROL-01",
        action="rolled out 2 weeks same strike",
        prediction="market bounce within 1 week",
    ),
    # 3. divergence: acted against the rule, resolved
    decision(
        "DEC-20260816-001",
        ticker="KO",
        decision_type="close_loss",
        rule_id="ST-MGT-01",
        action="closed early at 30% loss",
        divergence=True,
        prediction="further decline past $52",
    ),
    # 4. gap: no governing rule; open (no outcome yet)
    decision(
        "DEC-20260822-001",
        ticker="_BOOK",
        decision_type="skip",
        rule_id="NONE",
        action="no new positions this week",
        prediction="T reports Oct 8; cycle too short to hit 50%",
    ),
    outcome("OUT-20260920-001", "DEC-20260815-001"),
    outcome(
        "OUT-20260920-002",
        "DEC-20260815-002",
        outcome_type="assignment",
        outcome_detail="no bounce; assigned at $27",
        prediction_accurate=False,
        prediction_note="predicted bounce, market kept falling",
        net_pnl=-140.0,
    ),
    outcome(
        "OUT-20260921-001",
        "DEC-20260816-001",
        outcome_type="loss",
        outcome_detail="stock recovered two weeks later; early close locked the loss",
        prediction_accurate=False,
        prediction_note="predicted further decline; it recovered",
        net_pnl=-96.0,
    ),
    # orphan: references a decision that is not in the ledger
    outcome("OUT-20260922-001", "DEC-20260101-999"),
]


def ledger_text() -> str:
    lines = [json.dumps(r, separators=(",", ":")) for r in LEDGER_RECORDS]
    lines.insert(2, "")            # blank line: permitted by the schema
    lines.append("{corrupt json")  # must be surfaced, not swallowed
    return "\n".join(lines) + "\n"


class ParseAndMatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.decisions, self.outcomes, self.bad = parse_ledger(ledger_text())

    def test_splits_decisions_outcomes_and_corrupt_lines(self) -> None:
        self.assertEqual(len(self.decisions), 4)
        self.assertEqual(len(self.outcomes), 4)
        self.assertEqual(len(self.bad), 1)
        self.assertIn("not valid JSON", self.bad[0][1])

    def test_matches_by_decision_ref(self) -> None:
        resolved, open_decisions, orphans = match_outcomes(
            self.decisions, self.outcomes
        )
        self.assertEqual(len(resolved), 3)
        self.assertEqual(
            [d["id"] for d in open_decisions], ["DEC-20260822-001"]
        )
        self.assertEqual([o["id"] for o in orphans], ["OUT-20260922-001"])

    def test_calibration_counts_by_type(self) -> None:
        resolved, _, _ = match_outcomes(self.decisions, self.outcomes)
        table = calibration_by_type(resolved)
        self.assertEqual(
            table["entry"], {"count": 1, "accurate": 1, "inaccurate": 0}
        )
        self.assertEqual(
            table["roll"], {"count": 1, "accurate": 0, "inaccurate": 1}
        )
        self.assertEqual(
            table["close_loss"], {"count": 1, "accurate": 0, "inaccurate": 1}
        )


class RenderTests(unittest.TestCase):
    def setUp(self) -> None:
        decisions, outcomes, bad = parse_ledger(ledger_text())
        self.markdown = render_review(
            run_date=RUN_DATE,
            decisions=decisions,
            outcomes=outcomes,
            bad_lines=bad,
        )

    def test_all_expected_sections_present_in_order(self) -> None:
        positions = [
            self.markdown.index("# Wheel review — 2026-09-30"),
            self.markdown.index("## Calibration"),
            self.markdown.index("## Divergence"),
            self.markdown.index("## Gaps"),
            self.markdown.index("## Open decisions"),
            self.markdown.index("## Ledger integrity"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_calibration_table_rows(self) -> None:
        self.assertIn(
            "| entry | 1 | 1 | 0 | 1 of 1 predictions accurate |", self.markdown
        )
        self.assertIn(
            "| roll | 1 | 0 | 1 | 0 of 1 predictions accurate |", self.markdown
        )

    def test_accurate_and_inaccurate_predictions_are_marked(self) -> None:
        self.assertIn("✓ **DEC-20260815-001**", self.markdown)
        self.assertIn("✗ **DEC-20260815-002**", self.markdown)

    def test_divergence_shows_rule_action_and_outcome(self) -> None:
        section = self.markdown[self.markdown.index("## Divergence"):]
        self.assertIn("DEC-20260816-001", section)
        self.assertIn("rule cited: ST-MGT-01", section)
        self.assertIn("done instead: closed early at 30% loss", section)
        self.assertIn("what happened: stock recovered two weeks later", section)

    def test_gap_lists_none_rule_decisions_for_classification(self) -> None:
        section = self.markdown[self.markdown.index("## Gaps"):]
        self.assertIn("DEC-20260822-001", section)
        self.assertIn("classify: missing rule / judgment call", section)
        self.assertIn("§7.6", section)

    def test_open_decisions_listed_with_their_predictions(self) -> None:
        section = self.markdown[self.markdown.index("## Open decisions"):]
        self.assertIn("DEC-20260822-001", section)
        self.assertIn("cycle too short to hit 50%", section)

    def test_integrity_surfaces_orphans_and_corrupt_lines(self) -> None:
        section = self.markdown[self.markdown.index("## Ledger integrity"):]
        self.assertIn("OUT-20260922-001", section)
        self.assertIn("not valid JSON", section)

    def test_regime_identification_is_explicitly_not_produced(self) -> None:
        self.assertIn("regime identification", self.markdown)
        self.assertIn("not produced by this command", self.markdown)

    def test_render_is_deterministic(self) -> None:
        decisions, outcomes, bad = parse_ledger(ledger_text())
        again = render_review(
            run_date=RUN_DATE,
            decisions=decisions,
            outcomes=outcomes,
            bad_lines=bad,
        )
        self.assertEqual(self.markdown, again)


class RunReviewTests(unittest.TestCase):
    def test_writes_review_file_under_weeks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wheelops = Path(directory)
            (wheelops / "decisions").mkdir()
            (wheelops / "decisions" / "decisions.jsonl").write_text(
                ledger_text()
            )
            config = {"paths": {"wheelops": str(wheelops)}}
            path, markdown = run_review(config, RUN_DATE)
            self.assertEqual(path, wheelops / "weeks" / "review-2026-09-30.md")
            self.assertEqual(path.read_text(encoding="utf-8"), markdown)

    def test_empty_ledger_renders_a_valid_empty_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = {"paths": {"wheelops": directory}}
            _, markdown = run_review(config, RUN_DATE)
            self.assertIn("No resolved decisions yet", markdown)
            self.assertIn("## Open decisions", markdown)


if __name__ == "__main__":
    unittest.main()
