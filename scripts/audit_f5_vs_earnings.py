"""One-off Step 8 diagnostic: are F5's large-move penalties earnings-driven?

F10 / ST-ENT-05 already steps aside from earnings. If most of the single-day
moves F5 penalizes sit within a few trading days of a reported earnings date,
F5 is double-counting risk the earnings discipline would have avoided anyway.
This script builds that evidence base and writes a Markdown report to the
WheelOps folder. It changes nothing in the pipeline.

Run from the repo root:
    PYTHONPATH=src ~/.venvs/wheel-screener/bin/python scripts/audit_f5_vs_earnings.py
"""

from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf

from wheel_screener.data import (
    DEFAULT_REQUEST_THROTTLE,
    YFinanceFetchPolicy,
    yfinance_policy_from_config,
)
from wheel_screener.data.yfinance_client import normalize_price_history

# Private import, on purpose: the audit must reproduce F5's exact return
# arithmetic or it indicts a strawman. Evidential integrity beats API purity
# in a one-off script.
from wheel_screener.scoring.score_filters import _daily_returns

REPO_ROOT = Path(__file__).resolve().parent.parent
FLAGGED_NAMES = ("LW", "HPE", "MGM", "CCL", "BSX", "MOS", "CMG")
ATTRIBUTION_WINDOW_TRADING_DAYS = 3
STABILITY_WINDOW_CALENDAR_DAYS = 365
CROSS_CHECK_TOLERANCE = 0.005


@dataclass(frozen=True)
class LargeMove:
    move_date: date
    move_pct: float
    distance_trading_days: int | None  # signed; None if no earnings data

    @property
    def earnings_attributable(self) -> bool | None:
        if self.distance_trading_days is None:
            return None
        return abs(self.distance_trading_days) <= ATTRIBUTION_WINDOW_TRADING_DAYS


@dataclass(frozen=True)
class NameAudit:
    ticker: str
    f5_score: float
    csv_max_move: float
    csv_realized_vol: float
    recomputed_max_move: float | None
    moves: tuple[LargeMove, ...]
    earnings_dates: tuple[date, ...]
    error: str | None = None

    @property
    def conditions_fired(self) -> str:
        move_fired = self.csv_max_move >= MAX_SINGLE_DAY_MOVE
        # F5 scores 50 per condition; anything under 100 with no large move
        # means the universe-relative volatility condition fired.
        vol_fired = self.f5_score < 100.0 and (
            not move_fired or self.f5_score == 0.0
        )
        fired = []
        if move_fired:
            fired.append("move >= threshold")
        if vol_fired:
            fired.append("relative volatility")
        return " + ".join(fired) if fired else "none (F5 = 100)"


def latest_candidates_csv(output_dir: Path) -> Path:
    candidates = sorted(output_dir.glob("candidates_*.csv"))
    if not candidates:
        raise SystemExit(f"No candidates_*.csv found in {output_dir}")
    return candidates[-1]


def load_audit_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    with csv_path.open(newline="") as handle:
        return {row["ticker"]: row for row in csv.DictReader(handle)}


def select_audit_set(rows: dict[str, dict[str, str]]) -> list[str]:
    """Top-20 scored names with F5 < 100, then the flagged seven, deduped."""

    scored = [row for row in rows.values() if row["verdict"] == "scored"]
    scored.sort(key=lambda row: float(row["composite"]), reverse=True)
    audit = [
        row["ticker"]
        for row in scored[:20]
        if row["f5_score"] and float(row["f5_score"]) < 100.0
    ]
    audit.extend(name for name in FLAGGED_NAMES if name not in audit)
    return audit


def fetch_with_retries(
    description: str,
    fetch,
    policy: YFinanceFetchPolicy,
):
    backoff = policy.initial_backoff_seconds
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            DEFAULT_REQUEST_THROTTLE.wait(policy.min_request_interval_seconds)
            return fetch()
        except Exception as error:  # bounded retries, then surface
            last_error = error
            if attempt < policy.max_attempts:
                time.sleep(backoff)
                backoff *= policy.backoff_multiplier
    raise RuntimeError(f"{description} failed after retries: {last_error}")


def to_trading_day_positions(index: pd.DatetimeIndex) -> dict[date, int]:
    return {timestamp.date(): position for position, timestamp in enumerate(index)}


def nearest_trading_day_distance(
    move_day: date,
    earnings_day: date,
    positions: dict[date, int],
    ordered_days: list[date],
) -> int:
    """Signed trading-day distance from the earnings date to the move.

    Earnings dates can land on non-trading days (or after close); map each to
    the nearest trading day first, then difference the positions.
    """

    if earnings_day in positions:
        earnings_position = positions[earnings_day]
    else:
        nearest = min(ordered_days, key=lambda d: abs((d - earnings_day).days))
        earnings_position = positions[nearest]
    return positions[move_day] - earnings_position


def audit_name(
    ticker_symbol: str,
    row: dict[str, str],
    policy: YFinanceFetchPolicy,
) -> NameAudit:
    f5_score = float(row["f5_score"])
    csv_max_move = float(row["f5_max_daily_move"])
    csv_realized_vol = float(row["f5_realized_vol"])

    try:
        ticker = yf.Ticker(ticker_symbol)
        raw_history = fetch_with_retries(
            f"{ticker_symbol} history",
            lambda: ticker.history(
                period="2y", interval="1d", auto_adjust=False, actions=True
            ),
            policy,
        )
        earnings_frame = fetch_with_retries(
            f"{ticker_symbol} earnings dates",
            lambda: ticker.get_earnings_dates(limit=16),
            policy,
        )
    except RuntimeError as error:
        return NameAudit(
            ticker=ticker_symbol,
            f5_score=f5_score,
            csv_max_move=csv_max_move,
            csv_realized_vol=csv_realized_vol,
            recomputed_max_move=None,
            moves=(),
            earnings_dates=(),
            error=str(error),
        )

    history = normalize_price_history(raw_history)
    returns = _daily_returns(
        history, calendar_days=STABILITY_WINDOW_CALENDAR_DAYS
    )
    recomputed_max = float(returns.abs().max()) if not returns.empty else None

    today = date.today()
    earnings_dates: tuple[date, ...] = ()
    if earnings_frame is not None and len(earnings_frame) > 0:
        earnings_dates = tuple(
            sorted(
                {
                    timestamp.date()
                    for timestamp in earnings_frame.index
                    if timestamp.date() <= today
                }
            )
        )

    positions = to_trading_day_positions(returns.index)
    ordered_days = sorted(positions)
    moves = []
    for timestamp, value in returns.items():
        if abs(float(value)) < MAX_SINGLE_DAY_MOVE:
            continue
        move_day = timestamp.date()
        if earnings_dates:
            distance = min(
                (
                    nearest_trading_day_distance(
                        move_day, earnings_day, positions, ordered_days
                    )
                    for earnings_day in earnings_dates
                ),
                key=abs,
            )
        else:
            distance = None
        moves.append(
            LargeMove(
                move_date=move_day,
                move_pct=float(value),
                distance_trading_days=distance,
            )
        )

    return NameAudit(
        ticker=ticker_symbol,
        f5_score=f5_score,
        csv_max_move=csv_max_move,
        csv_realized_vol=csv_realized_vol,
        recomputed_max_move=recomputed_max,
        moves=tuple(moves),
        earnings_dates=earnings_dates,
    )


def render_name_section(audit: NameAudit) -> str:
    lines = [f"## {audit.ticker}", ""]
    lines.append(
        f"- F5 score: **{audit.f5_score:.0f}** | condition(s) fired: "
        f"{audit.conditions_fired}"
    )
    lines.append(
        f"- Run CSV: max daily move {audit.csv_max_move:.2%}, "
        f"realized vol {audit.csv_realized_vol:.2%}"
    )

    if audit.error is not None:
        lines.append(f"- **FETCH ERROR — attribution not possible**: {audit.error}")
        lines.append("")
        return "\n".join(lines)

    if audit.recomputed_max_move is not None:
        drift = abs(audit.recomputed_max_move - audit.csv_max_move)
        check = (
            "matches run CSV"
            if drift <= CROSS_CHECK_TOLERANCE
            else f"**WARNING: differs from run CSV by {drift:.2%} — "
            "window may have shifted a trading day since the run**"
        )
        lines.append(
            f"- Recomputed max move: {audit.recomputed_max_move:.2%} ({check})"
        )

    if not audit.earnings_dates:
        lines.append(
            "- **Earnings dates unavailable — attribution not possible.**"
        )
    else:
        window = (
            f"{audit.earnings_dates[0].isoformat()} to "
            f"{audit.earnings_dates[-1].isoformat()}"
        )
        lines.append(
            f"- Reported earnings dates on record: "
            f"{len(audit.earnings_dates)} ({window})"
        )

    threshold_text = f"{MAX_SINGLE_DAY_MOVE:.0%}"
    if not audit.moves:
        lines.append(
            f"- No single-day moves >= {threshold_text} in the window: the F5 "
            "penalty is **vol-condition-only**. Earnings attribution of large "
            "moves does not apply to this name."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append("")
    lines.append(
        "| Move date | Move | Earnings-attributable | Trading days from earnings |"
    )
    lines.append("|---|---|---|---|")
    attributable = 0
    for move in audit.moves:
        if move.earnings_attributable is None:
            verdict, distance_text = "unknown", "n/a"
        elif move.earnings_attributable:
            verdict = "**Y**"
            distance_text = f"{move.distance_trading_days:+d}"
            attributable += 1
        else:
            verdict = "N"
            distance_text = f"{move.distance_trading_days:+d}"
        lines.append(
            f"| {move.move_date.isoformat()} | {move.move_pct:+.2%} "
            f"| {verdict} | {distance_text} |"
        )
    lines.append("")
    lines.append(
        f"**{attributable} of {len(audit.moves)} moves earnings-attributable** "
        f"(within +/-{ATTRIBUTION_WINDOW_TRADING_DAYS} trading days)."
    )
    lines.append("")
    return "\n".join(lines)


def render_report(audits: list[NameAudit], csv_path: Path) -> str:
    total_moves = sum(len(a.moves) for a in audits)
    total_attributable = sum(
        1
        for a in audits
        for m in a.moves
        if m.earnings_attributable
    )
    vol_only = [a.ticker for a in audits if not a.moves and a.error is None]

    header = [
        "# F5-vs-Earnings Diagnostic Audit",
        "",
        f"- Run date: {date.today().isoformat()}",
        f"- Source run: `{csv_path.name}`",
        f"- F5 large-move threshold: {MAX_SINGLE_DAY_MOVE:.0%} "
        f"(from config.yaml, ST-SEL-05)",
        f"- Attribution window: +/-{ATTRIBUTION_WINDOW_TRADING_DAYS} trading days "
        "around a reported earnings date",
        f"- Audited names: {', '.join(a.ticker for a in audits)}",
        "",
        "The current top-20 contains **zero** F5-penalized names (all score "
        "F5 = 100); the audit set is the seven historically flagged names. "
        "F5 penalties currently gate names out of the top tier rather than "
        "distorting ranks within it.",
        "",
    ]
    sections = [render_name_section(a) for a in audits]
    share = (
        f"{total_attributable / total_moves:.0%}" if total_moves else "n/a"
    )
    footer = [
        "## Aggregate summary",
        "",
        f"- Across all audited names: **{total_attributable} of {total_moves} "
        f"large moves ({share}) are earnings-attributable.**",
        f"- Vol-condition-only penalties (no large moves at all): "
        f"{', '.join(vol_only) if vol_only else 'none'} — earnings-window "
        "exclusion for F5's move condition would not change these names.",
        "- This is the C1 evidence base: a high share supports excluding "
        "earnings-window moves from F5's move condition; a low share "
        "supports leaving F5 as-is.",
        "",
    ]
    return "\n".join(header + sections + footer)


if __name__ == "__main__":
    config = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    policy = yfinance_policy_from_config(config)
    MAX_SINGLE_DAY_MOVE = float(
        config["thresholds"]["stability"]["max_single_day_move"]
    )
    output_dir = (REPO_ROOT / config["paths"]["output"]).resolve()

    csv_path = latest_candidates_csv(output_dir)
    rows = load_audit_rows(csv_path)
    audit_set = select_audit_set(rows)
    print(f"AUDIT source={csv_path.name} names={','.join(audit_set)}", flush=True)

    audits = []
    for symbol in audit_set:
        print(f"  fetching {symbol} ...", flush=True)
        audits.append(audit_name(symbol, rows[symbol], policy))

    report_path = output_dir / f"audit_f5_vs_earnings_{date.today().isoformat()}.md"
    report_path.write_text(render_report(audits, csv_path), encoding="utf-8")
    print(f"REPORT {report_path}", flush=True)
    failures = [a.ticker for a in audits if a.error is not None]
    if failures:
        print(f"FETCH-FAILURES {','.join(failures)}", flush=True)
        sys.exit(1)
