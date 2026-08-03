"""Machine-readable CSV output -- the interchange format Component C reads.

`render_csv` is pure: no clock, no filesystem, no network. Everything it emits
is read off `PipelineResult`; nothing is recomputed here, so the CSV can never
disagree with the pipeline that produced it. `write_csv` is the only function
that touches disk.

This is data interchange, not presentation. The HTML report that used to share
this module was cut with the UI layer; its renderers now sit in `legacy/`.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from datetime import date, datetime
from typing import Any

from .result import PipelineResult


HARD_GATE_IDS = ("F1", "F2", "F3", "F4", "F9")

# 33 columns. `fmp_rescued_fields` was column 34 until the FMP rescue path was
# cut; provenance tracking, if it returns, gets designed against the MCP
# interface rather than restored in its FMP-shaped form.
CSV_COLUMNS = (
    "ticker",
    "company_name",
    "business_description",
    "industry",
    "sector",
    "market_cap",
    "verdict",
    "composite",
    "f1_pass",
    "f1_net_income_ttm",
    "f1_operating_cash_flow_ttm",
    "f2_pass",
    "f2_recommendation_mean",
    "f3_pass",
    "f3_price",
    "f4_pass",
    "f9_pass",
    "f9_options_available",
    "f2_margin_score",
    "f5_score",
    "f5_max_daily_move",
    "f5_realized_vol",
    "f6_score",
    "f6_dividend_yield",
    "f7_score",
    "f7_realized_vol_30d",
    "f8_score",
    "f8_pct_below_2y_high",
    "f10_triggered",
    "f10_days_to_earnings",
    "f10_next_earnings_date",
    "fail_reason",
    "f7_is_approximation",
)


def _evaluated_by_symbol(result: PipelineResult) -> dict[str, Any]:
    """Index every ticker that produced a snapshot, across all three buckets."""

    buckets = result.buckets
    return {
        evaluated.snapshot.symbol: evaluated
        for group in (
            buckets.passed,
            buckets.failed_fitness,
            buckets.failed_missing_data,
        )
        for evaluated in group
    }


def _score_by_filter(scored: Any) -> dict[str, Any]:
    return {result.filter_id: result for result in scored.filter_results}


def _gate_by_id(evaluated: Any | None) -> dict[str, Any]:
    if evaluated is None:
        return {}
    return {gate.gate_id: gate for gate in evaluated.gate_results}


def build_csv_rows(result: PipelineResult) -> list[list[Any]]:
    """One row per universe ticker, in universe-file order."""

    evaluated_by_symbol = _evaluated_by_symbol(result)
    flagged_by_symbol = {
        flagged.symbol: flagged for flagged in result.flagged_scored
    }
    state = result.current_state

    rows: list[list[Any]] = []
    for symbol in result.universe_symbols:
        record = state.get(symbol, {})
        evaluated = evaluated_by_symbol.get(symbol)
        flagged = flagged_by_symbol.get(symbol)

        # A fetch error never produced a snapshot, so its gates are blank
        # rather than False: nothing was evaluated to fail.
        gate_passed: dict[str, bool | None] = {
            gate_id: None for gate_id in HARD_GATE_IDS
        }
        if evaluated is not None:
            for gate in evaluated.gate_results:
                gate_passed[gate.gate_id] = gate.passed

        by_filter: dict[str, Any] = {}
        analyst_score = None
        f7_is_approximation = True
        if flagged is not None:
            by_filter = _score_by_filter(flagged.scored)
            analyst_score = flagged.scored.analyst_strength_score
            f7_result = by_filter.get("F7")
            if f7_result is not None:
                f7_is_approximation = f7_result.is_approximation

        def score_of(filter_id: str) -> float | None:
            return getattr(by_filter.get(filter_id), "score", None)

        def metric_of(filter_id: str, key: str) -> float | None:
            result_obj = by_filter.get(filter_id)
            if result_obj is None:
                return None
            return result_obj.metrics.get(key)

        f10 = flagged.f10 if flagged is not None else None

        gates = _gate_by_id(evaluated)

        def gate_metric(gate_id: str, key: str) -> float | int | bool | None:
            gate = gates.get(gate_id)
            return None if gate is None else gate.metrics.get(key)

        fundamentals = (
            evaluated.snapshot.fundamentals if evaluated is not None else {}
        )
        rows.append(
            [
                symbol,
                fundamentals.get("company_name"),
                fundamentals.get("business_description"),
                fundamentals.get("industry"),
                fundamentals.get("sector"),
                fundamentals.get("market_cap"),
                record.get("verdict"),
                record.get("composite"),
                gate_passed["F1"],
                gate_metric("F1", "net_income_ttm"),
                gate_metric("F1", "operating_cash_flow_ttm"),
                gate_passed["F2"],
                gate_metric("F2", "recommendation_mean"),
                gate_passed["F3"],
                gate_metric("F3", "price"),
                gate_passed["F4"],
                gate_passed["F9"],
                gate_metric("F9", "options_available"),
                analyst_score,
                score_of("F5"),
                metric_of("F5", "max_daily_move"),
                metric_of("F5", "realized_vol"),
                score_of("F6"),
                metric_of("F6", "dividend_yield"),
                score_of("F7"),
                metric_of("F7", "realized_vol_30d"),
                score_of("F8"),
                metric_of("F8", "pct_below_2y_high"),
                None if f10 is None else f10.triggered,
                None if f10 is None else f10.days_to_earnings,
                None if f10 is None else f10.next_earnings_date,
                record.get("reason"),
                f7_is_approximation,
            ]
        )
    return rows


def _csv_cell(value: Any) -> str:
    """Null renders empty; booleans lowercase; dates ISO."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def render_csv(pipeline_result: PipelineResult) -> str:
    """Render the machine-readable CSV that Components B and C consume."""

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in build_csv_rows(pipeline_result):
        writer.writerow([_csv_cell(value) for value in row])
    return buffer.getvalue()


def _write_atomic(path: Path, text: str) -> Path:
    """Mirror the state writer: temp sibling, then atomic replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)
    return path


def write_csv(
    pipeline_result: PipelineResult,
    output_dir: str | Path,
    timestamp: datetime,
) -> Path:
    """Write the CSV under the run timestamp, pairing it with the state file."""

    stamp = timestamp.strftime("%Y-%m-%d-%H%M%S")
    return _write_atomic(
        Path(output_dir) / f"candidates_{stamp}.csv",
        render_csv(pipeline_result),
    )
