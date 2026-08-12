"""Layer 0 fallback: fill snapshot nulls yfinance left behind, and nothing more.

**FMP is never a primary source and never a parallel fetch.** yfinance runs
first; this module is consulted only for the specific fields that came back
null, only for the four fields named in `FILLABLE_FIELDS`, and only when a key
is configured. On the 2026-08-11 universe that is 17 names of 1,285 for
fundamentals and 12 for market cap -- roughly 50 requests per run.

That narrowness is the design, not an accident of scope. AGENTS.md previously
recorded FMP as removed outright, on the reasoning that "missing data is a
scorer problem, not a source problem" (§10, 2026-08-06). That reasoning still
holds for the general case and §4.4's graceful-null handling is unchanged: a
name with a null field is still scored on what exists and flagged
`data_incomplete`. What changed is the residual. A hard gate that reads
`CANNOT_EVALUATE` fails closed, so a null `net_income_ttm` rejects a name on a
data gap rather than on its merits -- and 1.3% of a 5,000-name universe is
enough names to be worth one cheap request each.

Two rules keep this honest:

1. **The key is never logged, never returned, and never placed in an exception
   message.** Requests that fail raise with the symbol only.
2. **A filled snapshot says so.** `source.provider` becomes `yfinance+fmp` and
   `source.partial` becomes True, which is exactly what that field was defined
   for. A mixed-source snapshot must never read as a pure one.

Which fields are *not* here matters as much as which are. Analyst consensus is
excluded: FMP publishes grades, not Yahoo's 1-5 `recommendationMean`, and under
continuous scoring that field drives a score directly -- two scales in one
field would be a silent measurement error. Sector and industry are excluded
because G-11 was closed with "Yahoo Finance sector labels are authoritative at
pilot scale", and AL-SIZ-02/03 aggregate on those labels.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import requests
from dotenv import load_dotenv

from wheel.snapshot import normalize_symbol

FMP_BASE_URL = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT_SECONDS = 20.0

PROVIDER_LABEL = "fmp"
MERGED_PROVIDER_LABEL = "yfinance+fmp"

# The complete allowlist. A field absent here is never fetched, whatever it
# costs the screen -- widening this is a governance decision, not a code change.
FILLABLE_FIELDS: tuple[str, ...] = (
    "fundamentals.net_income_ttm",
    "fundamentals.operating_cash_flow_ttm",
    "fundamentals.revenue_ttm",
    "identity.market_cap",
)

# Which endpoint answers which field, and under which key in its payload. Two
# fields share the income statement, so the fetch is grouped by endpoint rather
# than issued per field.
_ENDPOINTS: Mapping[str, tuple[str, Mapping[str, str]]] = {
    "income": (
        "income-statement-ttm",
        {
            "fundamentals.net_income_ttm": "netIncome",
            "fundamentals.revenue_ttm": "revenue",
        },
    ),
    "cash_flow": (
        "cash-flow-statement-ttm",
        {
            "fundamentals.operating_cash_flow_ttm": (
                "netCashProvidedByOperatingActivities"
            )
        },
    ),
    "profile": ("profile", {"identity.market_cap": "marketCap"}),
}


class FmpConfigurationError(RuntimeError):
    """Raised when a fallback is attempted without an API key."""


class FmpRequestError(RuntimeError):
    """Raised when FMP cannot return a usable HTTP response."""


# Absolute on purpose. A relative ".env" resolves against the caller's working
# directory, so the fallback would silently disable itself whenever acquisition
# runs from anywhere but the repo root -- the same relative-path failure that
# has already bitten this project's config paths twice.
DEFAULT_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load_fmp_api_key(dotenv_path: str | Path = DEFAULT_DOTENV_PATH) -> str:
    """Load the secret without logging it or naming it in an error message."""

    load_dotenv(dotenv_path=dotenv_path, override=False)
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        raise FmpConfigurationError(
            "FMP_API_KEY is not configured; see .env.example. The fallback "
            "cannot run, so the null stands."
        )
    return api_key


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


# ---------------------------------------------------------------------------
# Pure: what is missing, and how a fill lands in the document
# ---------------------------------------------------------------------------


def _read(document: Mapping[str, Any], dotted: str) -> Any:
    section, key = dotted.split(".", 1)
    block = document.get(section)
    return block.get(key) if isinstance(block, Mapping) else None


def missing_fields(
    document: Mapping[str, Any],
    fillable: Sequence[str] = FILLABLE_FIELDS,
) -> tuple[str, ...]:
    """Which allowlisted fields came back null. Pure.

    An ETF legitimately has no net income or market cap, and asking FMP for one
    would spend a request to learn what ST-SEL-08 already knows. Instrument
    classes with no issuer behind them are skipped entirely.
    """

    quote_type = _read(document, "identity.quote_type")
    if isinstance(quote_type, str) and quote_type.strip().upper() in (
        "ETF",
        "MUTUALFUND",
        "INDEX",
        "CURRENCY",
    ):
        return ()
    return tuple(field for field in fillable if _read(document, field) is None)


def merge_fill(
    document: Mapping[str, Any],
    fills: Mapping[str, float],
) -> dict[str, Any]:
    """Apply fetched values and mark the snapshot as mixed-source. Pure.

    Only null fields are written. A fill that arrives for a field yfinance
    already answered is discarded rather than allowed to overwrite it -- the
    primary source stays primary even when the fallback disagrees.
    """

    merged = {
        key: (dict(value) if isinstance(value, Mapping) else value)
        for key, value in document.items()
    }
    applied = 0
    for field, value in fills.items():
        if field not in FILLABLE_FIELDS:
            continue
        number = _finite_number(value)
        if number is None:
            continue
        section, key = field.split(".", 1)
        block = merged.get(section)
        if not isinstance(block, dict) or block.get(key) is not None:
            continue
        block[key] = number
        applied += 1

    if applied:
        source = merged.get("source")
        if isinstance(source, dict):
            source["provider"] = MERGED_PROVIDER_LABEL
            source["partial"] = True
    return merged


def normalize_payload(
    payload: object,
    field_keys: Mapping[str, str],
) -> dict[str, float]:
    """Purely map one FMP response to allowlisted snapshot fields.

    FMP returns a single-element list for the statement endpoints and sometimes
    a bare object; both shapes are accepted, anything else yields nothing.
    """

    row: Mapping[str, Any] | None = None
    if isinstance(payload, list) and payload and isinstance(payload[0], Mapping):
        row = payload[0]
    elif isinstance(payload, Mapping):
        row = payload
    if row is None:
        return {}

    values: dict[str, float] = {}
    for field, key in field_keys.items():
        number = _finite_number(row.get(key))
        if number is not None:
            values[field] = number
    return values


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def fetch_endpoint(
    endpoint: str,
    symbol: str,
    api_key: str,
    *,
    http_get: Callable[..., Any] = requests.get,
) -> object:
    """One FMP request. The key travels in a header and never in an error."""

    if not api_key.strip():
        raise FmpConfigurationError("FMP_API_KEY is not configured.")
    try:
        response = http_get(
            f"{FMP_BASE_URL}/{endpoint}",
            params={"symbol": normalize_symbol(symbol)},
            headers={"apikey": api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except FmpConfigurationError:
        raise
    except Exception:
        # Never include request details: the authorization header is secret.
        raise FmpRequestError(
            f"FMP {endpoint} request failed for {normalize_symbol(symbol)}."
        ) from None


def fetch_fills(
    symbol: str,
    api_key: str,
    needed: Sequence[str],
    *,
    http_get: Callable[..., Any] = requests.get,
    on_request_failure: Callable[[FmpRequestError], None] | None = None,
) -> dict[str, float]:
    """Fetch values for `needed`, one request per endpoint that can serve them.

    Grouped by endpoint, so a name missing both net income and revenue costs one
    request rather than two. An endpoint that fails is skipped: a partial fill
    beats no fill, and the fields it would have answered simply stay null.
    """

    wanted = {field for field in needed if field in FILLABLE_FIELDS}
    if not wanted:
        return {}

    values: dict[str, float] = {}
    for endpoint, field_keys in _ENDPOINTS.values():
        applicable = {
            field: key for field, key in field_keys.items() if field in wanted
        }
        if not applicable:
            continue
        try:
            payload = fetch_endpoint(
                endpoint, symbol, api_key, http_get=http_get
            )
        except FmpRequestError as error:
            if on_request_failure is not None:
                on_request_failure(error)
            continue
        values.update(normalize_payload(payload, applicable))
    return values


def fill_document(
    document: Mapping[str, Any],
    api_key: str,
    *,
    http_get: Callable[..., Any] = requests.get,
    on_request_failure: Callable[[FmpRequestError], None] | None = None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Fill a snapshot's allowlisted nulls. Returns (document, fields filled).

    Makes **zero** requests when nothing allowlisted is null, which is the
    common case -- 98.7% of names on the last run.
    """

    needed = missing_fields(document)
    if not needed:
        return dict(document), ()
    fills = fetch_fills(
        document["ticker"],
        api_key,
        needed,
        http_get=http_get,
        on_request_failure=on_request_failure,
    )
    if not fills:
        return dict(document), ()
    return merge_fill(document, fills), tuple(sorted(fills))
