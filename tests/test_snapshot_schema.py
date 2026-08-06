"""Golden-file tests for the Layer 0 snapshot contract.

Two golden files carry the load. `2026-08-15_F.json` is a fully-populated
equity: every field a free-data snapshot can fill is filled, so it proves the
contract is satisfiable in practice. `2026-08-15_SPY-minimal.json` is an ETF
with the entire equity-only half null, which is the case ST-SEL-08 admits and
the one most likely to be broken by a careless "required" tightening.

Offline: no network, no clock, no provider.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from wheel.snapshot_schema import (
    RULE_FIELD_MAP,
    SCHEMA_VERSION,
    SNAPSHOT_SCHEMA,
    UNSATISFIABLE_AT_LAYER_0,
    SnapshotSchemaError,
    assert_valid_snapshot,
    resolve_field,
    snapshot_filename,
    validate_snapshot,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
EQUITY_GOLDEN = GOLDEN_DIR / "2026-08-15_F.json"
ETF_GOLDEN = GOLDEN_DIR / "2026-08-15_SPY-minimal.json"

# Every selection rule the schema is required to serve, from Source Brief v2.0.
ST_SEL_RULES = tuple(f"ST-SEL-{n:02d}" for n in range(1, 15))
AL_SEL_RULES = tuple(f"AL-SEL-{n:02d}" for n in range(1, 7))
AL_SIZ_RULES = tuple(f"AL-SIZ-{n:02d}" for n in range(1, 5))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


class GoldenFileTests(unittest.TestCase):
    def test_equity_golden_satisfies_the_contract(self) -> None:
        self.assertEqual(validate_snapshot(load(EQUITY_GOLDEN)), ())

    def test_etf_golden_satisfies_the_contract(self) -> None:
        # ST-SEL-08: ETFs are valid candidates. Null fundamentals and null
        # analyst consensus must validate, not fail.
        self.assertEqual(validate_snapshot(load(ETF_GOLDEN)), ())

    def test_golden_filenames_match_the_snapshot_ref_format(self) -> None:
        # decision-record-schema.md field 11: snapshot_ref is YYYY-MM-DD_TICKER.json
        document = load(EQUITY_GOLDEN)
        self.assertEqual(
            snapshot_filename(document["snapshot_date"], document["ticker"]),
            EQUITY_GOLDEN.name,
        )

    def test_equity_golden_fills_every_free_data_field(self) -> None:
        """A fully-populated snapshot leaves only the Component B fields null."""

        document = load(EQUITY_GOLDEN)
        expected_null = {
            "volatility.implied_volatility",
            "options.bid_ask_spread_at_target",
            "options.open_interest_at_target",
            "options.premium_pct_of_collateral",
        }
        actual_null = set()
        for section, spec in SNAPSHOT_SCHEMA.items():
            if not isinstance(spec, dict):
                continue
            for field in spec:
                dotted = f"{section}.{field}"
                if resolve_field(document, dotted) is None:
                    actual_null.add(dotted)
        self.assertEqual(actual_null, expected_null)


class RuleCoverageTests(unittest.TestCase):
    """Every required rule is either mapped to fields or declared unsatisfiable."""

    def test_every_selection_rule_is_accounted_for(self) -> None:
        required = set(ST_SEL_RULES + AL_SEL_RULES + AL_SIZ_RULES)
        accounted = set(RULE_FIELD_MAP) | set(UNSATISFIABLE_AT_LAYER_0)
        self.assertEqual(
            required - accounted,
            set(),
            "rules neither mapped to fields nor declared unsatisfiable",
        )

    def test_no_rule_is_both_mapped_and_declared_unsatisfiable(self) -> None:
        self.assertEqual(set(RULE_FIELD_MAP) & set(UNSATISFIABLE_AT_LAYER_0), set())

    def test_every_unsatisfiable_rule_states_a_reason(self) -> None:
        for rule, reason in UNSATISFIABLE_AT_LAYER_0.items():
            self.assertTrue(reason.strip(), f"{rule} has no stated reason")

    def test_mapped_fields_resolve_against_the_schema(self) -> None:
        """A field rename cannot silently orphan the rule that depends on it."""

        for rule, fields in RULE_FIELD_MAP.items():
            for dotted in fields:
                section, _, field = dotted.partition(".")
                self.assertIn(section, SNAPSHOT_SCHEMA, f"{rule} -> {dotted}")
                self.assertIn(field, SNAPSHOT_SCHEMA[section], f"{rule} -> {dotted}")

    def test_mapped_fields_resolve_against_the_golden_file(self) -> None:
        document = load(EQUITY_GOLDEN)
        for rule, fields in RULE_FIELD_MAP.items():
            for dotted in fields:
                try:
                    resolve_field(document, dotted)
                except KeyError:
                    self.fail(f"{rule} needs {dotted}, absent from the golden file")

    def test_hard_gate_rules_are_answerable_from_the_equity_golden(self) -> None:
        """The four hard gates must be non-null on a fully-populated snapshot."""

        document = load(EQUITY_GOLDEN)
        for rule in ("ST-SEL-01", "ST-SEL-02", "ST-SEL-03", "ST-SEL-04"):
            for dotted in RULE_FIELD_MAP[rule]:
                self.assertIsNotNone(
                    resolve_field(document, dotted),
                    f"{rule} cannot be evaluated: {dotted} is null",
                )


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = load(EQUITY_GOLDEN)

    def test_missing_required_field_is_reported_with_its_path(self) -> None:
        del self.document["fundamentals"]["net_income_ttm"]
        errors = validate_snapshot(self.document)
        self.assertIn("fundamentals.net_income_ttm: required field is missing", errors)

    def test_missing_whole_section_is_reported(self) -> None:
        del self.document["earnings"]
        self.assertIn("earnings: required object is missing", validate_snapshot(self.document))

    def test_wrong_type_is_reported(self) -> None:
        self.document["price"]["current"] = "12.30"
        errors = validate_snapshot(self.document)
        self.assertTrue(any("price.current: expected" in e for e in errors))

    def test_unexpected_field_is_rejected_because_the_contract_is_closed(self) -> None:
        # An unknown key means the producer and the scorers disagree about the
        # contract. Silently ignoring it is how drift starts.
        self.document["identity"]["beta"] = 1.2
        self.assertIn(
            "identity.beta: unexpected field (the contract is closed)",
            validate_snapshot(self.document),
        )

    def test_non_nullable_field_rejects_null(self) -> None:
        self.document["volatility"]["is_proxy"] = None
        self.assertIn("volatility.is_proxy: must not be null", validate_snapshot(self.document))

    def test_nullable_field_accepts_null(self) -> None:
        self.document["identity"]["market_cap"] = None
        self.assertEqual(validate_snapshot(self.document), ())

    def test_malformed_date_is_rejected(self) -> None:
        self.document["earnings"]["next_earnings_date"] = "10/08/2026"
        errors = validate_snapshot(self.document)
        self.assertTrue(any("earnings.next_earnings_date" in e for e in errors))

    def test_lowercase_ticker_is_rejected(self) -> None:
        self.document["ticker"] = "f"
        self.assertIn("ticker: must be uppercase", validate_snapshot(self.document))

    def test_schema_version_mismatch_is_reported(self) -> None:
        self.document["schema_version"] = "0.9"
        errors = validate_snapshot(self.document)
        self.assertTrue(any("schema_version" in e for e in errors))
        self.assertEqual(SCHEMA_VERSION, "1.0")

    def test_integer_is_accepted_where_a_float_is_expected(self) -> None:
        self.document["price"]["current"] = 12
        self.assertEqual(validate_snapshot(self.document), ())

    def test_bool_is_not_accepted_as_a_number(self) -> None:
        self.document["identity"]["market_cap"] = True
        errors = validate_snapshot(self.document)
        self.assertTrue(any("identity.market_cap: expected" in e for e in errors))

    def test_all_violations_are_collected_in_one_pass(self) -> None:
        del self.document["fundamentals"]["net_income_ttm"]
        self.document["ticker"] = "f"
        self.document["price"]["current"] = "cheap"
        self.assertGreaterEqual(len(validate_snapshot(self.document)), 3)

    def test_assert_valid_raises_listing_every_violation(self) -> None:
        self.document["ticker"] = "f"
        del self.document["earnings"]
        with self.assertRaises(SnapshotSchemaError) as caught:
            assert_valid_snapshot(self.document)
        message = str(caught.exception)
        self.assertIn("ticker: must be uppercase", message)
        self.assertIn("earnings: required object is missing", message)

    def test_assert_valid_is_quiet_on_the_golden_file(self) -> None:
        assert_valid_snapshot(self.document)

    def test_validation_is_pure(self) -> None:
        before = json.dumps(self.document, sort_keys=True)
        validate_snapshot(self.document)
        self.assertEqual(json.dumps(self.document, sort_keys=True), before)

    def test_non_object_document_is_rejected(self) -> None:
        self.assertTrue(validate_snapshot(["not", "an", "object"]))


if __name__ == "__main__":
    unittest.main()
