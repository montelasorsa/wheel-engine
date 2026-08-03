"""QUARANTINED -- the HTML half of the old reporting/render.py.

Cut with the UI layer in the plugin/MCP reorg. Kept only so the operator can
verify nothing needed was lost before deleting it. Nothing in src/ imports
this; it pairs with report.html.j2 and serve.py, also in this folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from wheel.csv_output import _evaluated_by_symbol, _gate_by_id, _score_by_filter
from wheel.gates import GateFailureKind
from wheel.result import PipelineResult
from wheel.scoring import IV_PROXY_APPROXIMATION


TEMPLATE_DIR = Path(__file__).parent
TEMPLATE_NAME = "report.html.j2"

# F10 / ST-ENT-05 proximity bands. The flag never disqualifies; these only
# control how loudly the date is drawn.
F10_WARNING_DAYS = 14
F10_NOTABLE_DAYS = 30
F10_NEUTRAL_DAYS = 45


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
        row = {
            "ticker": evaluated.snapshot.symbol,
            "blocking": blocking,
            "sources": [],
        }
        row.update(_business_context(evaluated))
        rows.append(row)
    rows.sort(key=lambda row: row["ticker"])
    return rows


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
