"""Integration-level regression baseline over REAL snapshots (§5.8, §4.3).

`tests/golden/live/` holds actual Layer 0 output from the 2026-08-06 run.
`expected_scores.json` freezes every scorer verdict, reason, metric, composite
and classification those snapshots produced. This test recomputes and compares
byte-for-byte, so any change to a Layer 1 scorer that shifts a verdict, a
reason string, or a metric fails here.

Per AGENTS.md §4.3 that is the intended behavior: a commit that changes
scoring logic regenerates this baseline IN THE SAME COMMIT, and the diff of
expected_scores.json is the review artifact. Regenerate with:

    PYTHONPATH=src python tests/test_golden_baseline.py --regenerate

The hand-built goldens in tests/golden/ are unit-test fixtures with chosen
edge cases; they are a different tool and stay untouched.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from wheel.scorers import (
    RuleResult,
    SelectionThresholds,
    evaluate_cross_candidate_rules,
    evaluate_single_ticker_rules,
)
from wheel.snapshot_schema import validate_snapshot
from wheel.week_report import classify, composite_score

LIVE_DIR = Path(__file__).parent / "golden" / "live"
EXPECTED_PATH = LIVE_DIR / "expected_scores.json"

# Mirrors config/example.yaml, literal on purpose: a config edit must not
# silently move the baseline.
THRESHOLDS = SelectionThresholds(
    min_ttm_net_income=0.0,
    min_operating_cash_flow=0.0,
    min_price=10.0,
    max_price=50.0,
    max_mean_rating=2.5,
    max_single_day_move=0.15,
    earnings_flag_days=45,
)
WEIGHTS = {
    "volatility": 0.20,
    "chart_position": 0.20,
    "cash_flow_strength": 0.20,
    "dividend": 0.20,
    "analyst_strength": 0.20,
}


def snapshot_paths() -> list[Path]:
    return sorted(
        p for p in LIVE_DIR.glob("*.json") if p.name != EXPECTED_PATH.name
    )


def result_to_dict(result: RuleResult) -> dict:
    return {
        "rule_id": result.rule_id,
        "kind": result.kind.value,
        "verdict": result.verdict.value,
        "reason": result.reason,
        "metrics": dict(result.metrics),
        "is_approximation": result.is_approximation,
        "score": result.score,
    }


def compute_baseline() -> dict:
    documents = [json.loads(p.read_text()) for p in snapshot_paths()]
    baseline: dict = {}
    for document in documents:
        results = evaluate_single_ticker_rules(document, THRESHOLDS)
        baseline[document["ticker"]] = {
            "snapshot": f"{document['snapshot_date']}_{document['ticker']}.json",
            "classification": classify(results),
            "composite": composite_score(results, WEIGHTS),
            "results": [result_to_dict(r) for r in results],
        }
    baseline["_cross_candidate"] = [
        result_to_dict(r) for r in evaluate_cross_candidate_rules(documents)
    ]
    return baseline


def regenerate() -> None:
    EXPECTED_PATH.write_text(
        json.dumps(compute_baseline(), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(f"regenerated {EXPECTED_PATH}")


class LiveGoldenBaselineTests(unittest.TestCase):
    def test_live_goldens_exist(self) -> None:
        self.assertEqual(len(snapshot_paths()), 5)

    def test_live_goldens_satisfy_the_contract(self) -> None:
        for path in snapshot_paths():
            with self.subTest(snapshot=path.name):
                self.assertEqual(
                    validate_snapshot(json.loads(path.read_text())), ()
                )

    def test_scorer_output_matches_the_frozen_baseline(self) -> None:
        """The §4.3 gate: scorer changes regenerate this file, same commit."""

        self.assertTrue(
            EXPECTED_PATH.is_file(),
            "expected_scores.json is missing -- run --regenerate",
        )
        expected = json.loads(EXPECTED_PATH.read_text())
        actual = json.loads(
            json.dumps(compute_baseline(), sort_keys=True)  # normalize types
        )
        self.assertEqual(actual, expected)

    def test_baseline_records_the_live_run_outcome(self) -> None:
        """Pins the 2026-08-06 headline results so the file stays honest."""

        expected = json.loads(EXPECTED_PATH.read_text())
        # ST-SEL-01 split: F is NI-negative but OCF-positive, so it flags
        # rather than failing, and clears fitness into the thesis tier.
        self.assertEqual(expected["F"]["classification"], "thesis_required")
        self.assertEqual(expected["MARA"]["classification"], "rejected")
        self.assertEqual(expected["T"]["classification"], "thesis_required")
        self.assertEqual(expected["KO"]["classification"], "thesis_required")
        self.assertEqual(expected["SPY"]["classification"], "thesis_required")

        # Continuous scoring: the four cleared names used to sit on 100 / 100 /
        # 90 / 88.9 with the top two exactly tied. They now separate, and T --
        # 21.5B net income on 39.9B operating cash flow, 4.81% yield, 16.6%
        # below its two-year high -- leads on merit rather than on the alphabet.
        composites = {
            ticker: expected[ticker]["composite"]
            for ticker in ("T", "F", "KO", "SPY")
        }
        self.assertEqual(len(set(composites.values())), 4)
        self.assertEqual(
            list(composites), sorted(composites, key=composites.get, reverse=True)
        )
        self.assertAlmostEqual(composites["T"], 74.329, places=3)

        # AL-SIZ-04 caught F/KO/T reporting in the same week on real data.
        cross = {r["rule_id"]: r for r in expected["_cross_candidate"]}
        self.assertEqual(cross["AL-SIZ-04"]["verdict"], "flag")
        self.assertIn("2026-W43", cross["AL-SIZ-04"]["reason"])


if __name__ == "__main__":
    if "--regenerate" in sys.argv:
        regenerate()
        sys.exit(0)
    unittest.main()
