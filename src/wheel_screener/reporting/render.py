"""Presentation layer: renders a finished run as HTML and CSV.

`render_html` and `render_csv` are pure -- no clock, no filesystem, no network.
Everything they show is read off `PipelineResult`; nothing is recomputed here,
so the report can never disagree with the pipeline that produced it.
`write_report_and_csv` is the only function that touches disk.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from datetime import date, datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader

from wheel_screener.screening.hard_gates import GateFailureKind
from wheel_screener.scoring.score_filters import IV_PROXY_APPROXIMATION

from .model import PipelineResult


TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"

HARD_GATE_IDS = ("F1", "F2", "F3", "F4", "F9")

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
    "fmp_rescued_fields",
    "f7_is_approximation",
)

# F10 / ST-ENT-05 proximity bands. The flag never disqualifies; these only
# control how loudly the date is drawn.
F10_WARNING_DAYS = 14
F10_NOTABLE_DAYS = 30
F10_NEUTRAL_DAYS = 45


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


RESCUE_SOURCE = "fmp"


def _rescued_fields(evaluated: Any | None) -> tuple[str, ...]:
    """Fields FMP supplied, from snapshot provenance.

    `field_sources` is a full provenance map -- every successfully-populated
    fundamental is tagged "yfinance" by `build_ticker_snapshot`, not just
    rescued ones. Only entries `rescue.py` overwrote to "fmp" are an actual
    rescue. Filtering on the value (not just key presence) reads generically,
    so a future FMP reactivation needs no change here or in the template.
    """

    if evaluated is None:
        return ()
    sources = getattr(evaluated.snapshot, "field_sources", None) or {}
    return tuple(
        sorted(field for field, source in sources.items() if source == RESCUE_SOURCE)
    )


def _f10_view(flag: Any) -> dict[str, Any]:
    """Render F10 as a dated proximity chip rather than a boolean."""

    days = flag.days_to_earnings
    next_date = flag.next_earnings_date
    if next_date is None or days is None or days < 0:
        return {
            "label": "no calendar data",
            "css_class": "f10-unknown",
            "triggered": bool(flag.triggered),
            "days": None,
            "date": None,
        }

    if days < F10_WARNING_DAYS:
        css_class = "f10-warning"
    elif days < F10_NOTABLE_DAYS:
        css_class = "f10-notable"
    elif days <= F10_NEUTRAL_DAYS:
        css_class = "f10-neutral"
    else:
        css_class = "f10-far"

    return {
        "label": f"{next_date.strftime('%b')} {next_date.day} ({days}d)",
        "css_class": css_class,
        "triggered": bool(flag.triggered),
        "days": days,
        "date": next_date,
    }


def _score_by_filter(scored: Any) -> dict[str, Any]:
    return {result.filter_id: result for result in scored.filter_results}


def _gate_by_id(evaluated: Any | None) -> dict[str, Any]:
    if evaluated is None:
        return {}
    return {gate.gate_id: gate for gate in evaluated.gate_results}


def format_market_cap(value: float | int | None) -> str | None:
    """$2.95T / $45.71B / $820M -- compact enough for a table sub-line."""

    if not isinstance(value, (int, float)) or value <= 0:
        return None
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if value >= threshold:
            return f"${value / threshold:.2f}{suffix}".replace(".00", "")
    return f"${value:,.0f}"


def _business_context(evaluated: Any | None) -> dict[str, Any]:
    """Company identity fields for a row; every field fail-open to None."""

    fundamentals = (
        evaluated.snapshot.fundamentals if evaluated is not None else {}
    )
    sector = fundamentals.get("sector")
    industry = fundamentals.get("industry")
    if sector and industry:
        sector_line = f"{sector} — {industry}"
    else:
        sector_line = sector or industry
    return {
        "company_name": fundamentals.get("company_name"),
        "business_description": fundamentals.get("business_description"),
        "sector_line": sector_line,
        "market_cap_text": format_market_cap(fundamentals.get("market_cap")),
    }


def _fmt_score(value: float | None) -> str:
    return "--" if value is None else f"{value:.0f}"


def _score_with_metric(score_text: str, *metric_texts: str | None) -> str:
    """Compose the 'score · metric' cell; score alone when nothing measured."""

    present = [text for text in metric_texts if text]
    if not present:
        return score_text
    return f"{score_text} · {' / '.join(present)}"


def _pct(value: float | None) -> str | None:
    return None if value is None else f"{value:.2%}"


def build_ranked_rows(result: PipelineResult) -> list[dict[str, Any]]:
    """Scored survivors, composite descending, ranked for section C."""

    def sort_key(flagged: Any) -> tuple[int, float, str]:
        composite = flagged.scored.composite_score
        # Unscoreable composites sort last, then alphabetically, so the order
        # is stable across runs.
        return (1, 0.0, flagged.symbol) if composite is None else (
            0,
            -composite,
            flagged.symbol,
        )

    evaluated_by_symbol = _evaluated_by_symbol(result)
    rows = []
    for rank, flagged in enumerate(sorted(result.flagged_scored, key=sort_key), 1):
        scored = flagged.scored
        by_filter = _score_by_filter(scored)
        composite = scored.composite_score
        evaluated = evaluated_by_symbol.get(flagged.symbol)
        gates = _gate_by_id(evaluated)

        def metric(filter_id: str, key: str) -> float | None:
            score_result = by_filter.get(filter_id)
            return None if score_result is None else score_result.metrics.get(key)

        recommendation_mean = (
            gates["F2"].metrics.get("recommendation_mean")
            if "F2" in gates
            else None
        )
        f6_yield = metric("F6", "dividend_yield")
        row = {
            "rank": rank,
            "ticker": flagged.symbol,
            "composite": composite,
            "composite_text": "--" if composite is None else f"{composite:.1f}",
            "composite_pct": 0.0 if composite is None else max(0.0, min(100.0, composite)),
            "f5": _score_with_metric(
                _fmt_score(getattr(by_filter.get("F5"), "score", None)),
                _pct(metric("F5", "max_daily_move")),
                _pct(metric("F5", "realized_vol")),
            ),
            "f6": _score_with_metric(
                _fmt_score(getattr(by_filter.get("F6"), "score", None)),
                f"{f6_yield:.2f}%" if f6_yield is not None else "—",
            ),
            "f7": _score_with_metric(
                _fmt_score(getattr(by_filter.get("F7"), "score", None)),
                _pct(metric("F7", "realized_vol_30d")),
            ),
            "f8": _score_with_metric(
                _fmt_score(getattr(by_filter.get("F8"), "score", None)),
                _pct(metric("F8", "pct_below_2y_high")),
            ),
            "f2": _score_with_metric(
                _fmt_score(scored.analyst_strength_score),
                f"{recommendation_mean:.2f}"
                if recommendation_mean is not None
                else None,
            ),
            "f10": _f10_view(flagged.f10),
        }
        row.update(_business_context(evaluated))
        rows.append(row)
    return rows


def build_missing_data_rows(result: PipelineResult) -> list[dict[str, Any]]:
    """Names that could not be evaluated, with the gate that could not run."""

    rows = []
    for evaluated in result.buckets.failed_missing_data:
        blocking = []
        for gate in evaluated.gate_results:
            if gate.passed or gate.failure_kind is not GateFailureKind.MISSING_DATA:
                continue
            # Observed inputs from gate metrics: what was null, and what was
            # present alongside it -- the expected-vs-actual gut-check line.
            observed = ", ".join(
                f"{name} = {_observed_value(name, value)}"
                for name, value in gate.metrics.items()
            )
            blocking.append(
                {
                    "gate_id": gate.gate_id,
                    "reason": gate.reason,
                    "observed": observed,
                }
            )
        sources = getattr(evaluated.snapshot, "field_sources", None) or {}
        row = {
            "ticker": evaluated.snapshot.symbol,
            "blocking": blocking,
            "sources": [
                {"field": field, "source": sources[field]}
                for field in sorted(sources)
                if sources[field] != "yfinance"
            ],
        }
        row.update(_business_context(evaluated))
        rows.append(row)
    rows.sort(key=lambda row: row["ticker"])
    return rows


_MONEY_METRICS = {"net_income_ttm", "operating_cash_flow_ttm", "price"}


def _observed_value(name: str, value: float | int | bool | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if name in _MONEY_METRICS:
        if abs(value) >= 1e6:
            return f"${value / 1e6:,.0f}M present"
        return f"${value:,.2f}"
    return f"{value:g} present"


def build_summary(result: PipelineResult) -> dict[str, Any]:
    """Header counts for section A, and the fitness-fail total for section F."""

    percentile = result.universe_volatility_percentile
    return {
        "run_timestamp": result.run_timestamp,
        "run_timestamp_text": result.run_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "universe_size": len(result.universe_symbols),
        "scored": len(result.flagged_scored),
        "fitness_fail": len(result.buckets.failed_fitness),
        "missing_data": len(result.buckets.failed_missing_data),
        "fetch_error": len(result.fetch_error_symbols),
        "volatility_benchmark": percentile,
        "volatility_benchmark_text": (
            "unavailable" if percentile is None else f"{percentile:.2%}"
        ),
        "iv_approximation_note": IV_PROXY_APPROXIMATION,
    }


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
                ",".join(_rescued_fields(evaluated)),
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


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _diff_with_names(result: PipelineResult) -> dict[str, Any]:
    """The Step 5 diff plus company names, joined fail-open.

    A newly-dropped name that became a fetch error has no snapshot this run;
    it renders as ticker alone rather than being omitted.
    """

    evaluated_by_symbol = _evaluated_by_symbol(result)

    def named(entries: list) -> list[dict[str, Any]]:
        enriched = []
        for entry in entries:
            evaluated = evaluated_by_symbol.get(entry["ticker"])
            fundamentals = (
                evaluated.snapshot.fundamentals if evaluated is not None else {}
            )
            enriched.append(
                {**entry, "company_name": fundamentals.get("company_name")}
            )
        return enriched

    diff = dict(result.diff)
    diff["newly_qualified"] = named(diff.get("newly_qualified", []))
    diff["newly_dropped"] = named(diff.get("newly_dropped", []))
    return diff


def render_html(pipeline_result: PipelineResult) -> str:
    """Render the self-contained, offline-viewable HTML report."""

    template = _environment().get_template(TEMPLATE_NAME)
    return template.render(
        summary=build_summary(pipeline_result),
        diff=_diff_with_names(pipeline_result),
        ranked=build_ranked_rows(pipeline_result),
        missing_data=build_missing_data_rows(pipeline_result),
        fetch_errors=sorted(pipeline_result.fetch_error_symbols),
    )


def _write_atomic(path: Path, text: str) -> Path:
    """Mirror the state writer: temp sibling, then atomic replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)
    return path


def write_report_and_csv(
    pipeline_result: PipelineResult,
    output_dir: str | Path,
    timestamp: datetime,
) -> tuple[Path, Path]:
    """Write both artifacts under one timestamp, pairing them with the state."""

    stamp = timestamp.strftime("%Y-%m-%d-%H%M%S")
    directory = Path(output_dir)
    report_path = _write_atomic(
        directory / f"report_{stamp}.html",
        render_html(pipeline_result),
    )
    csv_path = _write_atomic(
        directory / f"candidates_{stamp}.csv",
        render_csv(pipeline_result),
    )
    return report_path, csv_path
