"""Static HTML renderer for a frozen weekly screen.

The parser and renderer are pure: markdown + sidecar + configuration values in,
one self-contained HTML string out. Filesystem discovery and writes live only
in ``render_latest`` at the command edge. No provider, network, or live market
data is consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from .config_io import load_config, wheelops_dir
from .monitored import BEYOND_ZONE, SIDECAR_SUFFIX, zone_order


@dataclass(frozen=True)
class Candidate:
    ticker: str
    score: float
    price: float | None
    zone: str
    sector: str
    dividend_yield: float | None
    volatility_percent: float | None
    below_high_percent: float | None
    earnings: str
    flags: tuple[str, ...]
    thesis_backed: bool

    @property
    def collateral(self) -> float | None:
        return self.price * 100.0 if self.price is not None else None


@dataclass(frozen=True)
class WeeklyScreen:
    run_date: str
    candidates: tuple[Candidate, ...]
    funnel: tuple[tuple[str, int], ...]


def _markdown_text(value: str) -> str:
    return re.sub(r"[*_`]", "", value).strip()


def _number(value: str) -> float | None:
    match = re.search(r"-?[0-9][0-9,]*(?:\.[0-9]+)?", value)
    if match is None:
        return None
    return float(match.group(0).replace(",", ""))


def parse_weekly_screen(
    markdown: str,
    sidecar: Mapping[str, Any],
    thesis_tickers: set[str] | frozenset[str] = frozenset(),
) -> WeeklyScreen:
    """Build the display model from the two frozen weekly artifacts. Pure."""

    raw_entries = sidecar.get("entries")
    entries = raw_entries if isinstance(raw_entries, Mapping) else {}
    details: dict[str, tuple[str, ...]] = {}
    in_monitored = False

    for line in markdown.splitlines():
        if line.startswith("## Monitored"):
            in_monitored = True
            continue
        if in_monitored and line.startswith("## "):
            break
        if not in_monitored or not line.startswith("|"):
            continue
        cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        if len(cells) != 9 or cells[0] == "Ticker" or set(cells[0]) == {"-"}:
            continue
        ticker = _markdown_text(cells[0]).upper()
        if ticker in entries:
            details[ticker] = cells

    candidates: list[Candidate] = []
    for ticker, record in entries.items():
        if not isinstance(record, Mapping):
            continue
        symbol = str(ticker).strip().upper()
        cells = details.get(symbol, (symbol, "", "", "", "", "", "", "", ""))
        raw_flags = _markdown_text(cells[8])
        flags = (
            tuple(part.strip() for part in raw_flags.split(",") if part.strip())
            if raw_flags not in ("", "—")
            else ()
        )
        candidates.append(
            Candidate(
                ticker=symbol,
                score=float(record.get("score") or 0.0),
                price=_number(cells[2]),
                zone=str(record.get("zone") or BEYOND_ZONE),
                sector=_markdown_text(cells[3]) or "Unknown",
                dividend_yield=_number(cells[4]),
                volatility_percent=_number(cells[5]),
                below_high_percent=_number(cells[6]),
                earnings=_markdown_text(cells[7]) or "—",
                flags=flags,
                thesis_backed=symbol in thesis_tickers,
            )
        )

    funnel: list[tuple[str, int]] = []
    match = re.search(r"^- Funnel:\s*(.+)$", markdown, re.MULTILINE)
    if match:
        for part in match.group(1).split("→"):
            count = re.search(r"(\d+)\s*$", part.strip())
            if count:
                label = part.strip()[: count.start()].strip()
                funnel.append((label, int(count.group(1))))

    run_date = str(sidecar.get("run_date") or "")
    if not run_date:
        heading = re.search(r"^# Wheel screen — (\d{4}-\d{2}-\d{2})$", markdown, re.MULTILINE)
        run_date = heading.group(1) if heading else "unknown date"

    return WeeklyScreen(
        run_date=run_date,
        candidates=tuple(candidates),
        funnel=tuple(funnel),
    )


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}" if abs(value) >= 100 else f"${value:,.2f}"


def _percent(value: float | None, *, suffix: str = "%") -> str:
    return "—" if value is None else f"{value:.0f}{suffix}"


def _zone_heading(
    zone: str,
    candidates: Sequence[Candidate],
    net_liq: float,
    per_name_cap: float,
) -> tuple[str, str]:
    ceiling = net_liq * per_name_cap / 100.0
    if zone == "Zone 1":
        return "Zone 1", f"Tradeable now · price ≤ {_money(ceiling)}"
    prices = [candidate.price for candidate in candidates if candidate.price is not None]
    unlock = min(prices) * 100.0 / per_name_cap if prices and per_name_cap > 0 else None
    label = "Beyond zones" if zone == BEYOND_ZONE else zone
    return label, f"Locked · nearest visible name unlocks at ~{_money(unlock)}"


def _badge(text: str, kind: str) -> str:
    return f'<span class="badge {kind}">{escape(text)}</span>'


def _candidate_rows(candidates: Sequence[Candidate]) -> str:
    rows: list[str] = []
    for candidate in candidates:
        ticker = escape(candidate.ticker)
        ticker_cell = f"<strong>{ticker}</strong>"
        if candidate.thesis_backed:
            ticker_cell += " " + _badge("thesis", "info")
        flags = " ".join(_badge(flag, "warn") for flag in candidate.flags)
        if not flags:
            flags = _badge("compliant", "good")
        rows.append(
            f'<tr class="{"thesis" if candidate.thesis_backed else ""}">'
            f"<td>{ticker_cell}</td>"
            f'<td class="num score">{candidate.score:.1f}</td>'
            f'<td class="num">{_money(candidate.price)}</td>'
            f"<td>{escape(candidate.sector)}</td>"
            f'<td class="num">{_percent(candidate.dividend_yield)}</td>'
            f'<td class="num">{_percent(candidate.volatility_percent)}</td>'
            f'<td class="num">{_percent(candidate.below_high_percent, suffix="% below")}</td>'
            f"<td>{escape(candidate.earnings)}</td>"
            f"<td>{flags}</td>"
            "</tr>"
        )
    return "".join(rows)


def _candidate_table(candidates: Sequence[Candidate]) -> str:
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Ticker</th><th>Score</th><th>Price</th><th>Sector</th>"
        "<th>Dividend</th><th>Volatility†</th><th>2y high</th>"
        "<th>Earnings</th><th>Status</th>"
        "</tr></thead><tbody>"
        + _candidate_rows(candidates)
        + "</tbody></table></div>"
    )


def _sector_counts(candidates: Sequence[Candidate]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.sector] = counts.get(candidate.sector, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _sector_bars(candidates: Sequence[Candidate]) -> str:
    counts = _sector_counts(candidates)
    maximum = max((count for _, count in counts), default=1)
    palette = ("#2f7d64", "#4878a8", "#b17a2b", "#845f9e", "#a95858", "#51879a")
    bars = []
    for index, (sector, count) in enumerate(counts):
        width = count / maximum * 100.0
        color = palette[index % len(palette)]
        bars.append(
            '<div class="bar-row">'
            f'<div class="bar-label"><span>{escape(sector)}</span><strong>{count}</strong></div>'
            '<div class="bar-track" aria-hidden="true">'
            f'<div class="bar-fill" style="width:{width:.2f}%;background:{color}"></div>'
            "</div></div>"
        )
    return "".join(bars) or '<p class="empty">No monitored candidates.</p>'


def _book_candidates(candidates: Sequence[Candidate]) -> list[Candidate]:
    zone_one = [candidate for candidate in candidates if candidate.zone == "Zone 1"]
    best: dict[str, Candidate] = {}
    for candidate in sorted(zone_one, key=lambda item: -item.score):
        best.setdefault(candidate.sector, candidate)
    return sorted(best.values(), key=lambda item: -item.score)


def _build_book(candidates: Sequence[Candidate]) -> str:
    rows = []
    for candidate in _book_candidates(candidates):
        rows.append(
            "<tr>"
            f"<td><strong>{escape(candidate.ticker)}</strong></td>"
            f"<td>{escape(candidate.sector)}</td>"
            f'<td class="num">{candidate.score:.1f}</td>'
            f'<td class="num">{_money(candidate.price)}</td>'
            f'<td class="num">{_money(candidate.collateral)}</td>'
            "</tr>"
        )
    if not rows:
        return '<p class="empty">No Zone 1 candidates are available for this view.</p>'
    return (
        '<div class="table-wrap"><table><thead><tr><th>Ticker</th><th>Sector</th>'
        "<th>Score</th><th>Price</th><th>1-contract collateral</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _reserve_candidates(candidates: Sequence[Candidate]) -> tuple[list[Candidate], set[str]]:
    zone_one = sorted(
        (candidate for candidate in candidates if candidate.zone == "Zone 1" and candidate.price is not None),
        key=lambda item: (not item.thesis_backed, -item.score, item.ticker),
    )
    diversified = _book_candidates(candidates)
    suggested: list[Candidate] = diversified[:3]
    for candidate in zone_one:
        if candidate not in suggested and len(suggested) < 3:
            suggested.append(candidate)
    return zone_one, {candidate.ticker for candidate in suggested}


def _reserve_picker(candidates: Sequence[Candidate]) -> str:
    available, suggested = _reserve_candidates(candidates)
    choices = []
    for candidate in available:
        checked = " checked" if candidate.ticker in suggested else ""
        choices.append(
            '<label class="pick">'
            f'<input type="checkbox" data-ticker="{escape(candidate.ticker)}" '
            f'data-sector="{escape(candidate.sector)}" data-price="{candidate.price:.8f}"{checked}>'
            f'<span><strong>{escape(candidate.ticker)}</strong><small>{escape(candidate.sector)}</small></span>'
            f'<span class="pick-money">{_money(candidate.collateral)}</span>'
            "</label>"
        )
    return "".join(choices) or '<p class="empty">No priced Zone 1 names to calculate.</p>'


def render_html(
    screen: WeeklyScreen,
    *,
    net_liq: float,
    per_name_cap: float,
) -> str:
    """Render one portable HTML document from an immutable display model."""

    candidates = sorted(
        screen.candidates,
        key=lambda item: (zone_order(item.zone), not item.thesis_backed, -item.score, item.ticker),
    )
    by_zone: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_zone.setdefault(candidate.zone, []).append(candidate)

    zone_sections = []
    for zone in sorted(by_zone, key=zone_order):
        entries = sorted(
            by_zone[zone],
            key=lambda item: (not item.thesis_backed, -item.score, item.ticker),
        )
        heading, status = _zone_heading(zone, entries, net_liq, per_name_cap)
        zone_sections.append(
            '<section class="zone-card">'
            f'<div class="section-heading"><div><p class="eyebrow">Price zone</p><h2>{escape(heading)}</h2></div>'
            f'<span class="zone-status {"open" if zone == "Zone 1" else "locked"}">{escape(status)}</span></div>'
            + _candidate_table(entries)
            + "</section>"
        )

    funnel = "".join(
        f'<div class="metric"><span>{escape(label.title())}</span><strong>{count:,}</strong></div>'
        for label, count in screen.funnel
    )
    monitored = len(candidates)
    sectors = len(_sector_counts(candidates))
    thesis_count = sum(candidate.thesis_backed for candidate in candidates)
    summary = (
        funnel
        + f'<div class="metric"><span>Sectors</span><strong>{sectors}</strong></div>'
        + f'<div class="metric"><span>Thesis-backed</span><strong>{thesis_count}/{monitored}</strong></div>'
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Wheel Engine weekly screen — {escape(screen.run_date)}</title>
<style>
:root{{--bg:#f4f5f6;--surface:#fff;--surface-2:#f8f9fa;--text:#1d252c;--muted:#61707b;--line:#d9dee2;--accent:#256c57;--accent-soft:#e4f1ec;--amber:#9a6417;--amber-soft:#fff3d8;--red:#a63c3c;--red-soft:#fdeaea;--blue:#356e9b;--blue-soft:#e7f0f7}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}button,input{{font:inherit}}.shell{{max-width:1400px;margin:auto;padding:32px}}header{{margin-bottom:24px}}.eyebrow{{margin:0 0 5px;color:var(--accent);font-size:11px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}}h1{{font-size:clamp(26px,4vw,44px);line-height:1.05;margin:0 0 10px;letter-spacing:-.025em}}h2{{font-size:21px;margin:0}}h3{{font-size:18px;margin:0 0 12px}}.lede{{max-width:750px;color:var(--muted);margin:0}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin-top:22px}}.metric{{background:var(--surface);padding:13px 15px}}.metric span{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}}.metric strong{{font-size:20px}}.tabs{{display:flex;gap:6px;border-bottom:1px solid var(--line);margin-bottom:18px;overflow:auto}}.tabs button{{border:0;border-bottom:3px solid transparent;background:transparent;color:var(--muted);padding:11px 15px;cursor:pointer;white-space:nowrap;font-weight:700}}.tabs button[aria-selected="true"]{{color:var(--accent);border-color:var(--accent)}}[role="tabpanel"][hidden]{{display:none}}.zone-card,.panel-card{{background:var(--surface);border:1px solid var(--line);margin-bottom:16px;padding:18px}}.section-heading{{display:flex;justify-content:space-between;align-items:end;gap:12px;margin-bottom:14px}}.zone-status{{font-size:12px;font-weight:700;padding:5px 9px;border:1px solid currentColor}}.zone-status.open{{color:var(--accent);background:var(--accent-soft)}}.zone-status.locked{{color:var(--amber);background:var(--amber-soft)}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:850px}}th,td{{padding:10px 9px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle}}th{{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em}}tbody tr:last-child td{{border-bottom:0}}tr.thesis{{background:var(--accent-soft)}}.num{{font-variant-numeric:tabular-nums;white-space:nowrap}}.score{{font-weight:800;color:var(--accent)}}.badge{{display:inline-block;border:1px solid currentColor;padding:2px 6px;font-size:10px;font-weight:750;white-space:nowrap}}.badge.good{{color:var(--accent);background:var(--accent-soft)}}.badge.warn{{color:var(--amber);background:var(--amber-soft);margin:1px}}.badge.bad{{color:var(--red);background:var(--red-soft)}}.badge.info{{color:var(--blue);background:var(--blue-soft)}}.two-col{{display:grid;grid-template-columns:minmax(300px,.8fr) minmax(500px,1.2fr);gap:16px}}.bar-row{{margin:13px 0}}.bar-label{{display:flex;justify-content:space-between;gap:10px;margin-bottom:5px}}.bar-track{{height:12px;background:var(--surface-2);border:1px solid var(--line)}}.bar-fill{{height:100%;min-width:2px}}.callout{{border-left:4px solid var(--amber);background:var(--amber-soft);padding:12px 14px;margin-top:14px;color:var(--text)}}.calc-grid{{display:grid;grid-template-columns:minmax(260px,.7fr) minmax(500px,1.3fr);gap:16px}}.picker{{display:grid;gap:7px}}.pick{{display:flex;align-items:center;gap:10px;border:1px solid var(--line);padding:10px;cursor:pointer;background:var(--surface)}}.pick:has(input:checked){{border-color:var(--accent);background:var(--accent-soft)}}.pick input{{accent-color:var(--accent)}}.pick span:nth-of-type(1){{display:flex;flex-direction:column;flex:1}}.pick small{{color:var(--muted)}}.pick-money{{font-variant-numeric:tabular-nums}}.reserve-summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:12px}}.reserve-summary div{{background:var(--surface-2);padding:12px}}.reserve-summary span{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase}}.reserve-summary strong{{font-size:19px}}.reserve-summary.breach strong:last-child{{color:var(--red)}}.reserve-summary.safe strong:last-child{{color:var(--accent)}}#capacity-table tr.breach{{background:var(--red-soft)}}#capacity-table tr.warning{{background:var(--amber-soft)}}.empty{{color:var(--muted)}}footer{{border-top:1px solid var(--line);margin-top:28px;padding:18px 0;color:var(--muted);font-size:12px}}.footnote{{color:var(--muted);font-size:12px;margin-top:12px}}
@media(max-width:850px){{.shell{{padding:20px 12px}}.two-col,.calc-grid{{grid-template-columns:1fr}}.section-heading{{align-items:start;flex-direction:column}}}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111619;--surface:#192126;--surface-2:#202a30;--text:#edf1f3;--muted:#a5b0b7;--line:#364249;--accent:#6fc5a7;--accent-soft:#18372e;--amber:#efb85f;--amber-soft:#3a2d17;--red:#ee8888;--red-soft:#3b2022;--blue:#82b6df;--blue-soft:#1d3344}}}}
</style>
</head>
<body>
<div class="shell">
<header><p class="eyebrow">Component A · Weekly screen</p><h1>Wheel Engine <span class="num">{escape(screen.run_date)}</span></h1><p class="lede">A compact view of the monitored tier across account-sized zones. Scores rank rule-compliant inputs; they do not make a trade decision.</p><div class="metrics">{summary}</div></header>
<nav class="tabs" role="tablist" aria-label="Weekly report sections">
<button role="tab" id="tab-candidates" aria-controls="candidates" aria-selected="true">Candidates by zone</button>
<button role="tab" id="tab-sectors" aria-controls="sectors" aria-selected="false">Sector allocation</button>
<button role="tab" id="tab-reserve" aria-controls="reserve" aria-selected="false">Reserve check</button>
</nav>
<main>
<div id="candidates" role="tabpanel" aria-labelledby="tab-candidates">{''.join(zone_sections)}<p class="footnote">† Volatility is the 30-day realized proxy, not implied volatility. Thesis-backed names reflect files present in WheelOps/notes when this report was rendered.</p></div>
<div id="sectors" role="tabpanel" aria-labelledby="tab-sectors" hidden><div class="two-col"><section class="panel-card"><p class="eyebrow">Monitored mix</p><h2>Sector allocation</h2>{_sector_bars(candidates)}</section><section class="panel-card"><p class="eyebrow">Illustrative, not a decision</p><h2>Build a book</h2><p>Highest-scoring Zone 1 name in each represented sector.</p>{_build_book(candidates)}<div class="callout"><strong>AL-SIZ-02 · 50% sector ceiling.</strong> Picking from one sector makes exposure 100% and breaches the ceiling. With only two sectors, exactly equal collateral merely sits at 50% each; any imbalance pushes one sector above the limit. Three or more sectors provide room for unequal position sizes.</div></section></div></div>
<div id="reserve" role="tabpanel" aria-labelledby="tab-reserve" hidden><div class="calc-grid"><section class="panel-card"><p class="eyebrow">One contract each</p><h2>Add Zone 1 assignments</h2><p>Top three suggestions are pre-selected. Change the set to test capacity.</p><div class="picker">{_reserve_picker(candidates)}</div></section><section class="panel-card"><p class="eyebrow">Constitution §1.3</p><h2>Assignment capacity</h2><div class="reserve-summary safe" id="reserve-summary"><div><span>Net liquidity</span><strong>{_money(net_liq)}</strong></div><div><span>Cumulative collateral</span><strong id="total-collateral">$0</strong></div><div><span>Reserve remaining</span><strong id="reserve-percent">100%</strong></div></div><div class="table-wrap"><table id="capacity-table"><thead><tr><th>Added</th><th>Ticker</th><th>Sector</th><th>Collateral</th><th>Cumulative</th><th>Reserve</th><th>Status</th></tr></thead><tbody></tbody></table></div><p class="footnote">The ≥50% reserve floor is tested against assignment collateral and configured net liquidity of {_money(net_liq)}. This calculator does not place or recommend a trade.</p></section></div></div>
</main>
<footer>Wheel Engine weekly screen — {escape(screen.run_date)}. Screen output proposes; the operator decides. Not financial advice.</footer>
</div>
<script>
(()=>{{
const tabs=[...document.querySelectorAll('[role="tab"]')];
const panels=[...document.querySelectorAll('[role="tabpanel"]')];
function openTab(button){{tabs.forEach(tab=>tab.setAttribute('aria-selected',String(tab===button)));panels.forEach(panel=>panel.hidden=panel.id!==button.getAttribute('aria-controls'));}}
tabs.forEach(tab=>tab.addEventListener('click',()=>openTab(tab)));
const net={json.dumps(net_liq)};
const boxes=[...document.querySelectorAll('.pick input')];
const money=value=>new Intl.NumberFormat('en-US',{{style:'currency',currency:'USD',maximumFractionDigits:0}}).format(value);
function updateCapacity(){{
 let total=0,step=0,rows='';
 boxes.filter(box=>box.checked).forEach(box=>{{
  step+=1;const collateral=Number(box.dataset.price)*100;total+=collateral;
  const reserve=(net-total)/net*100;const status=reserve<50?'BREACH':reserve<60?'WARNING':'COMPLIANT';
  const kind=reserve<50?'breach':reserve<60?'warning':'';
  rows+=`<tr class="${{kind}}"><td>${{step}}</td><td><strong>${{box.dataset.ticker}}</strong></td><td>${{box.dataset.sector}}</td><td class="num">${{money(collateral)}}</td><td class="num">${{money(total)}}</td><td class="num">${{reserve.toFixed(0)}}%</td><td><span class="badge ${{reserve<50?'bad':reserve<60?'warn':'good'}}">${{status}}</span></td></tr>`;
 }});
 document.querySelector('#capacity-table tbody').innerHTML=rows||'<tr><td colspan="7" class="empty">Select a candidate to model assignment.</td></tr>';
 document.querySelector('#total-collateral').textContent=money(total);
 const reserve=(net-total)/net*100;document.querySelector('#reserve-percent').textContent=reserve.toFixed(0)+'%';
 document.querySelector('#reserve-summary').className='reserve-summary '+(reserve<50?'breach':'safe');
}}
boxes.forEach(box=>box.addEventListener('change',updateCapacity));updateCapacity();
}})();
</script>
</body></html>
"""
    return html


def latest_report_paths(weeks_dir: Path, run_date: str | None = None) -> tuple[Path, Path]:
    """Resolve the newest markdown/sidecar pair, or one explicit date."""

    if run_date is not None:
        markdown = weeks_dir / f"{run_date}.md"
        sidecar = weeks_dir / f"{run_date}{SIDECAR_SUFFIX}"
        if not markdown.is_file() or not sidecar.is_file():
            raise FileNotFoundError(f"No complete weekly screen for {run_date}.")
        return markdown, sidecar

    candidates = sorted(weeks_dir.glob(f"*{SIDECAR_SUFFIX}"), reverse=True)
    for sidecar in candidates:
        stamp = sidecar.name[: -len(SIDECAR_SUFFIX)]
        markdown = weeks_dir / f"{stamp}.md"
        if markdown.is_file():
            return markdown, sidecar
    raise FileNotFoundError(f"No markdown/sidecar pair found in {weeks_dir}.")


def render_latest(
    config: Mapping[str, Any],
    run_date: str | None = None,
) -> tuple[Path, WeeklyScreen]:
    """Read frozen artifacts, render, and atomically write the portable file."""

    wheelops = wheelops_dir(config)
    weeks_dir = wheelops / "weeks"
    markdown_path, sidecar_path = latest_report_paths(weeks_dir, run_date)
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    ticker_entries = sidecar.get("entries") if isinstance(sidecar, Mapping) else {}
    thesis_tickers = {
        str(ticker).upper()
        for ticker in (ticker_entries or {})
        if (wheelops / "notes" / f"{str(ticker).upper()}.md").is_file()
    }
    screen = parse_weekly_screen(
        markdown_path.read_text(encoding="utf-8"),
        sidecar,
        thesis_tickers,
    )
    account = config["account"]
    output = weeks_dir / f"{screen.run_date}.html"
    temporary = output.with_suffix(".html.tmp")
    temporary.write_text(
        render_html(
            screen,
            net_liq=float(account["net_liq"]),
            per_name_cap=float(account["per_name_cap"]),
        ),
        encoding="utf-8",
    )
    temporary.replace(output)
    return output, screen


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    run_date = arguments[0] if arguments else None
    path, screen = render_latest(load_config("config.yaml"), run_date)
    size = path.stat().st_size
    if size >= 50 * 1024:
        path.unlink()
        raise RuntimeError(f"Rendered report is {size} bytes; limit is under 50KB.")
    print(
        f"RENDERED {path} candidates={len(screen.candidates)} bytes={size}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
