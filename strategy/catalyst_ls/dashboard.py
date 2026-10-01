"""Dashboard data: JSON snapshots of scans and backtests, plus the HTML page built from them."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, metrics, synthetic
from .config import DEFAULT_PATH
from .screen import Candidate, Screener

TEMPLATE = Path(__file__).with_name("dashboard_template.html")


def _clean(x):
    """JSON-safe: NaN/inf -> None, numpy scalars -> Python, timestamps -> ISO dates."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.date().isoformat()
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def candidate_json(c: Candidate, cfg: dict) -> dict:
    return {
        "ticker": c.ticker, "name": c.name, "sector": c.sector, "side": c.side, "score": c.score,
        "catalyst_score": c.catalyst_score, "price": c.price, "market_cap": c.market_cap,
        "size_usd": backtest.size_for(c, cfg), "reasons": c.reasons,
        "events": [{"date": e.date, "kind": e.kind, "detail": e.detail, "url": e.url} for e in c.events],
    }


def scan_json(asof, longs, shorts, exits, cfg) -> dict:
    n = cfg["portfolio"]["max_positions_per_side"]
    return _clean({
        "date": asof,
        "pairs_available": min(n, len(longs), len(shorts)),
        "longs": [candidate_json(c, cfg) for c in longs[:10]],
        "shorts": [candidate_json(c, cfg) for c in shorts[:10]],
        "positions": [{"position": p, "hold": ok, "reasons": r} for p, ok, r in exits],
    })


def _weekly(series: pd.Series) -> list:
    s = series.dropna()
    s = s.groupby(s.index.to_period("W-FRI")).last()
    return [[p.end_time.date().isoformat(), round(float(v), 4)] for p, v in s.items()]


def backtest_json(result, bench: dict[str, pd.Series], rf, cfg) -> dict:
    ret = metrics.strategy_returns(result, cfg)
    stats = {"Strategy": metrics.stats(ret, rf)}
    curves = {"Strategy": (1 + ret).cumprod() * 100}
    for name, px in bench.items():
        r = px.reindex(ret.index).ffill().pct_change(fill_method=None).fillna(0)
        stats[name] = metrics.stats(r, rf)
        curves[name] = (1 + r).cumprod() * 100
    return _clean({
        "period": [ret.index[0], ret.index[-1]],
        "stats": stats,
        "curves": {k: _weekly(v) for k, v in curves.items()},
        "trade_stats": metrics.trade_stats(result.trades),
        "invested_share": float((result.gross_exposure > 0).mean()),
        "trades": [t.__dict__ for t in result.trades][-200:],
        "exit_mode": cfg["portfolio"]["exit_mode"],
    })


def example_json(cfg: dict) -> dict:
    """Run the real screener and backtest on the synthetic scenario and record what happened."""
    idx, panel, u = synthetic.example_scenario(long_rev_growth_q=0.32)
    screener = Screener(u, panel.features(cfg), cfg)
    res = backtest.run(screener, panel.adj_open, panel.adj_close, cfg, None, idx[300], idx[-1])
    legs = {t.side: t for t in res.trades if t.ticker in ("AAA", "BBB")}
    if set(legs) != {"long", "short"}:
        return {"error": "example scenario produced no paired trade with the current config"}
    entry = legs["long"].entry_date
    signal = idx[idx < entry][-1]
    longs, shorts = screener.screen(signal)
    picked = {c.ticker: c for c in longs + shorts}
    exit_day = max(t.exit_date for t in legs.values())
    window = idx[(idx >= signal - pd.Timedelta(days=120)) & (idx <= exit_day + pd.Timedelta(days=60))]
    costs = sum(t.pnl for t in res.trades) - float(res.daily_pnl.sum())
    signals = [s for s in res.signals if signal - pd.Timedelta(days=35) <= s["date"] <= exit_day + pd.Timedelta(days=10)]
    out = {"signal_date": signal, "costs": costs, "net_pnl": float(res.daily_pnl.sum()),
           "signals": signals, "legs": {}}
    for side, t in legs.items():
        c = picked[t.ticker]
        out["legs"][side] = {
            **candidate_json(c, cfg),
            "entry_date": t.entry_date, "entry_price": t.entry_price, "exit_date": t.exit_date,
            "exit_price": t.exit_price, "exit_reason": t.exit_reason, "pnl": t.pnl, "notional": t.notional,
            "prices": [[d.date().isoformat(), round(float(panel.adj_close.at[d, t.ticker]), 2)] for d in window],
        }
    return _clean(out)


def unconfirmed(config_path: Path = DEFAULT_PATH) -> list[dict]:
    """Settings marked UNCONFIRMED in config.yaml, with their comment."""
    out, section = [], ""
    for line in Path(config_path).read_text().splitlines():
        top = re.match(r"^(\w[\w ]*):\s*(?:#\s*(.*))?$", line)
        if top:
            section = top.group(1)
        if "UNCONFIRMED" not in line or line.lstrip().startswith("#"):
            continue
        note = re.sub(r",?\s*UNCONFIRMED[:,]?\s*", " ", line.split("#", 1)[1]).strip(" :,")
        if top:
            out.append({"key": f"{section} (all)", "value": "", "note": note})
            continue
        km = re.match(r"^\s*([\w ]+):\s*([^#]*?)\s*#", line)
        if km:
            out.append({"key": f"{section}.{km.group(1).strip()}", "value": km.group(2), "note": note})
    out.append({"key": "sector_thresholds (non-tech sectors)", "value": "see table",
                "note": "growth thresholds for energy, materials, industrials, staples, utilities, real estate"})
    out.append({"key": "financials", "value": "ROE-based rules", "note": "rules for banks, lenders and BNPL"})
    return out


def _latest(output: Path, prefix: str) -> dict | None:
    files = sorted(output.glob(f"{prefix}_*.json"))
    return json.loads(files[-1].read_text()) if files else None


def build(cfg: dict, output: Path, data_access: str = "unknown") -> Path:
    public_cfg = {k: v for k, v in cfg.items() if k != "data"}
    data = _clean({
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "data_access": data_access,
        "config": public_cfg,
        "unconfirmed": unconfirmed(),
        "scan": _latest(output, "scan"),
        "backtest": _latest(output, "backtest"),
        "example": example_json(cfg),
    })
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    output.mkdir(exist_ok=True)
    path = output / "dashboard.html"
    path.write_text(html)
    return path
