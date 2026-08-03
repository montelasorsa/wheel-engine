"""Composition root: wires the existing pure components into one run.

This module holds no screening logic of its own. Every rule lives in
`screening` and `scoring`; this only loads config, fetches, and calls them in
order. `run_pipeline` is importable so the Step 7 serve route can call it
directly rather than shelling out.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from wheel_screener.data import (
    DEFAULT_REQUEST_THROTTLE,
    TickerSnapshot,
    fetch_earnings_calendar,
    fetch_ticker_snapshot,
    yfinance_policy_from_config,
)
from wheel_screener.reporting import PipelineResult, write_report_and_csv
from wheel_screener.scoring import (
    composite_weights_from_config,
    compute_universe_volatility_percentile,
    score_eligible_snapshot,
    scoring_thresholds_from_config,
)
from wheel_screener.screening import (
    evaluate_hard_gates_for_snapshots,
    hard_gate_thresholds_from_config,
    partition_evaluated_hard_gates,
    rescue_enabled_from_config,
    rescue_operating_cash_flow_ttm,
)
from wheel_screener.screening.step5_pipeline import finalize_step5_run

PROGRESS_EVERY = 25


def load_config(config_path: str | Path) -> Mapping[str, Any]:
    """Parse the YAML config at the IO edge."""

    return yaml.safe_load(Path(config_path).read_text())


def load_universe_symbols(
    config: Mapping[str, Any],
    base_dir: Path,
) -> tuple[str, ...]:
    """Read the universe CSV, preserving file order and dropping repeats."""

    universe = config["universe"]
    path = base_dir / universe["file"]
    column = universe["ticker_column"]

    symbols: list[str] = []
    seen: set[str] = set()
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get(column) or "").strip().upper()
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    if not symbols:
        raise ValueError(f"No tickers found in {path}.")
    return tuple(symbols)


def _fmp_value_fetcher() -> Any:
    """Build the FMP callable lazily so a dormant rescue needs no API key."""

    def fetch(symbol: str) -> float | None:
        from wheel_screener.data import (
            fetch_fmp_operating_cash_flow_ttm,
            load_fmp_api_key,
        )

        return fetch_fmp_operating_cash_flow_ttm(symbol, load_fmp_api_key())

    return fetch


def run_pipeline(config_path: str | Path = "config.yaml") -> PipelineResult:
    """Fetch, gate, score, flag, diff and persist one full universe run."""

    config_path = Path(config_path)
    base_dir = config_path.parent
    config = load_config(config_path)

    symbols = load_universe_symbols(config, base_dir)
    policy = yfinance_policy_from_config(config)
    gate_thresholds = hard_gate_thresholds_from_config(config)
    scoring_thresholds = scoring_thresholds_from_config(config)
    weights = composite_weights_from_config(config)
    output_dir = (base_dir / config["paths"]["output"]).resolve()

    # One timestamp for the whole run, so state, report and CSV are pairable.
    run_timestamp = datetime.now()
    run_date = run_timestamp.date()

    print(f"RUN start={run_timestamp:%Y-%m-%d %H:%M:%S} universe={len(symbols)}", flush=True)

    snapshots: list[TickerSnapshot] = []
    fetch_error_symbols: list[str] = []
    fetch_failures: list[tuple[str, str]] = []
    for index, symbol in enumerate(symbols, 1):
        try:
            snapshots.append(
                fetch_ticker_snapshot(
                    symbol,
                    policy=policy,
                    throttle=DEFAULT_REQUEST_THROTTLE,
                )
            )
        except Exception as error:  # one bad ticker must never kill the run
            fetch_error_symbols.append(symbol)
            fetch_failures.append((symbol, type(error).__name__))
        if index % PROGRESS_EVERY == 0 or index == len(symbols):
            print(
                f"INGEST {index}/{len(symbols)} "
                f"normalized={len(snapshots)} errors={len(fetch_error_symbols)}",
                flush=True,
            )

    if fetch_failures:
        kinds = sorted({kind for _, kind in fetch_failures})
        print(f"FETCH-ERRORS {len(fetch_failures)} kinds={','.join(kinds)}", flush=True)

    evaluated = evaluate_hard_gates_for_snapshots(snapshots, gate_thresholds)
    rescue_enabled = rescue_enabled_from_config(config)
    if rescue_enabled:
        batch = rescue_operating_cash_flow_ttm(
            evaluated,
            gate_thresholds,
            _fmp_value_fetcher(),
            enabled=True,
        )
        evaluated = batch.evaluated_tickers
        print(f"RESCUE queried={len(batch.queried_symbols)}", flush=True)
    else:
        print("RESCUE dormant (RESCUE_ENABLED=false)", flush=True)

    buckets = partition_evaluated_hard_gates(evaluated)
    print(
        f"GATES passed={len(buckets.passed)} "
        f"fitness_fail={len(buckets.failed_fitness)} "
        f"missing_data={len(buckets.failed_missing_data)}",
        flush=True,
    )

    universe_volatility_percentile = compute_universe_volatility_percentile(
        snapshots,
        scoring_thresholds,
    )
    scored_tickers = [
        score_eligible_snapshot(
            evaluated_ticker.snapshot,
            evaluated_ticker.gate_results,
            scoring_thresholds,
            weights,
            universe_volatility_percentile,
        )
        for evaluated_ticker in buckets.passed
    ]
    print(f"SCORED {len(scored_tickers)}", flush=True)

    # F10 only attaches to scored survivors, so only they need a calendar.
    calendars_by_symbol: dict[str, Mapping[str, Any] | None] = {}
    for index, evaluated_ticker in enumerate(buckets.passed, 1):
        symbol = evaluated_ticker.snapshot.symbol
        try:
            calendars_by_symbol[symbol] = fetch_earnings_calendar(
                symbol,
                policy=policy,
                throttle=DEFAULT_REQUEST_THROTTLE,
            )
        except Exception:
            calendars_by_symbol[symbol] = None
    print(f"CALENDARS {len(calendars_by_symbol)}", flush=True)

    step5 = finalize_step5_run(
        universe_symbols=symbols,
        fetch_error_symbols=fetch_error_symbols,
        buckets=buckets,
        scored_tickers=scored_tickers,
        calendars_by_symbol=calendars_by_symbol,
        run_date=run_date,
        run_timestamp=run_timestamp,
        earnings_threshold_days=int(
            config["thresholds"]["earnings"]["flag_within_days"]
        ),
        output_dir=output_dir,
    )

    return PipelineResult(
        run_timestamp=run_timestamp,
        run_date=run_date,
        universe_symbols=symbols,
        fetch_error_symbols=tuple(fetch_error_symbols),
        buckets=buckets,
        step5=step5,
        universe_volatility_percentile=universe_volatility_percentile,
    )


if __name__ == "__main__":
    result = run_pipeline("config.yaml")
    report_path, csv_path = write_report_and_csv(
        result,
        result.step5.state_path.parent,
        result.run_timestamp,
    )
    print(f"STATE  {result.step5.state_path}", flush=True)
    print(f"REPORT {report_path}", flush=True)
    print(f"CSV    {csv_path}", flush=True)
