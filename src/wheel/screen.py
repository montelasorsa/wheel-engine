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
from .monitored import (
    monitored_config_from_config,
    read_prior_sidecar,
    sidecar_payload,
    write_sidecar,
)
from .scorers import (
    evaluate_cross_candidate_rules,
    evaluate_single_ticker_rules,
    selection_thresholds_from_config,
)
from .snapshot_schema import snapshot_filename, validate_snapshot
from .week_report import ScoredName, classify, render_week_report


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
    run_date: date,
) -> tuple[list[Mapping[str, Any]], list[tuple[str, str]]]:
    """Load and validate every snapshot Layer 0 wrote for this run date.

    The universe is whatever Stage 2 produced, so the screen enumerates the
    snapshot folder rather than a configured list -- there is no longer a
    hand-picked watchlist to iterate.

    Returns (documents, unusable) where unusable carries (ticker, reason) for
    snapshots that exist but cannot be scored -- surfaced, never dropped.
    """

    documents: list[Mapping[str, Any]] = []
    unusable: list[tuple[str, str]] = []
    prefix = f"{run_date.isoformat()}_"
    for path in sorted(Path(snapshots_dir).glob(f"{prefix}*.json")):
        symbol = path.stem[len(prefix):]
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            unusable.append((symbol, f"unreadable snapshot: {error}"))
            continue
        errors = validate_snapshot(document)
        if errors:
            unusable.append(
                (symbol, f"snapshot violates the contract: {errors[0]}")
            )
            continue
        documents.append(document)
    return documents, unusable


def read_run_manifest(wheelops: Path, run_date: date) -> dict[str, Any]:
    """Stage 1/2 counts from the acquisition run, if it left a manifest."""

    path = wheelops / "universe" / f"run-{run_date.isoformat()}.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def run_screen(
    config: Mapping[str, Any],
    run_date: date,
) -> tuple[Path, str]:
    """Score one day's snapshots and write `weeks/YYYY-MM-DD.md`."""

    wheelops = wheelops_dir(config)
    thresholds = selection_thresholds_from_config(config)

    documents, missing = load_snapshot_documents(wheelops / "snapshots", run_date)
    scored = [
        ScoredName(
            document=document,
            results=evaluate_single_ticker_rules(document, thresholds),
        )
        for document in documents
    ]
    position_rows = read_position_rows(wheelops / "positions")

    # AL-SIZ-03/04 are scoped to names the operator is actually considering:
    # thesis-backed candidates plus anything already held. Across 200 screened
    # names every week clusters, and a flag that always fires is not a flag.
    held = {
        str(row.get("ticker") or "").strip().upper() for row in position_rows
    }
    considered = [
        name.document
        for name in scored
        if classify(name.results) == "candidate" or name.ticker in held
    ]
    cross_results = evaluate_cross_candidate_rules(considered)

    weeks_dir = wheelops / "weeks"
    settings = monitored_config_from_config(config)
    prior = read_prior_sidecar(weeks_dir, run_date.isoformat())

    account = config["account"]
    markdown, kept = render_week_report(
        run_date=run_date,
        net_liq=float(account["net_liq"]),
        per_name_cap=float(account["per_name_cap"]),
        scored=scored,
        cross_results=cross_results,
        position_rows=position_rows,
        missing=missing,
        weights=config["weights"],
        monitored_settings=settings,
        prior_monitored=prior,
        run_manifest=read_run_manifest(wheelops, run_date),
    )

    weeks_dir.mkdir(parents=True, exist_ok=True)
    path = weeks_dir / f"{run_date.isoformat()}.md"
    temporary = path.with_suffix(".md.tmp")
    temporary.write_text(markdown, encoding="utf-8")
    temporary.replace(path)
    write_sidecar(
        weeks_dir, run_date.isoformat(), sidecar_payload(run_date.isoformat(), kept, settings)
    )
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
