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
    NEAR_HIGH_FLAG_FRACTION,
    ST_SEL_05_NOTE,
    evaluate_al_sel_04,
    evaluate_al_sel_06,
    evaluate_al_siz_03,
    evaluate_al_siz_04,
    evaluate_cross_candidate_rules,
    evaluate_single_ticker_rules,
    evaluate_st_ent_05,
    evaluate_st_sel_02,
    evaluate_st_sel_03,
    evaluate_st_sel_05,
    evaluate_st_sel_06,
    evaluate_st_sel_08,
    evaluate_st_sel_12,
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
from wheel.snapshot_schema import RULE_FIELD_MAP, validate_snapshot

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
    max_price=50.0,
    max_mean_rating=2.5,
    max_single_day_move=0.15,
    earnings_flag_days=45,
)
FLAG_VOL = GOLDEN_DIR / "2026-08-15_MARA-flagvol.json"


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
                "price": {"min_usd": 10.0, "max_usd": 50.0},
                "analyst": {"max_mean_rating": 2.5},
                "stability": {"max_single_day_move": 0.15},
                "earnings": {"flag_within_days": 45},
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
        document["volatility"]["implied_volatility"] = 0.31  # below the flag line
        result = evaluate_st_sel_10(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertFalse(result.is_approximation)
        self.assertIsNone(result.approximation_note)
        self.assertEqual(result.metrics["measure_used"], "implied volatility")

    def test_boundary_at_the_warning_line_passes(self) -> None:
        document = load(EQUITY)
        document["volatility"]["realized_vol_30d"] = 0.50
        self.assertEqual(
            evaluate_st_sel_10(document, THRESHOLDS).verdict, Verdict.PASS
        )

    def test_just_above_the_warning_line_flags_rather_than_fails(self) -> None:
        document = load(EQUITY)
        document["volatility"]["realized_vol_30d"] = 0.5001
        result = evaluate_st_sel_10(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FLAG)
        self.assertEqual(result.kind, RuleKind.FLAG)
        self.assertFalse(result.disqualifying)

    def test_flag_zone_golden_warns_without_disqualifying(self) -> None:
        result = evaluate_st_sel_10(load(FLAG_VOL), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FLAG)
        self.assertFalse(result.disqualifying)
        self.assertIn("elevated but not disqualifying", result.reason)

    def test_boundary_at_the_disqualifying_ceiling_only_flags(self) -> None:
        document = load(EQUITY)
        document["volatility"]["realized_vol_30d"] = 0.80
        self.assertEqual(
            evaluate_st_sel_10(document, THRESHOLDS).verdict, Verdict.FLAG
        )

    def test_just_above_the_disqualifying_ceiling_fails(self) -> None:
        document = load(EQUITY)
        document["volatility"]["realized_vol_30d"] = 0.8001
        result = evaluate_st_sel_10(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertTrue(result.disqualifying)

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
        self.assertEqual(len(results), 4)
        self.assertTrue(all(r.verdict is Verdict.PASS for r in results))
        self.assertTrue(clears_hard_gates(results))

    def test_etf_clears_the_gates_with_one_not_applicable(self) -> None:
        """ST-SEL-08 end to end: an ETF is a candidate, not a rejection."""

        results = evaluate_hard_gates(load(ETF), THRESHOLDS)
        verdicts = {r.rule_id: r.verdict for r in results}
        self.assertEqual(verdicts["AL-SEL-04"], Verdict.PASS)
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
            # AL-SEL-04 joins: APLD has no thesis note either.
            ["ST-SEL-01", "ST-SEL-10", "AL-SEL-04"],
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
                    self.assertRegex(result.rule_id, r"^(ST|AL)-[A-Z]{3}-\d{2}$")
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


# ---------------------------------------------------------------------------
# Soft scores and flags
# ---------------------------------------------------------------------------


class SoftRuleTests(unittest.TestCase):
    """One rule per method; ETF branch asserted wherever the rule has one."""

    def test_st_sel_08_classifies_an_equity(self) -> None:
        result = evaluate_st_sel_08(load(EQUITY))
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertTrue(result.metrics["has_company_fundamentals"])

    def test_st_sel_08_classifies_an_etf_as_valid_not_rejected(self) -> None:
        result = evaluate_st_sel_08(load(ETF))
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertFalse(result.metrics["has_company_fundamentals"])
        self.assertIn("valid candidate, not a rejection", result.reason)
        self.assertFalse(result.disqualifying)

    def test_st_sel_08_never_disqualifies(self) -> None:
        # It classifies; it does not judge.
        for path in (EQUITY, ETF, HIGH_VOL, FLAG_VOL):
            with self.subTest(snapshot=path.name):
                self.assertFalse(evaluate_st_sel_08(load(path)).disqualifying)

    def test_st_sel_02_bullish_consensus_passes(self) -> None:
        result = evaluate_st_sel_02(load(EQUITY), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.kind, RuleKind.SCORE)

    def test_st_sel_02_bearish_consensus_fails_without_disqualifying(self) -> None:
        document = load(EQUITY)
        document["analyst"]["recommendation_mean"] = 3.4
        result = evaluate_st_sel_02(document, THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FAIL)
        # A score, not a gate: a weak consensus never rejects on its own.
        self.assertFalse(result.disqualifying)

    def test_st_sel_02_etf_is_not_applicable(self) -> None:
        result = evaluate_st_sel_02(load(ETF), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.NOT_APPLICABLE)
        self.assertIn("ST-SEL-08", result.reason)

    def test_st_sel_03_price_inside_band_passes(self) -> None:
        self.assertEqual(
            evaluate_st_sel_03(load(EQUITY), THRESHOLDS).verdict, Verdict.PASS
        )

    def test_st_sel_03_price_above_band_fails(self) -> None:
        # SPY at $618 is far outside the configured band.
        result = evaluate_st_sel_03(load(ETF), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertFalse(result.disqualifying)

    def test_st_sel_03_names_its_interim_status(self) -> None:
        # AL-SEL-02 supersedes the fixed band but needs account net_liq.
        self.assertIn("AL-SEL-02", evaluate_st_sel_03(load(EQUITY), THRESHOLDS).reason)

    def test_st_sel_05_stable_chart_passes(self) -> None:
        result = evaluate_st_sel_05(load(EQUITY), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)

    def test_st_sel_05_violent_move_fails(self) -> None:
        # APLD's largest single-day move is 29%, well past the 15% limit.
        self.assertEqual(
            evaluate_st_sel_05(load(HIGH_VOL), THRESHOLDS).verdict, Verdict.FAIL
        )

    def test_st_sel_05_always_declares_its_approximation(self) -> None:
        """Carried the same way as ST-SEL-10, and for a stronger reason."""

        for path in (EQUITY, HIGH_VOL, FLAG_VOL):
            with self.subTest(snapshot=path.name):
                result = evaluate_st_sel_05(load(path), THRESHOLDS)
                self.assertTrue(result.is_approximation)
                self.assertEqual(result.approximation_note, ST_SEL_05_NOTE)

    def test_st_sel_05_note_admits_the_undetectable_risk(self) -> None:
        # The rule names social-media-driven moves; no price series sees them.
        self.assertIn("social media", ST_SEL_05_NOTE)

    def test_st_sel_05_missing_data_cannot_be_evaluated(self) -> None:
        document = load(EQUITY)
        document["stability"]["max_single_day_move_1y"] = None
        self.assertEqual(
            evaluate_st_sel_05(document, THRESHOLDS).verdict, Verdict.CANNOT_EVALUATE
        )

    def test_st_sel_06_payer_passes(self) -> None:
        self.assertEqual(evaluate_st_sel_06(load(EQUITY)).verdict, Verdict.PASS)

    def test_st_sel_06_non_payer_is_never_disqualifying(self) -> None:
        # "Preferred, not required" -- a non-payer stays a valid candidate.
        result = evaluate_st_sel_06(load(HIGH_VOL))
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertFalse(result.disqualifying)
        self.assertIn("preferred, not required", result.reason)

    def test_st_sel_12_far_from_high_passes(self) -> None:
        result = evaluate_st_sel_12(load(EQUITY), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.PASS)

    def test_st_sel_12_near_high_flags(self) -> None:
        # MARA sits 3.2% below its two-year high, inside the 10% band.
        result = evaluate_st_sel_12(load(FLAG_VOL), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FLAG)
        self.assertEqual(result.kind, RuleKind.FLAG)
        self.assertFalse(result.disqualifying)

    def test_st_sel_12_threshold_is_a_named_constant(self) -> None:
        self.assertEqual(NEAR_HIGH_FLAG_FRACTION, 0.10)
        self.assertEqual(THRESHOLDS.near_high_fraction, NEAR_HIGH_FLAG_FRACTION)

    def test_st_sel_12_boundary_at_exactly_ten_percent_flags(self) -> None:
        document = load(EQUITY)
        document["chart_position"]["pct_below_two_year_high"] = 0.10
        self.assertEqual(
            evaluate_st_sel_12(document, THRESHOLDS).verdict, Verdict.FLAG
        )

    def test_st_ent_05_distant_earnings_pass(self) -> None:
        # F reports in 54 days, beyond the 45-day window.
        self.assertEqual(
            evaluate_st_ent_05(load(EQUITY), THRESHOLDS).verdict, Verdict.PASS
        )

    def test_st_ent_05_imminent_earnings_flag(self) -> None:
        result = evaluate_st_ent_05(load(FLAG_VOL), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.FLAG)
        self.assertFalse(result.disqualifying)
        self.assertIn("do not open across it", result.reason)

    def test_st_ent_05_etf_has_no_earnings_event(self) -> None:
        # Absence of the event, not absence of a measurement.
        result = evaluate_st_ent_05(load(ETF), THRESHOLDS)
        self.assertEqual(result.verdict, Verdict.NOT_APPLICABLE)

    def test_st_ent_05_equity_without_a_date_cannot_be_evaluated(self) -> None:
        document = load(EQUITY)
        document["earnings"]["days_to_earnings"] = None
        self.assertEqual(
            evaluate_st_ent_05(document, THRESHOLDS).verdict, Verdict.CANNOT_EVALUATE
        )

    def test_al_sel_04_thesis_present_passes(self) -> None:
        result = evaluate_al_sel_04(load(EQUITY))
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.kind, RuleKind.GATE)

    def test_al_sel_04_missing_thesis_disqualifies(self) -> None:
        result = evaluate_al_sel_04(load(HIGH_VOL))
        self.assertEqual(result.verdict, Verdict.FAIL)
        self.assertTrue(result.disqualifying)
        self.assertIn("not tradeable", result.reason)

    def test_al_sel_04_unanswered_is_not_the_same_as_false(self) -> None:
        document = load(EQUITY)
        document["operator_gates"]["thesis_note_exists"] = None
        result = evaluate_al_sel_04(document)
        self.assertEqual(result.verdict, Verdict.CANNOT_EVALUATE)
        self.assertFalse(result.disqualifying)

    def test_al_sel_06_large_cap_passes(self) -> None:
        self.assertEqual(
            evaluate_al_sel_06(load(EQUITY), THRESHOLDS).verdict, Verdict.PASS
        )

    def test_al_sel_06_sub_mid_cap_fails(self) -> None:
        document = load(EQUITY)
        document["identity"]["market_cap"] = 900_000_000
        self.assertEqual(
            evaluate_al_sel_06(document, THRESHOLDS).verdict, Verdict.FAIL
        )

    def test_al_sel_06_etf_is_not_applicable(self) -> None:
        self.assertEqual(
            evaluate_al_sel_06(load(ETF), THRESHOLDS).verdict, Verdict.NOT_APPLICABLE
        )

    def test_al_sel_06_is_independent_of_price(self) -> None:
        # The rule exists so a screen does not reject a sound $15 large-cap.
        document = load(EQUITY)
        document["price"]["current"] = 15.0
        self.assertEqual(
            evaluate_al_sel_06(document, THRESHOLDS).verdict, Verdict.PASS
        )


class CrossCandidateRuleTests(unittest.TestCase):
    """AL-SIZ-03/04 read the whole candidate set, so their interface differs."""

    def setUp(self) -> None:
        self.candidates = [load(p) for p in (EQUITY, ETF, HIGH_VOL, FLAG_VOL)]

    def test_al_siz_03_no_repeat_industry_passes(self) -> None:
        result = evaluate_al_siz_03(self.candidates)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.kind, RuleKind.FLAG)

    def test_al_siz_03_repeated_industry_flags_without_blocking(self) -> None:
        duplicate = load(FLAG_VOL)
        duplicate["ticker"] = "RIOT"
        duplicate["identity"]["industry"] = "Capital Markets"
        result = evaluate_al_siz_03(self.candidates + [duplicate])
        self.assertEqual(result.verdict, Verdict.FLAG)
        self.assertFalse(result.disqualifying)
        self.assertIn("warning, not a block", result.reason)
        self.assertIn("MARA", result.reason)
        self.assertIn("RIOT", result.reason)

    def test_al_siz_03_null_industry_is_skipped_not_grouped(self) -> None:
        # The ETF has a null industry; two nulls must not read as a cluster.
        second_etf = load(ETF)
        second_etf["ticker"] = "QQQ"
        result = evaluate_al_siz_03([load(ETF), second_etf])
        self.assertEqual(result.verdict, Verdict.PASS)

    def test_al_siz_04_no_clustering_passes(self) -> None:
        result = evaluate_al_siz_04(self.candidates)
        self.assertEqual(result.verdict, Verdict.PASS)

    def test_al_siz_04_same_week_flags(self) -> None:
        same_week = load(EQUITY)
        same_week["ticker"] = "GM"
        same_week["earnings"]["earnings_week"] = "2026-W35"
        result = evaluate_al_siz_04(self.candidates + [same_week])
        self.assertEqual(result.verdict, Verdict.FLAG)
        self.assertFalse(result.disqualifying)
        self.assertIn("2026-W35", result.reason)
        self.assertIn("display, not a constraint", result.reason)

    def test_al_siz_04_catches_clustering_across_unrelated_sectors(self) -> None:
        """The correlation the sector view misses entirely."""

        a, b = load(EQUITY), load(HIGH_VOL)
        a["earnings"]["earnings_week"] = b["earnings"]["earnings_week"] = "2026-W44"
        self.assertNotEqual(a["identity"]["sector"], b["identity"]["sector"])
        self.assertEqual(evaluate_al_siz_04([a, b]).verdict, Verdict.FLAG)

    def test_cross_candidate_rules_need_two_names_to_mean_anything(self) -> None:
        for result in evaluate_cross_candidate_rules([load(EQUITY)]):
            with self.subTest(rule=result.rule_id):
                self.assertEqual(result.verdict, Verdict.PASS)

    def test_empty_candidate_set_cannot_be_evaluated(self) -> None:
        for result in evaluate_cross_candidate_rules([]):
            with self.subTest(rule=result.rule_id):
                self.assertEqual(result.verdict, Verdict.CANNOT_EVALUATE)

    def test_cross_candidate_rules_do_not_mutate_the_set(self) -> None:
        before = copy.deepcopy(self.candidates)
        evaluate_cross_candidate_rules(self.candidates)
        self.assertEqual(self.candidates, before)


class FullRuleSetTests(unittest.TestCase):
    def test_every_single_ticker_rule_runs(self) -> None:
        results = evaluate_single_ticker_rules(load(EQUITY), THRESHOLDS)
        self.assertEqual(
            [r.rule_id for r in results],
            [
                "ST-SEL-01", "ST-SEL-04", "ST-SEL-10", "AL-SEL-04",
                "ST-SEL-08", "ST-SEL-02", "ST-SEL-03", "ST-SEL-05", "ST-SEL-06",
                "ST-SEL-12", "ST-ENT-05", "AL-SEL-06",
            ],
        )

    def test_all_thirteen_served_rules_are_implemented(self) -> None:
        """Every rule the snapshot contract claims to serve has a scorer."""

        implemented = {
            r.rule_id for r in evaluate_single_ticker_rules(load(EQUITY), THRESHOLDS)
        } | {r.rule_id for r in evaluate_cross_candidate_rules([load(EQUITY)])}
        self.assertEqual(set(RULE_FIELD_MAP) - implemented, set())

    def test_etf_is_a_viable_candidate_end_to_end(self) -> None:
        """ST-SEL-08 across the whole rule set: no NOT_APPLICABLE disqualifies."""

        results = evaluate_single_ticker_rules(load(ETF), THRESHOLDS)
        not_applicable = [
            r.rule_id for r in results if r.verdict is Verdict.NOT_APPLICABLE
        ]
        self.assertEqual(
            sorted(not_applicable), ["AL-SEL-06", "ST-ENT-05", "ST-SEL-01", "ST-SEL-02"]
        )
        self.assertEqual(disqualified_by(results), ())

    def test_scoring_the_full_set_does_not_mutate_the_snapshot(self) -> None:
        document = load(FLAG_VOL)
        before = copy.deepcopy(document)
        evaluate_single_ticker_rules(document, THRESHOLDS)
        self.assertEqual(document, before)
