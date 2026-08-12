"""End-to-end /wheel-screen test against golden snapshots. No network.

Builds a temporary WheelOps sibling, copies the goldens into snapshots/, and
runs the Layer 1 phase exactly as `commands/wheel-screen --score-only` would.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from wheel.screen import run_screen
from wheel.universe import Stage1Survivor
from wheel_mcp.acquire import deep_snapshot

GOLDEN_DIR = Path(__file__).parent / "golden"
RUN_DATE = date(2026, 8, 15)


def make_config(wheelops: Path) -> dict:
    return {
        "paths": {"wheelops": str(wheelops)},
        "universe": {
            "source": "us_equities_with_options",
            "price_floor": 10,
            "market_cap_floor": 2_000_000_000,
            "include": [],
            "exclude": [],
        },
        "account": {"net_liq": 12000, "per_name_cap": 0.25},
        "weights": {
            "volatility": 0.20,
            "chart_position": 0.20,
            "cash_flow_strength": 0.20,
            "dividend": 0.20,
            "analyst_strength": 0.20,
        },
        "thresholds": {
            "profitability": {
                "min_ttm_net_income": 0,
                "min_operating_cash_flow": 0,
            },
            "price": {"min_usd": 10.0, "max_usd": 50.0},
            "analyst": {"max_mean_rating": 2.5},
            "stability": {"max_single_day_move": 0.15},
            "earnings": {"flag_within_days": 45},
        },
    }


class WheelScreenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.wheelops = Path(self._directory.name)
        snapshots = self.wheelops / "snapshots"
        snapshots.mkdir()
        for golden, target in (
            ("2026-08-15_F.json", "2026-08-15_F.json"),
            ("2026-08-15_SPY-minimal.json", "2026-08-15_SPY.json"),
            ("2026-08-15_APLD-highvol.json", "2026-08-15_APLD.json"),
            ("2026-08-15_MARA-flagvol.json", "2026-08-15_MARA.json"),
        ):
            shutil.copy(GOLDEN_DIR / golden, snapshots / target)
        self.addCleanup(self._directory.cleanup)

    def test_writes_the_week_file_with_all_five_sections(self) -> None:
        path, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertEqual(path, self.wheelops / "weeks" / "2026-08-15.md")
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(encoding="utf-8"), markdown)
        for heading in (
            "# Wheel screen — 2026-08-15",
            "## Monitored",
            "## Ranked candidates",
            "## Portfolio context",
            "## Flagged / rejected",
        ):
            self.assertIn(heading, markdown)

    def test_screen_outcome_matches_the_goldens(self) -> None:
        _, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertIn("| 1 | F |", markdown)          # in zone, top ranked
        self.assertIn("| 2 | MARA |", markdown)       # in zone, flagged
        self.assertIn("| · | SPY |", markdown)        # locked, out of zone
        # APLD is rejected; at scale rejections are counted by gate rather
        # than listed by name.
        self.assertIn("ST-SEL-01: 1 name", markdown)
        # A name with no snapshot is simply absent now: the screen enumerates
        # what Stage 2 produced rather than checking a configured list.
        self.assertNotIn("GHOST", markdown)

    def test_cross_candidate_rules_reach_the_report(self) -> None:
        _, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertIn("AL-SIZ-03", markdown)
        self.assertIn("AL-SIZ-04", markdown)

    def test_corrupt_snapshot_is_surfaced_not_scored(self) -> None:
        (self.wheelops / "snapshots" / "2026-08-15_F.json").write_text("{not json")
        _, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertIn("**F** — unreadable snapshot", markdown)

    def test_contract_violation_is_surfaced_not_scored(self) -> None:
        target = self.wheelops / "snapshots" / "2026-08-15_F.json"
        text = target.read_text().replace('"ticker": "F"', '"ticker": "f"')
        target.write_text(text)
        _, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertIn("violates the contract", markdown)

    def test_positions_ledger_feeds_portfolio_context(self) -> None:
        positions = self.wheelops / "positions"
        positions.mkdir()
        (positions / "ledger.csv").write_text(
            "ticker,sector,strike,contracts,status\n"
            "F,Consumer Cyclical,11,1,open\n"
        )
        _, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertIn("$1,100 needed vs $12,000 available", markdown)
        self.assertIn("Consumer Cyclical 100%", markdown)

    def test_empty_snapshot_folder_renders_an_empty_screen(self) -> None:
        for path in (self.wheelops / "snapshots").glob("*.json"):
            path.unlink()
        _, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertIn("# Wheel screen", markdown)
        self.assertIn("No in-zone candidates", markdown)

    def test_reused_snapshot_is_copied_to_current_date_and_screened(self) -> None:
        snapshots = self.wheelops / "snapshots"
        today = snapshots / "2026-08-15_F.json"
        document = json.loads(today.read_text())
        today.unlink()
        document["snapshot_date"] = "2026-08-14"
        yesterday = snapshots / "2026-08-14_F.json"
        yesterday.write_text(json.dumps(document))

        def unexpected_fetch(*_args, **_kwargs):
            self.fail("a reusable snapshot must not trigger a provider fetch")

        result = deep_snapshot(
            [
                Stage1Survivor(
                    "F",
                    price=document["price"]["current"],
                    market_cap=document["identity"]["market_cap"],
                    sector=document["identity"]["sector"],
                )
            ],
            wheelops=self.wheelops,
            run_date=RUN_DATE,
            fetched_at=datetime(2026, 8, 15, 9, 0),
            policy=None,
            fetch_snapshot=unexpected_fetch,
            fetch_calendar=unexpected_fetch,
            say=lambda _message: None,
        )

        self.assertEqual(result["reused"], ["F"])
        self.assertTrue(yesterday.is_file())
        self.assertTrue(today.is_file())
        self.assertEqual(today.read_bytes(), yesterday.read_bytes())

        _, markdown = run_screen(make_config(self.wheelops), RUN_DATE)
        self.assertIn("| 1 | F |", markdown)


if __name__ == "__main__":
    unittest.main()
