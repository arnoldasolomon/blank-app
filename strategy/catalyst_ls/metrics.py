"""Performance statistics and the backtest report."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def stats(returns: pd.Series, rf: pd.Series | float = 0.0) -> dict:
    r = returns.dropna()
    if r.empty:
        return {}
    rf_daily = (rf.reindex(r.index).ffill().fillna(0) if isinstance(rf, pd.Series) else pd.Series(rf, index=r.index)) / TRADING_DAYS
    excess = r - rf_daily
    curve = (1 + r).cumprod()
    years = len(r) / TRADING_DAYS
    dd = curve / curve.cummax() - 1
    downside = np.sqrt((excess.clip(upper=0) ** 2).mean()) * np.sqrt(TRADING_DAYS)
    cagr = curve.iloc[-1] ** (1 / years) - 1 if years > 0 and curve.iloc[-1] > 0 else np.nan
    return {
        "total_return": curve.iloc[-1] - 1,
        "cagr": cagr,
        "volatility": r.std() * np.sqrt(TRADING_DAYS),
        "sharpe": excess.mean() / excess.std() * np.sqrt(TRADING_DAYS) if excess.std() > 0 else np.nan,
        "sortino": excess.mean() * TRADING_DAYS / downside if downside and downside > 0 else np.nan,
        "max_drawdown": dd.min(),
        "calmar": cagr / -dd.min() if dd.min() < 0 else np.nan,
    }


def trade_stats(trades) -> dict:
    if not trades:
        return {"trades": 0}
    df = pd.DataFrame([t.__dict__ for t in trades])
    df["ret"] = df["pnl"] / df["notional"]
    df["days"] = (df["exit_date"] - df["entry_date"]).dt.days
    out = {"trades": len(df), "win_rate": (df["pnl"] > 0).mean(), "avg_trade_return": df["ret"].mean(),
           "avg_holding_days": df["days"].mean()}
    for side in ("long", "short"):
        s = df[df["side"] == side]
        out[f"{side}_trades"] = len(s)
        out[f"{side}_win_rate"] = (s["pnl"] > 0).mean() if len(s) else np.nan
        out[f"{side}_pnl"] = s["pnl"].sum()
    return out


def report(result, benchmarks: dict[str, pd.Series], rf: pd.Series | float, cfg: dict) -> str:
    capital = float(cfg["portfolio"]["capital_usd"])
    prev_equity = result.equity.shift(1).fillna(capital)
    strat_ret = result.daily_pnl / prev_equity
    rows = {"Strategy": stats(strat_ret, rf)}
    for name, px in benchmarks.items():
        px = px.reindex(strat_ret.index).ffill()
        rows[name] = stats(px.pct_change(fill_method=None).fillna(0), rf)
    table = pd.DataFrame(rows).T
    fmt = {"total_return": "{:.1%}", "cagr": "{:.1%}", "volatility": "{:.1%}", "sharpe": "{:.2f}",
           "sortino": "{:.2f}", "max_drawdown": "{:.1%}", "calmar": "{:.2f}"}
    for col, f in fmt.items():
        if col in table:
            table[col] = table[col].map(lambda v, f=f: f.format(v) if pd.notna(v) else "n/a")

    ts = trade_stats(result.trades)
    invested = (result.gross_exposure > 0).mean()
    lines = [
        "# Backtest report", "",
        f"Period: {strat_ret.index[0].date()} to {strat_ret.index[-1].date()}  ",
        f"Capital base: ${capital:,.0f}; max position ${cfg['portfolio']['max_position_usd']:,}; "
        f"max {cfg['portfolio']['max_positions_per_side']} per side; exit mode `{cfg['portfolio']['exit_mode']}`  ",
        f"Invested {invested:.0%} of trading days; average gross exposure when invested "
        f"${result.gross_exposure[result.gross_exposure > 0].mean():,.0f}", "",
        _md_table(table), "",
        "## Trades", "",
    ]
    for k, v in ts.items():
        lines.append(f"- {k}: {v:.2%}" if "rate" in k or "return" in k else f"- {k}: {v:,.1f}" if isinstance(v, float) else f"- {k}: {v}")
    if ts.get("trades", 0) < 30:
        lines += ["", f"**Warning: only {ts.get('trades', 0)} trades. Too few to judge the Sharpe ratio; "
                      "differences from the benchmarks may be noise.**"]
    if len(strat_ret) and benchmarks:
        spy = next(iter(benchmarks.values())).reindex(strat_ret.index).ffill().pct_change(fill_method=None)
        both = pd.concat([strat_ret, spy], axis=1).dropna()
        if len(both) > 20 and both.iloc[:, 1].var() > 0:
            beta = both.cov().iloc[0, 1] / both.iloc[:, 1].var()
            lines += ["", f"Beta to {next(iter(benchmarks))}: {beta:.2f}; correlation {both.corr().iloc[0, 1]:.2f}"]
    return "\n".join(lines) + "\n"


def _md_table(df: pd.DataFrame) -> str:
    cols = ["", *df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for idx, row in df.iterrows():
        out.append("| " + " | ".join([str(idx), *map(str, row.values)]) + " |")
    return "\n".join(out)
