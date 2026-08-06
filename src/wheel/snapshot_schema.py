"""The Layer 0 snapshot contract: the interface between the data edge and the scorers.

A snapshot is the reproducible market state for one ticker on one date, written
as `YYYY-MM-DD_TICKER.json` — the format `snapshot_ref` points at in the
decision record schema. `wheel_mcp.yahoo` produces it; every Layer 1 scorer
consumes it and nothing else. If a rule cannot be evaluated from a snapshot,
that is a contract gap, not a scorer bug.

Two design rules hold this together:

1. **Data only, no verdicts.** A snapshot records what was observed, including
   what was absent (`null`). It never says "passes ST-SEL-01" — that is Layer 1's
   job, and keeping the judgment out is what makes a snapshot replayable.
2. **Absence is explicit.** Every field a rule needs exists in the contract even
   when the free-data tier cannot fill it. A `null` with a stated reason is
   auditable; a missing key is a silent gap.

The validator is pure stdlib on purpose: no new dependency, and it stays a pure
function of (schema, document) so the golden test needs no network or fixtures.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"

# Rules that no snapshot can satisfy, and why. Layer 1 must not silently score
# these -- it reports them as un-evaluable and lets the operator decide.
#
# ST-SEL-09 and AL-SEL-04 are operator gates, not market data: they are carried
# in `operator_gates` as attestations the operator supplies, never as something
# a provider can answer.
UNSATISFIABLE_AT_LAYER_0 = {
    "ST-SEL-07": "Watchlist size and review cadence are run-level, not per-ticker.",
    "ST-SEL-09": (
        "Willingness to own for twelve months is operator judgment. Carried as "
        "an attestation in operator_gates; never derived."
    ),
    "ST-SEL-11": (
        "Premium as a percent of collateral needs an option chain (premium at "
        "~0.30 delta, 30-45 DTE). Free data cannot price it -- Component B."
    ),
    "ST-SEL-13": (
        "Options liquidity needs bid/ask spread and open interest at target "
        "strikes. Free data proves only that expirations exist -- Component B."
    ),
    "ST-SEL-14": (
        "'No ideal wheel stocks' is a constraint on the system, not a field: "
        "the universe is operator-supplied and cannot be derived."
    ),
    "AL-SEL-01": "Concurrent-position count is portfolio state, not ticker state.",
    "AL-SEL-02": "Derived strike band needs account net_liq -- portfolio state.",
    "AL-SEL-03": "Zone lock needs account net_liq -- portfolio state.",
    "AL-SEL-05": "Zone exit applies to held positions -- portfolio state.",
    "AL-SIZ-01": "Name and sector minimums are portfolio-level aggregates.",
    "AL-SIZ-02": "Sector collateral ceiling is a portfolio-level aggregate.",
}

# Every rule a snapshot CAN serve, mapped to the fields that serve it. The
# golden test asserts this mapping resolves against the schema, so a field
# rename cannot silently orphan a rule.
RULE_FIELD_MAP: Mapping[str, tuple[str, ...]] = {
    "ST-SEL-01": ("fundamentals.net_income_ttm", "fundamentals.operating_cash_flow_ttm"),
    "ST-SEL-02": ("analyst.recommendation_mean", "analyst.analyst_opinions"),
    "ST-SEL-03": ("price.current",),
    "ST-SEL-04": ("price.current",),
    "ST-SEL-05": ("stability.max_single_day_move_1y", "stability.realized_vol_1y"),
    "ST-SEL-06": ("dividend.pays_dividend", "dividend.yield_percent"),
    "ST-SEL-08": ("identity.quote_type",),
    "ST-SEL-10": ("volatility.implied_volatility", "volatility.realized_vol_30d"),
    "ST-SEL-12": ("chart_position.pct_below_two_year_high",),
    "ST-ENT-05": ("earnings.next_earnings_date", "earnings.days_to_earnings"),
    "AL-SEL-04": ("operator_gates.thesis_note_exists",),
    "AL-SEL-06": ("identity.market_cap",),
    "AL-SIZ-03": ("identity.industry",),
    "AL-SIZ-04": ("earnings.next_earnings_date", "earnings.earnings_week"),
}

_NUMBER = ("int", "float")

# Field spec: (type, required, nullable). Type "any" skips the check.
SNAPSHOT_SCHEMA: Mapping[str, Any] = {
    "schema_version": ("str", True, False),
    "snapshot_date": ("date", True, False),
    "ticker": ("str", True, False),
    "source": {
        "provider": ("str", True, False),
        "fetched_at": ("datetime", True, False),
        # True whenever any field below was filled by something other than the
        # named provider. Keeps a mixed-source snapshot from reading as pure.
        "partial": ("bool", True, False),
    },
    "identity": {
        "company_name": ("str", True, True),
        # ST-SEL-08: ETFs are valid candidates and score differently (no
        # earnings, no analyst consensus). The scorer must be able to tell.
        "quote_type": ("str", True, True),
        "sector": ("str", True, True),
        "industry": ("str", True, True),
        "market_cap": (_NUMBER, True, True),
        "currency": ("str", True, True),
        "exchange": ("str", True, True),
    },
    "price": {
        "current": (_NUMBER, True, True),
        "history_start": ("date", True, True),
        "history_end": ("date", True, True),
        "trading_days": ("int", True, True),
    },
    "fundamentals": {
        "net_income_ttm": (_NUMBER, True, True),
        "operating_cash_flow_ttm": (_NUMBER, True, True),
        "revenue_ttm": (_NUMBER, True, True),
    },
    "analyst": {
        "recommendation_mean": (_NUMBER, True, True),
        "recommendation_key": ("str", True, True),
        "analyst_opinions": ("int", True, True),
    },
    "dividend": {
        "pays_dividend": ("bool", True, True),
        "yield_percent": (_NUMBER, True, True),
        "last_ex_date": ("date", True, True),
    },
    # ST-SEL-05 inputs, precomputed at the edge because they are functions of
    # the full history the snapshot does not carry verbatim.
    "stability": {
        "max_single_day_move_1y": (_NUMBER, True, True),
        "realized_vol_1y": (_NUMBER, True, True),
    },
    "volatility": {
        # ST-SEL-10 wants true IV. The free tier has none, so `implied_volatility`
        # stays null and `is_proxy` stays true until Component B fills it. A
        # scorer that reads realized_vol_30d as IV must say so in its output.
        "implied_volatility": (_NUMBER, True, True),
        "realized_vol_30d": (_NUMBER, True, True),
        "is_proxy": ("bool", True, False),
        "proxy_note": ("str", True, True),
    },
    "chart_position": {
        "two_year_high": (_NUMBER, True, True),
        "pct_below_two_year_high": (_NUMBER, True, True),
    },
    # ST-SEL-13 and ST-SEL-11 live here and stay null on free data. The fields
    # exist so Component B fills a contract rather than extending one.
    "options": {
        "has_options": ("bool", True, True),
        "expirations_listed": ("int", True, True),
        "chain_available": ("bool", True, False),
        "bid_ask_spread_at_target": (_NUMBER, True, True),
        "open_interest_at_target": ("int", True, True),
        "premium_pct_of_collateral": (_NUMBER, True, True),
    },
    # ST-ENT-05 needs this for survivors; AL-SIZ-04 needs it for every
    # candidate, which is why it belongs in the snapshot and not in a
    # survivors-only side fetch.
    "earnings": {
        "next_earnings_date": ("date", True, True),
        "days_to_earnings": ("int", True, True),
        "earnings_week": ("str", True, True),
    },
    # Operator attestations. Never provider-derived; null means "not answered",
    # which is distinct from false.
    "operator_gates": {
        "thesis_note_exists": ("bool", True, True),
        "thesis_note_path": ("str", True, True),
        "willing_to_own_12mo": ("bool", True, True),
    },
}


class SnapshotSchemaError(ValueError):
    """Raised when a document does not satisfy the Layer 0 contract."""


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


def _matches(value: Any, expected: str | tuple[str, ...]) -> bool:
    if expected == "any":
        return True
    allowed = (expected,) if isinstance(expected, str) else expected
    actual = _type_name(value)
    if actual in allowed:
        return True
    # An int is an acceptable float; the reverse is not.
    if "float" in allowed and actual == "int":
        return True
    if "date" in allowed and actual == "str":
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    if "datetime" in allowed and actual == "str":
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            return False
    return False


def _validate_object(
    document: Any,
    schema: Mapping[str, Any],
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(document, Mapping):
        errors.append(f"{path or '<root>'}: expected an object, got {_type_name(document)}")
        return

    for key, spec in schema.items():
        where = f"{path}.{key}" if path else key
        present = key in document

        if isinstance(spec, dict):
            if not present:
                errors.append(f"{where}: required object is missing")
                continue
            _validate_object(document[key], spec, where, errors)
            continue

        expected_type, required, nullable = spec
        if not present:
            if required:
                errors.append(f"{where}: required field is missing")
            continue

        value = document[key]
        if value is None:
            if not nullable:
                errors.append(f"{where}: must not be null")
            continue
        if not _matches(value, expected_type):
            wanted = expected_type if isinstance(expected_type, str) else "/".join(expected_type)
            errors.append(f"{where}: expected {wanted}, got {_type_name(value)}")

    for key in document:
        if key not in schema:
            where = f"{path}.{key}" if path else key
            errors.append(f"{where}: unexpected field (the contract is closed)")


def validate_snapshot(document: Any) -> tuple[str, ...]:
    """Return every contract violation in `document`; empty means valid.

    Pure: no clock, no filesystem, no network. Collects all errors rather than
    raising on the first, so a malformed snapshot is diagnosed in one pass.
    """

    errors: list[str] = []
    _validate_object(document, SNAPSHOT_SCHEMA, "", errors)

    if isinstance(document, Mapping):
        version = document.get("schema_version")
        if version is not None and version != SCHEMA_VERSION:
            errors.append(
                f"schema_version: expected {SCHEMA_VERSION!r}, got {version!r}"
            )
        ticker = document.get("ticker")
        if isinstance(ticker, str) and ticker != ticker.upper():
            errors.append("ticker: must be uppercase")

    return tuple(errors)


def assert_valid_snapshot(document: Any) -> None:
    """Raise `SnapshotSchemaError` listing every violation, or return quietly."""

    errors = validate_snapshot(document)
    if errors:
        joined = "\n  - ".join(errors)
        raise SnapshotSchemaError(
            f"Snapshot does not satisfy the Layer 0 contract:\n  - {joined}"
        )


def snapshot_filename(snapshot_date: str, ticker: str) -> str:
    """`YYYY-MM-DD_TICKER.json` -- the name `snapshot_ref` points at."""

    return f"{snapshot_date}_{ticker.upper()}.json"


def resolve_field(document: Mapping[str, Any], dotted: str) -> Any:
    """Read a dotted path such as 'fundamentals.net_income_ttm'."""

    cursor: Any = document
    for part in dotted.split("."):
        if not isinstance(cursor, Mapping) or part not in cursor:
            raise KeyError(dotted)
        cursor = cursor[part]
    return cursor
