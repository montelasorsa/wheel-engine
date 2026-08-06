"""Layer 1 screen run: read snapshots, score, write the weekly report.

Snapshot-then-score (AGENTS.md §4.1): this module reads only what Layer 0
already wrote to `WheelOps/snapshots/` -- never a live call, no provider
import. Run it standalone against existing snapshots:

    PYTHONPATH=src python -m wheel.screen [YYYY-MM-DD]
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from .config_io import load_config, wheelops_dir
from .scorers import (
    evaluate_cross_candidate_rules,
    evaluate_single_ticker_rules,
    selection_thresholds_from_config,
)
from .snapshot_schema import snapshot_filename, validate_snapshot
from .week_report import ScoredName, render_week_report


def read_position_rows(positions_dir: Path) -> list[dict[str, Any]]:
    """Every row of every CSV in the ledger folder; tolerant of absence."""

    if not positions_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(positions_dir.glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                rows.extend(dict(row) for row in csv.DictReader(handle))
        except OSError:
            continue
    return rows


def load_snapshot_documents(
    snapshots_dir: Path,
    watchlist: tuple[str, ...],
    run_date: date,
) -> tuple[list[Mapping[str, Any]], list[tuple[str, str]]]:
    """Load and validate this run's snapshot per watchlist name.

    Returns (documents, missing) where missing carries (ticker, reason) for
    names with no valid snapshot -- surfaced, never dropped.
    """

    documents: list[Mapping[str, Any]] = []
    missing: list[tuple[str, str]] = []
    for symbol in watchlist:
        path = snapshots_dir / snapshot_filename(run_date.isoformat(), symbol)
        if not path.is_file():
            missing.append((symbol, f"no snapshot at {path.name}"))
            continue
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            missing.append((symbol, f"unreadable snapshot: {error}"))
            continue
        errors = validate_snapshot(document)
        if errors:
            missing.append(
                (symbol, f"snapshot violates the contract: {errors[0]}")
            )
            continue
        documents.append(document)
    return documents, missing


def run_screen(
    config: Mapping[str, Any],
    run_date: date,
) -> tuple[Path, str]:
    """Score one day's snapshots and write `weeks/YYYY-MM-DD.md`."""

    wheelops = wheelops_dir(config)
    thresholds = selection_thresholds_from_config(config)
    watchlist = tuple(
        str(entry).strip().upper()
        for entry in config.get("watchlist", [])
        if str(entry).strip()
    )
    if not watchlist:
        raise ValueError(
            "config.yaml needs a non-empty `watchlist:` list (ST-SEL-07)."
        )

    documents, missing = load_snapshot_documents(
        wheelops / "snapshots", watchlist, run_date
    )
    scored = [
        ScoredName(
            document=document,
            results=evaluate_single_ticker_rules(document, thresholds),
        )
        for document in documents
    ]
    cross_results = evaluate_cross_candidate_rules(documents)

    account = config["account"]
    markdown = render_week_report(
        run_date=run_date,
        net_liq=float(account["net_liq"]),
        per_name_cap=float(account["per_name_cap"]),
        scored=scored,
        cross_results=cross_results,
        position_rows=read_position_rows(wheelops / "positions"),
        missing=missing,
        weights=config["weights"],
    )

    weeks_dir = wheelops / "weeks"
    weeks_dir.mkdir(parents=True, exist_ok=True)
    path = weeks_dir / f"{run_date.isoformat()}.md"
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
    path, _ = run_screen(config, run_date)
    print(f"WEEK {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
