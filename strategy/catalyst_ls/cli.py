"""Command line: `python -m catalyst_ls scan` and `python -m catalyst_ls backtest`."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

import json

from . import backtest, config, dashboard, metrics, prices, universe
from .screen import Candidate, Screener
from .sec import SecClient

OUTPUT = Path(__file__).resolve().parent.parent / "output"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _setup(cfg: dict, start: pd.Timestamp, tickers: list[str] | None):
    sec = SecClient(cfg["data"]["cache_dir"], cfg["data"]["sec_user_agent"], cfg["data"]["sec_max_requests_per_second"])
    log("Loading universe and SEC fundamentals (first run downloads several GB; later runs use the cache)...")
    u = universe.build(cfg, sec, tickers, log=log)
    log(f"  {len(u.companies)} companies with XBRL fundamentals"
        + (f"; {len(u.unmapped_sp500)} historical S&P 500 members could not be mapped (delisted/renamed)" if u.unmapped_sp500 else ""))
    price_start = (start - pd.Timedelta(days=420)).date().isoformat()
    log("Downloading prices from Yahoo Finance...")
    panel = prices.download(list(u.companies) + cfg["backtest"]["benchmarks"], price_start, cfg["data"]["cache_dir"])
    missing = [t for t in u.companies if t not in panel.adj_close.columns or panel.adj_close[t].dropna().empty]
    if missing:
        log(f"  no Yahoo prices for {len(missing)} tickers (dropped)")
    return sec, u, panel


def cmd_scan(args, cfg):
    asof = pd.Timestamp(args.date or date.today())
    sec, u, panel = _setup(cfg, asof, args.tickers)
    screener = Screener(u, panel.features(cfg), cfg, insider_fetch=sec.archive_document)
    longs, shorts = screener.screen(asof)
    held = _load_positions(args.positions)
    exits = []
    cutoff = screener.runup_cutoff(screener._eligible(asof))
    for p in held:
        ok, reasons = screener.setup_holds(prices.yahoo_symbol(p["ticker"]), p["side"], asof, cutoff)
        exits.append((p, ok, reasons))
    text = render_scan(asof, longs, shorts, exits, cfg)
    OUTPUT.mkdir(exist_ok=True)
    out = OUTPUT / f"scan_{asof.date()}.md"
    out.write_text(text)
    (OUTPUT / f"scan_{asof.date()}.json").write_text(json.dumps(dashboard.scan_json(asof, longs, shorts, exits, cfg)))
    print(text)
    log(f"Saved {out}")


def cmd_backtest(args, cfg):
    start = pd.Timestamp(args.start or cfg["backtest"]["start"])
    end = pd.Timestamp(args.end) if args.end else None
    sec, u, panel = _setup(cfg, start, args.tickers)
    fetch = sec.archive_document if not args.no_insiders else None
    screener = Screener(u, panel.features(cfg), cfg, insider_fetch=fetch)
    rf = prices.risk_free(cfg["data"]["cache_dir"], start.date().isoformat(), cfg["costs"]["fallback_risk_free"])
    result = backtest.run(screener, panel.adj_open, panel.adj_close, cfg, rf, start, end, log=log if args.verbose else None)
    bench = {b: panel.adj_close[b] for b in cfg["backtest"]["benchmarks"] if b in panel.adj_close}
    text = metrics.report(result, bench, rf if not rf.empty else cfg["costs"]["fallback_risk_free"], cfg)
    text += "\n## Known biases\n\n" + KNOWN_BIASES.format(unmapped=len(u.unmapped_sp500))
    OUTPUT.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    (OUTPUT / f"backtest_{stamp}.md").write_text(text)
    pd.DataFrame([t.__dict__ for t in result.trades]).to_csv(OUTPUT / f"backtest_{stamp}_trades.csv", index=False)
    result.equity.to_csv(OUTPUT / f"backtest_{stamp}_equity.csv", header=["equity"])
    rf_for_stats = rf if not rf.empty else cfg["costs"]["fallback_risk_free"]
    (OUTPUT / f"backtest_{stamp}.json").write_text(json.dumps(dashboard.backtest_json(result, bench, rf_for_stats, cfg)))
    print(text)
    log(f"Saved reports to {OUTPUT}")


KNOWN_BIASES = """\
- **Survivorship**: Nasdaq names come from today's listing, and Yahoo has no prices for most delisted
  tickers ({unmapped} historical S&P 500 members could not be mapped). This flatters the long book and
  removes the best historical shorts (companies that went bust).
- **Fundamentals** are point-in-time (first-filed values, available from the filing date), but tag
  coverage varies by company; Q4 values and cash-flow quarters are derived from year-to-date figures.
- **Catalysts** are limited to what EDGAR publishes for free; estimate revisions and guidance are missing.
- **Costs** use placeholder CFD spread and financing rates from config.yaml, not your actual eToro/IG rates.
- **Your discretionary final call is not modelled**: this measures the rules only.
"""


def render_scan(asof, longs: list[Candidate], shorts: list[Candidate], exits, cfg) -> str:
    n = cfg["portfolio"]["max_positions_per_side"]
    pairs = min(n, len(longs), len(shorts)) if cfg["portfolio"]["require_pair"] else None
    lines = [f"# Scan {asof.date()}", ""]
    if pairs is not None:
        lines.append(f"Paired trades available: **{pairs}** (longs {len(longs)}, shorts {len(shorts)}; "
                     "a long is only taken with a short)")
    lines.append("")
    for title, cands in (("Long candidates", longs), ("Short candidates", shorts)):
        lines += [f"## {title}", ""]
        if not cands:
            lines += ["None today.", ""]
        for i, c in enumerate(cands[:10], 1):
            size = backtest.size_for(c, cfg)
            lines.append(f"### {i}. {c.ticker} — {c.name} ({c.sector})")
            lines.append(f"Score {c.score:.2f} · catalyst {c.catalyst_score:.2f} · price ${c.price:,.2f} · "
                         f"market cap ${c.market_cap / 1e9:,.1f}B · suggested size ${size:,.0f}")
            lines += [f"- {r}" for r in c.reasons]
            lines += [f"- Catalyst: {e.date.date()} {e.detail} ([filing]({e.url}))" for e in c.events] or ["- Catalyst: none"]
            lines.append("")
    if exits:
        lines += ["## Open positions", ""]
        for p, ok, reasons in exits:
            verdict = "HOLD" if ok else "**EXIT** (setup failed)"
            lines.append(f"### {p['ticker']} {p['side']}: {verdict}")
            lines += [f"- {r}" for r in reasons]
            lines.append("")
    return "\n".join(lines)


def _load_positions(path: str | None) -> list[dict]:
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "positions.yaml"
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    return data.get("positions") or []


def cmd_dashboard(args, cfg):
    path = dashboard.build(cfg, OUTPUT, data_access=args.data_access)
    log(f"Saved {path}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="catalyst_ls")
    ap.add_argument("--config", help="path to config.yaml")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a config value, e.g. --set long.revenue_growth_basis=yoy")
    ap.add_argument("--tickers", nargs="+", help="restrict to these tickers (quick tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="rank today's long and short candidates and check open positions")
    s.add_argument("--date", help="scan as of this date (default today)")
    s.add_argument("--positions", help="positions YAML (default strategy/positions.yaml)")
    b = sub.add_parser("backtest", help="run the historical backtest")
    b.add_argument("--start")
    b.add_argument("--end")
    b.add_argument("--no-insiders", action="store_true", help="skip Form 4 downloads (faster, fewer catalysts)")
    b.add_argument("--verbose", action="store_true")
    d = sub.add_parser("dashboard", help="build output/dashboard.html from the latest scan and backtest")
    d.add_argument("--data-access", default="ok", choices=["ok", "blocked", "unknown"],
                   help="shown on the dashboard's status bar")
    args = ap.parse_args(argv)
    cfg = config.load(args.config, args.set)
    {"scan": cmd_scan, "backtest": cmd_backtest, "dashboard": cmd_dashboard}[args.cmd](args, cfg)
