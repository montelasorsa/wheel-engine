"""Tests for /wheel-decide: schema validation, ID sequencing, and the CLI.

The CLI is driven with scripted prompts against a temporary WheelOps sibling;
every appended line is validated against docs/decision-record-schema.md via
`validate_decision_record`. No network, no real WheelOps.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from wheel.decide import build_context, latest_snapshot_for, run_interactive
from wheel.decision_record import (
    DECISION_TYPES,
    append_decision_record,
    next_decision_id,
    read_existing_ids,
    validate_decision_record,
)

GOLDEN_DIR = Path(__file__).parent / "golden"

VALID_RECORD = {
    "id": "DEC-20260815-001",
    "timestamp": "2026-08-15T10:42:00-06:00",
    "ticker": "F",
    "decision_type": "entry",
    "rule_id": "ST-ENT-02",
    "action": "sold CSP 42DTE 0.29d $11 strike $0.14 credit",
    "alternatives": "could have waited for the CPI print",
    "prediction": "expect F stays above $11 through Sept expiry",
    "rationale": "42 DTE clears FOMC; delta in band (ST-ENT-02)",
    "divergence": False,
    "snapshot_ref": "2026-08-15_F.json",
    "context": {"stock_price": 12.30, "reserve_after": 100.0},
}


class ValidatorTests(unittest.TestCase):
    def test_valid_record_passes(self) -> None:
        self.assertEqual(validate_decision_record(VALID_RECORD), ())

    def test_every_field_is_required(self) -> None:
        for field in VALID_RECORD:
            with self.subTest(field=field):
                record = {k: v for k, v in VALID_RECORD.items() if k != field}
                self.assertTrue(
                    any(e.startswith(field) for e in validate_decision_record(record))
                )

    def test_empty_prediction_is_refused(self) -> None:
        record = dict(VALID_RECORD, prediction="   ")
        errors = validate_decision_record(record)
        self.assertTrue(any("prediction" in e for e in errors))
        self.assertTrue(any("cannot be scored" in e for e in errors))

    def test_unknown_decision_type_is_refused(self) -> None:
        record = dict(VALID_RECORD, decision_type="vibe_check")
        self.assertTrue(validate_decision_record(record))

    def test_all_thirteen_schema_types_are_accepted(self) -> None:
        self.assertEqual(len(DECISION_TYPES), 13)
        for decision_type in DECISION_TYPES:
            record = dict(VALID_RECORD, decision_type=decision_type)
            if decision_type == "override":
                record["divergence"] = True
            with self.subTest(decision_type=decision_type):
                self.assertEqual(validate_decision_record(record), ())

    def test_override_without_divergence_is_refused(self) -> None:
        record = dict(VALID_RECORD, decision_type="override", divergence=False)
        self.assertTrue(
            any("§9.4" in e for e in validate_decision_record(record))
        )

    def test_rule_id_accepts_none_and_rejects_invented_shapes(self) -> None:
        self.assertEqual(
            validate_decision_record(dict(VALID_RECORD, rule_id="NONE")), ()
        )
        self.assertTrue(
            validate_decision_record(dict(VALID_RECORD, rule_id="ST-YOLO-1"))
        )

    def test_lowercase_ticker_is_refused_but_book_records_pass(self) -> None:
        self.assertTrue(validate_decision_record(dict(VALID_RECORD, ticker="f")))
        self.assertEqual(
            validate_decision_record(dict(VALID_RECORD, ticker="_BOOK")), ()
        )

    def test_unexpected_field_is_refused(self) -> None:
        self.assertTrue(validate_decision_record(dict(VALID_RECORD, mood="good")))


class IdSequenceTests(unittest.TestCase):
    DAY = date(2026, 8, 15)

    def test_first_id_of_the_day(self) -> None:
        self.assertEqual(next_decision_id((), self.DAY), "DEC-20260815-001")

    def test_increments_within_the_day(self) -> None:
        ids = ("DEC-20260815-001", "DEC-20260815-002")
        self.assertEqual(next_decision_id(ids, self.DAY), "DEC-20260815-003")

    def test_other_days_and_outcome_lines_do_not_count(self) -> None:
        ids = ("DEC-20260814-009", "OUT-20260815-001")
        self.assertEqual(next_decision_id(ids, self.DAY), "DEC-20260815-001")


class AppendTests(unittest.TestCase):
    def test_appends_one_compact_line_and_never_rewrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions" / "decisions.jsonl"
            append_decision_record(path, VALID_RECORD)
            second = dict(VALID_RECORD, id="DEC-20260815-002")
            append_decision_record(path, second)
            lines = path.read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0]), VALID_RECORD)
            self.assertEqual(json.loads(lines[1]), second)
            self.assertNotIn(" ", lines[0].split('","')[0])  # compact separators

    def test_invalid_record_is_refused_and_nothing_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            with self.assertRaises(ValueError):
                append_decision_record(path, dict(VALID_RECORD, prediction=""))
            self.assertFalse(path.exists())

    def test_blank_lines_are_tolerated_when_reading_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            line = json.dumps(VALID_RECORD, separators=(",", ":"))
            path.write_text(line + "\n\n" + "\n")
            self.assertEqual(read_existing_ids(path), ("DEC-20260815-001",))


class InteractiveCliTests(unittest.TestCase):
    NOW = datetime(2026, 8, 15, 14, 30, tzinfo=timezone.utc)

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.wheelops = Path(self._directory.name)
        (self.wheelops / "snapshots").mkdir()
        shutil.copy(
            GOLDEN_DIR / "2026-08-15_F.json",
            self.wheelops / "snapshots" / "2026-08-15_F.json",
        )
        self.addCleanup(self._directory.cleanup)
        self.config = {
            "paths": {"wheelops": str(self.wheelops)},
            "account": {"net_liq": 12000, "per_name_cap": 0.25},
        }
        self.said: list[str] = []

    def drive(self, answers: list[str]) -> Path | None:
        feed = iter(answers)
        return run_interactive(
            self.config,
            now=self.NOW,
            ask=lambda _prompt: next(feed),
            say=self.said.append,
        )

    def test_full_flow_appends_a_schema_valid_record(self) -> None:
        path = self.drive(
            [
                "f",                       # ticker, normalized to F
                "entry",                   # decision_type
                "ST-ENT-02",               # rule_id
                "sold CSP $11 strike",     # action
                "could have waited",       # alternatives
                "F stays above $11 through expiry",  # prediction
                "delta and DTE in band",   # rationale
                "n",                       # divergence
                "y",                       # confirm
            ]
        )
        self.assertIsNotNone(path)
        lines = path.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(validate_decision_record(record), ())
        self.assertEqual(record["id"], "DEC-20260815-001")
        self.assertEqual(record["ticker"], "F")
        self.assertEqual(record["snapshot_ref"], "2026-08-15_F.json")
        self.assertEqual(record["context"]["stock_price"], 12.30)
        self.assertEqual(record["context"]["reserve_after"], 100.0)

    def test_empty_prediction_is_reprompted_not_accepted(self) -> None:
        path = self.drive(
            [
                "F", "entry", "", "sold CSP", "could have waited",
                "",                                  # empty prediction: refused
                "   ",                               # whitespace: refused again
                "recovers above $12 in two weeks",   # accepted
                "reasoning", "n", "y",
            ]
        )
        record = json.loads(path.read_text().splitlines()[0])
        self.assertEqual(record["prediction"], "recovers above $12 in two weeks")
        self.assertEqual(record["rule_id"], "NONE")
        self.assertTrue(any("prediction is required" in s for s in self.said))

    def test_declining_confirmation_writes_nothing(self) -> None:
        path = self.drive(
            [
                "F", "entry", "ST-ENT-02", "act", "alt",
                "a real prediction", "why", "n",
                "n",                       # decline at confirmation
            ]
        )
        self.assertIsNone(path)
        self.assertFalse(
            (self.wheelops / "decisions" / "decisions.jsonl").exists()
        )
        self.assertTrue(any("nothing written" in s for s in self.said))

    def test_override_requires_divergence_true(self) -> None:
        path = self.drive(
            [
                "F", "override", "NONE", "act", "alt", "pred", "why",
                "n",                       # refused: override must diverge
                "y",                       # accepted
                "y",                       # confirm
            ]
        )
        record = json.loads(path.read_text().splitlines()[0])
        self.assertTrue(record["divergence"])

    def test_ids_increment_across_runs(self) -> None:
        answers = [
            "F", "entry", "ST-ENT-02", "act", "alt", "pred", "why", "n", "y",
        ]
        self.drive(list(answers))
        path = self.drive(list(answers))
        ids = [json.loads(line)["id"] for line in path.read_text().splitlines()]
        self.assertEqual(ids, ["DEC-20260815-001", "DEC-20260815-002"])

    def test_no_snapshot_and_no_manual_ref_aborts(self) -> None:
        path = self.drive(
            [
                "ZZZZ", "skip", "ST-PHI-04", "no action", "alt", "pred",
                "why", "n",
                "",                        # no manual snapshot_ref: abort
            ]
        )
        self.assertIsNone(path)


class ContextTests(unittest.TestCase):
    def test_position_row_enriches_context(self) -> None:
        document = json.loads((GOLDEN_DIR / "2026-08-15_F.json").read_text())
        context = build_context(
            document,
            ticker="F",
            net_liq=12000.0,
            position_rows=[
                {"ticker": "F", "sector": "Consumer Cyclical", "strike": "11",
                 "contracts": "1", "status": "open"},
            ],
        )
        self.assertEqual(context["stock_price"], 12.30)
        self.assertEqual(context["strike"], 11.0)
        self.assertEqual(context["pct_of_net_liq"], 9.2)
        self.assertAlmostEqual(context["reserve_after"], 90.8)

    def test_latest_snapshot_picks_the_newest_stamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshots = Path(directory)
            (snapshots / "2026-08-08_F.json").write_text("{}")
            (snapshots / "2026-08-15_F.json").write_text("{}")
            (snapshots / "2026-08-15_FSLR.json").write_text("{}")
            found = latest_snapshot_for(snapshots, "F")
            self.assertEqual(found.name, "2026-08-15_F.json")


if __name__ == "__main__":
    unittest.main()
