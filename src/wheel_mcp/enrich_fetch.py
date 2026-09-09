"""Layer 0: fetch `info` for the top monitored names and cache the records.

Runs between the screen and the render. The screen decides *which* names
matter and writes them to its sidecar; this module pays one provider call per
name on that short list and hands each response straight to
`wheel.enrich.build_enrichment`, which owns the shaping.

Fetch and write only (AGENTS.md §4). No rule is applied here and no score is
touched -- enrichment is display data, and a name's ranking is identical
whether or not this step ever ran.

    PYTHONPATH=src python -m wheel_mcp.enrich_fetch [YYYY-MM-DD]
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any, Callable, Mapping

from wheel.config_io import load_config, wheelops_dir
from wheel.enrich import (
    EnrichmentConfig,
    build_enrichment,
    empty_enrichment,
    enrichment_config_from_config,
    select_enrichment_targets,
    write_enrichment,
)
from wheel.monitored import SIDECAR_SUFFIX

from .yahoo import (
    DEFAULT_REQUEST_THROTTLE,
    RequestThrottle,
    fetch_ticker_info,
    yfinance_policy_from_config,
)

PROGRESS_EVERY = 10


def latest_sidecar(weeks_dir: Path, run_date: str | None = None) -> Path:
    """The sidecar for one run date, or the newest one on disk."""

    if run_date is not None:
        path = weeks_dir / f"{run_date}{SIDECAR_SUFFIX}"
        if not path.is_file():
            raise FileNotFoundError(f"No monitored sidecar for {run_date}.")
        return path
    candidates = sorted(weeks_dir.glob(f"*{SIDECAR_SUFFIX}"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No monitored sidecar found in {weeks_dir}.")
    return candidates[0]


def enrich_tickers(
    tickers: list[str],
    *,
    wheelops: Path,
    run_date: date,
    fetch_info: Callable[..., Mapping[str, Any]] = fetch_ticker_info,
    policy: Any = None,
    throttle: RequestThrottle = DEFAULT_REQUEST_THROTTLE,
    say: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Fetch and cache one record per ticker; a failure costs one name.

    A provider error writes the all-null record rather than nothing at all, so
    the report shows an expandable card that says the data is missing instead
    of silently omitting a row the operator was looking for.
    """

    written: list[str] = []
    errors: list[tuple[str, str]] = []

    for index, ticker in enumerate(tickers, start=1):
        try:
            keywords: dict[str, Any] = {"throttle": throttle}
            if policy is not None:
                keywords["policy"] = policy
            info = fetch_info(ticker, **keywords)
            document = build_enrichment(ticker, info, fetched_on=run_date)
        except Exception as error:  # provider failure is expected, not fatal
            errors.append((ticker, f"{type(error).__name__}: {error}"))
            document = empty_enrichment(ticker, fetched_on=run_date)
        write_enrichment(wheelops, run_date, document)
        written.append(document["ticker"])
        if index % PROGRESS_EVERY == 0 or index == len(tickers):
            say(f"  ENRICHED {index}/{len(tickers)}")

    return {"written": written, "errors": errors}


def run_enrichment(
    config: Mapping[str, Any],
    run_date: str | None = None,
    *,
    fetch_info: Callable[..., Mapping[str, Any]] = fetch_ticker_info,
    say: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Read the screen's sidecar, enrich its top names, write the cache."""

    wheelops = wheelops_dir(config)
    sidecar_path = latest_sidecar(wheelops / "weeks", run_date)
    stamp = sidecar_path.name[: -len(SIDECAR_SUFFIX)]
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Unreadable sidecar {sidecar_path}: {error}") from error

    settings: EnrichmentConfig = enrichment_config_from_config(config)
    tickers = select_enrichment_targets(sidecar, settings)
    say(
        f"ENRICH {stamp} top_n={settings.top_n} "
        f"include_locked_zones={settings.include_locked_zones} "
        f"targets={len(tickers)}"
    )

    result = enrich_tickers(
        tickers,
        wheelops=wheelops,
        run_date=date.fromisoformat(stamp),
        fetch_info=fetch_info,
        policy=yfinance_policy_from_config(config),
        say=say,
    )
    for ticker, reason in result["errors"]:
        say(f"  FETCH-ERROR {ticker}: {reason}")
    result["run_date"] = stamp
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    run_date = arguments[0] if arguments else None
    config = load_config("config.yaml")
    result = run_enrichment(config, run_date)
    print(
        f"ENRICHED {result['run_date']} names={len(result['written'])} "
        f"errors={len(result['errors'])}",
        flush=True,
    )
    # A run that enriched nothing is not a failure -- an empty monitored tier
    # is a legitimate week. Only a run that could not read the sidecar is, and
    # that already raised above.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
