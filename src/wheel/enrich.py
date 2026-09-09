"""Layer 1: shape a provider `info` dictionary into the enrichment contract.

The screener answers "which names pass the rules"; enrichment answers "what is
this company" for the handful of names that passed. It is mechanical
throughout -- field extraction and coercion, nothing judged, no model
inference, no rule ID emitted. Enrichment never changes a score and never
reaches a scorer; it is display data for the rendered report.

Pure and provider-free, in the same split as everything else at Layer 1
(AGENTS.md §4.2). The `info` call that produces the input lives at Layer 0 in
`wheel_mcp.enrich_fetch`; this module only shapes what it returns and owns the
cache layout it writes to.

**Every field is nullable.** A provider that omits `freeCashflow` is the normal
case, not an error, and the contract carries the key with a null rather than
dropping it -- so the renderer can print "—" without asking whether a section
exists (AGENTS.md §4.4: degrade, don't crash).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

ENRICHMENT_SCHEMA_VERSION = 1
ENRICHMENT_SOURCE = "yfinance.info"
ENRICHMENT_DIRNAME = "enrichment"

# Names beyond this are dropped from the stored record rather than the report,
# so the file size ceiling is defended before the HTML is built, not after.
OFFICER_CAP = 12


# ---------------------------------------------------------------------------
# Coercions -- provider values in, JSON-safe values or None out
# ---------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    """A non-empty string, else None. Whitespace-only counts as missing."""

    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _number(value: Any) -> float | None:
    """A finite float. NaN and infinity are missing data, not values."""

    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _epoch_date(value: Any) -> str | None:
    """Yahoo reports `exDividendDate` as a UTC epoch; store it as ISO.

    A raw epoch renders as a nine-digit number in the report, which is worse
    than showing nothing. The conversion is mechanical and fixed to UTC so the
    same input yields the same date on any machine.
    """

    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10]).isoformat()
        except ValueError:
            return None
    seconds = _number(value)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# The contract: (output key, provider key, coercion), in render order
# ---------------------------------------------------------------------------

FieldSpec = tuple[str, str, Callable[[Any], Any]]

BUSINESS_FIELDS: tuple[FieldSpec, ...] = (
    ("long_name", "longName", _text),
    ("website", "website", _text),
    ("long_business_summary", "longBusinessSummary", _text),
    ("sector", "sector", _text),
    ("industry", "industry", _text),
    ("full_time_employees", "fullTimeEmployees", _integer),
)

RATIO_FIELDS: tuple[FieldSpec, ...] = (
    ("trailing_pe", "trailingPE", _number),
    ("forward_pe", "forwardPE", _number),
    ("price_to_book", "priceToBook", _number),
    ("debt_to_equity", "debtToEquity", _number),
    ("return_on_equity", "returnOnEquity", _number),
    ("profit_margins", "profitMargins", _number),
    ("operating_margins", "operatingMargins", _number),
)

REVENUE_FIELDS: tuple[FieldSpec, ...] = (
    ("total_revenue", "totalRevenue", _number),
    ("revenue_growth", "revenueGrowth", _number),
    ("revenue_per_share", "revenuePerShare", _number),
)

CASH_FLOW_FIELDS: tuple[FieldSpec, ...] = (
    ("free_cashflow", "freeCashflow", _number),
    ("operating_cashflow", "operatingCashflow", _number),
)

# `dividend_yield` is stored exactly as the provider reports it, matching
# `wheel.universe.Stage1Row` -- one convention for the whole codebase beats two
# that disagree about whether 2.3 means 2.3% or 230%.
DIVIDEND_FIELDS: tuple[FieldSpec, ...] = (
    ("dividend_rate", "dividendRate", _number),
    ("dividend_yield", "dividendYield", _number),
    ("payout_ratio", "payoutRatio", _number),
    ("ex_dividend_date", "exDividendDate", _epoch_date),
)

ANALYST_FIELDS: tuple[FieldSpec, ...] = (
    ("number_of_analyst_opinions", "numberOfAnalystOpinions", _integer),
    ("target_mean_price", "targetMeanPrice", _number),
    ("recommendation_key", "recommendationKey", _text),
)

SECTIONS: tuple[tuple[str, tuple[FieldSpec, ...]], ...] = (
    ("business", BUSINESS_FIELDS),
    ("ratios", RATIO_FIELDS),
    ("revenue", REVENUE_FIELDS),
    ("cash_flow", CASH_FLOW_FIELDS),
    ("dividend", DIVIDEND_FIELDS),
    ("analyst", ANALYST_FIELDS),
)


def section_keys(section: str) -> tuple[str, ...]:
    """Every output key in one section, in contract order."""

    for name, fields in SECTIONS:
        if name == section:
            return tuple(key for key, _, _ in fields)
    raise KeyError(section)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrichmentConfig:
    """How many monitored names to enrich, and which zones count."""

    top_n: int = 50
    include_locked_zones: bool = True


def enrichment_config_from_config(config: Mapping[str, Any]) -> EnrichmentConfig:
    settings = config.get("enrichment") or {}
    return EnrichmentConfig(
        top_n=int(settings.get("top_n", 50)),
        include_locked_zones=bool(settings.get("include_locked_zones", True)),
    )


# ---------------------------------------------------------------------------
# Building one record
# ---------------------------------------------------------------------------


def extract_officers(info: Mapping[str, Any]) -> list[dict[str, str | None]]:
    """Names and titles only, in the order the provider listed them.

    Everything else `companyOfficers` carries -- age, compensation, exercised
    option value -- is personal data with no bearing on a screen, so it is
    dropped at the boundary rather than written to disk and filtered later.
    """

    raw = info.get("companyOfficers")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    officers: list[dict[str, str | None]] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        name = _text(entry.get("name"))
        title = _text(entry.get("title"))
        if name is None and title is None:
            continue
        officers.append({"name": name, "title": title})
        if len(officers) >= OFFICER_CAP:
            break
    return officers


def build_enrichment(
    ticker: str,
    info: Mapping[str, Any] | None,
    *,
    fetched_on: date,
) -> dict[str, Any]:
    """One provider `info` dictionary as the enrichment contract. Pure.

    A `None` or unusable `info` still produces a complete, fully-null record:
    the run recorded that it looked, and the renderer has the same shape to
    read either way.
    """

    source = info if isinstance(info, Mapping) else {}
    document: dict[str, Any] = {
        "schema_version": ENRICHMENT_SCHEMA_VERSION,
        "ticker": ticker.strip().upper(),
        "fetched_on": fetched_on.isoformat(),
        "source": ENRICHMENT_SOURCE,
    }
    for section, fields in SECTIONS:
        document[section] = {
            key: coerce(source.get(provider_key))
            for key, provider_key, coerce in fields
        }
    document["officers"] = extract_officers(source)
    return document


def empty_enrichment(ticker: str, *, fetched_on: date) -> dict[str, Any]:
    """The all-null record, for a name whose fetch failed outright."""

    return build_enrichment(ticker, None, fetched_on=fetched_on)


# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------


def select_enrichment_targets(
    sidecar: Mapping[str, Any] | None,
    settings: EnrichmentConfig,
) -> list[str]:
    """The top-scoring monitored tickers to enrich, highest score first.

    Reads the screen's JSON sidecar rather than the rendered markdown, for the
    reason `wheel.monitored` gives: recovering numbers from prose tables breaks
    the first time a column moves.
    """

    entries = (sidecar or {}).get("entries")
    if not isinstance(entries, Mapping):
        return []

    ranked: list[tuple[float, str]] = []
    for ticker, record in entries.items():
        if not isinstance(record, Mapping):
            continue
        symbol = str(ticker).strip().upper()
        if not symbol:
            continue
        zone = str(record.get("zone") or "")
        if not settings.include_locked_zones and zone != "Zone 1":
            continue
        score = _number(record.get("score"))
        ranked.append((score if score is not None else 0.0, symbol))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [symbol for _, symbol in ranked[: max(0, settings.top_n)]]


# ---------------------------------------------------------------------------
# Cache layout: WheelOps/enrichment/YYYY-MM-DD/<TICKER>.json
# ---------------------------------------------------------------------------


def enrichment_dir(wheelops: str | Path, run_date: date | str) -> Path:
    stamp = run_date if isinstance(run_date, str) else run_date.isoformat()
    return Path(wheelops) / ENRICHMENT_DIRNAME / stamp


def enrichment_path(
    wheelops: str | Path, run_date: date | str, ticker: str
) -> Path:
    return enrichment_dir(wheelops, run_date) / f"{ticker.strip().upper()}.json"


def write_enrichment(
    wheelops: str | Path,
    run_date: date | str,
    document: Mapping[str, Any],
) -> Path:
    """Write one record atomically, as every other artifact is written."""

    path = enrichment_path(wheelops, run_date, str(document["ticker"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path


def read_enrichment(
    wheelops: str | Path, run_date: date | str, ticker: str
) -> dict[str, Any] | None:
    """One record, or None if it was never written or cannot be read."""

    path = enrichment_path(wheelops, run_date, ticker)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_enrichment_set(
    wheelops: str | Path,
    run_date: date | str,
    tickers: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Every readable record for a run date, keyed by ticker.

    An unreadable file is skipped, not raised: enrichment is decoration on a
    report that has to render either way.
    """

    directory = enrichment_dir(wheelops, run_date)
    if not directory.is_dir():
        return {}
    wanted = (
        {str(t).strip().upper() for t in tickers} if tickers is not None else None
    )
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        symbol = path.stem.upper()
        if wanted is not None and symbol not in wanted:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            found[symbol] = payload
    return found
