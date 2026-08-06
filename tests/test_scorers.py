"""Golden-file tests for the Layer 1 hard gates.

Three golden snapshots carry the cases:

- `2026-08-15_F.json`    -- compliant equity; every gate should pass.
- `2026-08-15_SPY-minimal.json` -- ETF with null fundamentals. ST-SEL-08 says
  this is a valid candidate, so ST-SEL-01 must return NOT_APPLICABLE, never FAIL.
- `2026-08-15_APLD-highvol.json` -- the Source Brief's own counterexample:
  negative earnings and ~135% volatility. ST-SEL-01 and ST-SEL-10 both reject it.

Every gate is also exercised against a mutated golden, so a rule that silently
stops firing fails a test rather than quietly passing every name.

Offline: no network, no clock, no provider.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from wheel.scorers import (
    IV_PROXY_NOTE,
    RuleKind,
    SelectionThresholds,
    Verdict,
    clears_hard_gates,
    disqualified_by,
    evaluate_hard_gates,
    evaluate_st_sel_01,
    evaluate_st_sel_04,
    evaluate_st_sel_10,
    has_company_fundamentals,
    selection_thresholds_from_config,
    unevaluated,
)
from wheel.snapshot_schema import validate_snapshot

GOLDEN_DIR = Path(__file__).parent / "golden"
EQUITY = GOLDEN_DIR / "2026-08-15_F.json"
ETF = GOLDEN_DIR / "2026-08-15_SPY-minimal.json"
HIGH_VOL = GOLDEN_DIR / "2026-08-15_APLD-highvol.json"

# Mirrors config.yaml; kept literal so a config edit cannot silently move a
# threshold out from under these expectations.
THRESHOLDS = SelectionThresholds(
    min_ttm_net_income=0.0,
    min_operating_cash_flow=0.0,
    min_price=10.0,
    max_implied_volatility=0.50,
)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


class GoldenFixtureTests(unittest.TestCase):
    """The fixtures must satisfy the Layer 0 contract before they prove anything."""

    def test_every_golden_snapshot_is_contract_valid(self) -> None:
        for path in (EQUITY, ETF, HIGH_VOL):
            with self.subTest(snapshot=path.name):
                self.assertEqual(validate_snapshot(load(path)), ())


class ThresholdConfigTests(unittest.TestCase):
    def test_thresholds_load_from_config_shape(self) -> None:
        config = {
            "thresholds": {
                "profitability": {
                    "min_ttm_net_income": 0,
                    "min_operating_cash_flow": 0,
                },
                "price": {"min_usd": 10.0},
                "iv_proxy": {"high_vol_penalty_above": 0.50},
            }
        }
        self.assertEqual(selection_thresholds_from_config(config), THRESHOLDS)


class InstrumentClassTests(unittest.TestCase):
    """ST-SEL-08 -- ETFs are valid candidates, so the branch must be right."""

    def test_equity_has_company_fundamentals(self) -> None:
        self.assertTrue(has_company_fundamentals(load(EQUITY)))

    def test_etf_has_no_company_fundamentals(self) -> None:
        self.assertFalse(has_company_fundamentals(load(ETF)))

    def test_quote_type_is_matched_case_insensitively(self) -> None:
        document = load(ETF)
        document["identity"]["quote_type"] = "etf"
        self.assertFalse(has_company_fundamentals(document))

    def test_unknown_quote_type_is_treated_as_an_equity(self) -> None:
        # Conservative: an unclassified name keeps the fundamental gates
        # applying rather than waiving them.
        document = load(EQUITY)
        document["identity"]["quote_type"] = None
        self.assertTrue(has_company_fundamentals(document))


class StSel01ProfitabilityTests(unittest.TestCase):
    def test_profitable_equity_passes(self) -> None:
        result = evaluate_st_sel_01(load(EQUITY), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.rule_id, "ST-SEL-01")
        self.assertEqual(result.kind, RuleKind.GATE)
        self.assertFalse(result.disqualifying)

    def test_etf_is_not_applicable_not_a_failure(self) -> None:
        """The ST-SEL-08 branch: null fundamentals on an ETF is not a FAIL."""

        result = evaluate_st_sel_01(load(ETF), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.NOT_APPLICABLE)
        self.assertFalse(result.disqualifying)
        self.assertIn("ST-SEL-08", result.reason)

    def test_negative_earnings_fail(self) -> None:
        result = evaluate_st_sel_01(load(HIGH_VOL), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertTrue(result.disqualifying)
        self.assertIn("net income", result.reason)
        self.assertIn("operating cash flow", result.reason)

    def test_negative_cash_flow_alone_fails(self) -> None:
        document = load(EQUITY)
        document["fundamentals"]["operating_cash_flow_ttm"] = -1
        result = evaluate_st_sel_01(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertIn("operating cash flow", result.reason)
        self.assertNotIn("net income", result.reason)

    def test_exactly_zero_is_not_positive(self) -> None:
        document = load(EQUITY)
        document["fundamentals"]["net_income_ttm"] = 0
        self.assertEqual(
            evaluate_st_sel_01(document, THRESHOLDS).verdict, Verdict.FAIL
        )

    def test_missing_fundamentals_on_an_equity_cannot_be_evaluated(self) -> None:
        # Distinct from the ETF case: an equity with null net income is a data
        # gap, not an instrument class.
        document = load(EQUITY)
        document["fundamentals"]["net_income_ttm"] = None
        result = evaluate_st_sel_01(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.CANNOT_EVALUATE)
        self.assertIn("net_income_ttm", result.reason)
        self.assertFalse(result.disqualifying)

    def test_metrics_carry_the_observed_inputs(self) -> None:
        result = evaluate_st_sel_01(load(EQUITY), THRESHOLDS)
        self.assertEqual(result.metrics["net_income_ttm"], 5900000000)
        self.assertEqual(result.metrics["operating_cash_flow_ttm"], 15400000000)


class StSel04PriceFloorTests(unittest.TestCase):
    def test_price_above_floor_passes(self) -> None:
        result = evaluate_st_sel_04(load(EQUITY), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.rule_id, "ST-SEL-04")

    def test_floor_applies_to_etfs_too(self) -> None:
        # The floor is a property of the price, not the issuer -- an ETF is not
        # waived from it the way it is waived from ST-SEL-01.
        result = evaluate_st_sel_04(load(ETF), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)

    def test_sub_ten_fails(self) -> None:
        document = load(EQUITY)
        document["price"]["current"] = 9.99
        result = evaluate_st_sel_04(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertTrue(result.disqualifying)

    def test_exactly_ten_passes(self) -> None:
        document = load(EQUITY)
        document["price"]["current"] = 10.0
        self.assertEqual(
            evaluate_st_sel_04(document, THRESHOLDS).verdict, Verdict.PASS
        )

    def test_missing_price_cannot_be_evaluated(self) -> None:
        document = load(EQUITY)
        document["price"]["current"] = None
        self.assertEqual(
            evaluate_st_sel_04(document, THRESHOLDS).verdict, Verdict.CANNOT_EVALUATE
        )


class StSel10VolatilityTests(unittest.TestCase):
    def test_normal_volatility_passes_on_the_proxy(self) -> None:
        result = evaluate_st_sel_10(load(EQUITY), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.rule_id, "ST-SEL-10")

    def test_high_volatility_disqualifies(self) -> None:
        result = evaluate_st_sel_10(load(HIGH_VOL), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertTrue(result.disqualifying)

    def test_proxy_use_is_declared_on_every_result(self) -> None:
        """A name rejected on a proxy must be reported as rejected on a proxy."""

        for path in (EQUITY, HIGH_VOL):
            with self.subTest(snapshot=path.name):
                result = evaluate_st_sel_10(load(path), THRESHOLDS)
                self.assertTrue(result.is_approximation)
                self.assertEqual(result.approximation_note, IV_PROXY_NOTE)
                self.assertIn("proxy", result.reason)

    def test_true_iv_is_preferred_over_the_proxy_when_present(self) -> None:
        document = load(HIGH_VOL)
        # Component B fills this one day; the proxy must then step aside even
        # when the two disagree about the verdict.
        document["volatility"]["implied_volatility"] = 0.31
        result = evaluate_st_sel_10(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertFalse(result.is_approximation)
        self.assertIsNone(result.approximation_note)
        self.assertEqual(result.metrics["measure_used"], "implied volatility")

    def test_boundary_at_the_ceiling_passes(self) -> None:
        document = load(EQUITY)
        document["volatility"]["realized_vol_30d"] = 0.50
        self.assertEqual(
            evaluate_st_sel_10(document, THRESHOLDS).verdict, Verdict.PASS
        )

    def test_just_above_the_ceiling_fails(self) -> None:
        document = load(EQUITY)
        document["volatility"]["realized_vol_30d"] = 0.5001
        self.assertEqual(
            evaluate_st_sel_10(document, THRESHOLDS).verdict, Verdict.FAIL
        )

    def test_no_volatility_at_all_cannot_be_evaluated(self) -> None:
        document = load(EQUITY)
        document["volatility"]["realized_vol_30d"] = None
        document["volatility"]["implied_volatility"] = None
        result = evaluate_st_sel_10(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.CANNOT_EVALUATE)
        self.assertFalse(result.disqualifying)


class HardGateSuiteTests(unittest.TestCase):
    def test_compliant_equity_clears_every_gate(self) -> None:
        results = evaluate_hard_gates(load(EQUITY), THRESHOLDS)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.verdict is Verdict.PASS for r in results))
        self.assertTrue(clears_hard_gates(results))

    def test_etf_clears_the_gates_with_one_not_applicable(self) -> None:
        """ST-SEL-08 end to end: an ETF is a candidate, not a rejection."""

        results = evaluate_hard_gates(load(ETF), THRESHOLDS)
        verdicts = {r.rule_id: r.verdict for r in results}
        self.assertEqual(verdicts["ST-SEL-01"], Verdict.NOT_APPLICABLE)
        self.assertEqual(verdicts["ST-SEL-04"], Verdict.PASS)
        self.assertEqual(verdicts["ST-SEL-10"], Verdict.PASS)
        self.assertTrue(clears_hard_gates(results))
        self.assertEqual(disqualified_by(results), ())

    def test_high_vol_name_is_rejected_by_two_rules(self) -> None:
        results = evaluate_hard_gates(load(HIGH_VOL), THRESHOLDS)
        self.assertFalse(clears_hard_gates(results))
        self.assertEqual(
            [r.rule_id for r in disqualified_by(results)],
            ["ST-SEL-01", "ST-SEL-10"],
        )

    def test_cannot_evaluate_fails_closed(self) -> None:
        """A data gap must never read as a pass."""

        document = load(EQUITY)
        document["price"]["current"] = None
        results = evaluate_hard_gates(document, THRESHOLDS)
        self.assertFalse(clears_hard_gates(results))
        self.assertEqual(disqualified_by(results), ())
        self.assertEqual([r.rule_id for r in unevaluated(results)], ["ST-SEL-04"])

    def test_every_result_carries_a_rule_id_and_reason(self) -> None:
        for path in (EQUITY, ETF, HIGH_VOL):
            for result in evaluate_hard_gates(load(path), THRESHOLDS):
                with self.subTest(snapshot=path.name, rule=result.rule_id):
                    self.assertTrue(result.rule_id.startswith("ST-SEL-"))
                    self.assertTrue(result.reason.strip())
                    self.assertIs(result.kind, RuleKind.GATE)

    def test_scoring_does_not_mutate_the_snapshot(self) -> None:
        document = load(EQUITY)
        before = copy.deepcopy(document)
        evaluate_hard_gates(document, THRESHOLDS)
        self.assertEqual(document, before)

    def test_gates_are_deterministic(self) -> None:
        document = load(EQUITY)
        self.assertEqual(
            evaluate_hard_gates(document, THRESHOLDS),
            evaluate_hard_gates(document, THRESHOLDS),
        )

    def test_unvalidated_document_reports_rather_than_raises(self) -> None:
        # A scorer handed a malformed document must degrade to CANNOT_EVALUATE;
        # the schema validator is what enforces shape.
        results = evaluate_hard_gates({"ticker": "X"}, THRESHOLDS)
        self.assertTrue(
            all(r.verdict is Verdict.CANNOT_EVALUATE for r in results)
        )


if __name__ == "__main__":
    unittest.main()
