"""Weekly-rebalanced, paired long/short backtest.

Signals use data up to the last trading day of each week; trades fill at the
next trading day's open. Positions are marked to market daily on adjusted
closes, with CFD spread and overnight financing charged.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .screen import Candidate, Screener


@dataclass
class Position:
    ticker: str
    side: str
    notional: float
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    score: float
    last_price: float


@dataclass
class Trade:
    ticker: str
    side: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    notional: float
    pnl: float
    exit_reason: str


@dataclass
class Result:
    equity: pd.Series
    daily_pnl: pd.Series
    gross_exposure: pd.Series
    trades: list[Trade]
    signals: list[dict] = field(default_factory=list)


def week_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period("W-FRI")).max().values)


def size_for(c: Candidate, cfg: dict) -> float:
    pc = cfg["portfolio"]
    if pc["sizing"] == "catalyst":
        return pc["max_position_usd"] * min(1.0, c.catalyst_score / pc["catalyst_score_full_size"])
    return float(pc["max_position_usd"])


def choose(held_long: list[str], held_short: list[str], cands_long: list[Candidate], cands_short: list[Candidate],
           scores: dict[str, float], cfg: dict) -> tuple[list[str], list[str]]:
    """Target books with equal leg counts: keep valid holdings, fill with best new candidates."""
    pc = cfg["portfolio"]
    n_max = pc["max_positions_per_side"]
    new_long = [c.ticker for c in cands_long if c.ticker not in held_long and c.ticker not in held_short]
    new_short = [c.ticker for c in cands_short if c.ticker not in held_short and c.ticker not in held_long]
    if pc["require_pair"]:
        n = min(n_max, len(held_long) + len(new_long), len(held_short) + len(new_short))
        n_long = n_short = n
    else:
        n_long = min(n_max, len(held_long) + len(new_long))
        n_short = min(n_max, len(held_short) + len(new_short))
    keep_long = sorted(held_long, key=lambda t: -scores.get(t, 0))[:n_long]
    keep_short = sorted(held_short, key=lambda t: -scores.get(t, 0))[:n_short]
    return (keep_long + new_long[: n_long - len(keep_long)],
            keep_short + new_short[: n_short - len(keep_short)])


def run(screener: Screener, opens: pd.DataFrame, closes: pd.DataFrame, cfg: dict,
        rf: pd.Series | None = None, start=None, end=None, log=None) -> Result:
    pc, cc = cfg["portfolio"], cfg["costs"]
    start = pd.Timestamp(start or cfg["backtest"]["start"])
    end = pd.Timestamp(end or cfg["backtest"]["end"] or closes.index[-1])
    days = closes.index[(closes.index >= start) & (closes.index <= end)]
    signal_days = set(week_ends(days))
    spread = cc["spread_bps_per_side"] / 1e4
    rf = rf.reindex(days).ffill().fillna(cc["fallback_risk_free"]) if rf is not None and not rf.empty \
        else pd.Series(cc["fallback_risk_free"], index=days)

    book: dict[str, Position] = {}
    trades: list[Trade] = []
    pending: tuple[list[str], list[str], dict[str, Candidate], dict[str, str]] | None = None
    pnl = pd.Series(0.0, index=days)
    gross = pd.Series(0.0, index=days)
    signals: list[dict] = []
    prev_day = None

    for day in days:
        day_pnl = 0.0
        # 1) Execute last signal at today's open.
        if pending is not None:
            tgt_long, tgt_short, cand_map, exit_reasons = pending
            target = {t: "long" for t in tgt_long} | {t: "short" for t in tgt_short}
            for t in list(book):
                if target.get(t) != book[t].side:
                    px = _px(opens, t, day) or book[t].last_price
                    day_pnl += _mark(book[t], px)
                    day_pnl -= abs(book[t].shares * px) * spread
                    trades.append(_close(book.pop(t), day, px, exit_reasons.get(t, "rebalanced out")))
            for t, side in target.items():
                if t in book:
                    continue
                px = _px(opens, t, day)
                if not px:
                    continue
                notional = size_for(cand_map[t], cfg)
                if notional <= 0:
                    continue
                pos = Position(t, side, notional, day, px, notional / px, cand_map[t].score, px)
                day_pnl -= notional * spread
                book[t] = pos
            pending = None

        # 2) Mark to market at the close and charge financing for the days held.
        cal_days = (day - prev_day).days if prev_day is not None else 1
        for t, pos in list(book.items()):
            px = _px(closes, t, day)
            if px:
                day_pnl += _mark(pos, px)
            value = abs(pos.shares * pos.last_price)
            rate = rf[day] + cc["financing_markup_annual"] if pos.side == "long" else cc["financing_markup_annual"] - rf[day]
            day_pnl -= value * rate * cal_days / 365
        gross[day] = sum(abs(p.shares * p.last_price) for p in book.values())
        pnl[day] = day_pnl
        prev_day = day

        # 3) Stop-loss check (daily, fills next open).
        stop = pc.get("stop_loss")
        stopped = {}
        if stop:
            for t, pos in book.items():
                move = pos.last_price / pos.entry_price - 1
                if (move if pos.side == "long" else -move) <= -stop:
                    stopped[t] = f"stop-loss {stop:.0%}"

        # 4) Weekly signal.
        if day in signal_days or stopped:
            longs, shorts = screener.screen(day) if day in signal_days else ([], [])
            exit_reasons = dict(stopped)
            cutoff = screener.runup_cutoff(screener._eligible(day)) if day in signal_days else None
            for t, pos in book.items():
                if t in stopped or day not in signal_days:
                    continue
                ok, reasons = screener.setup_holds(t, pos.side, day, cutoff)
                if not ok:
                    exit_reasons[t] = "setup failed: " + "; ".join(r[5:] for r in reasons if r.startswith("FAIL"))
            held_long = [t for t, p in book.items() if p.side == "long" and t not in exit_reasons]
            held_short = [t for t, p in book.items() if p.side == "short" and t not in exit_reasons]
            if day not in signal_days:   # stop-out only: keep the rest, pairs rebalance on the weekly signal
                tgt_long, tgt_short = held_long, held_short
                if pc["require_pair"]:
                    n = min(len(held_long), len(held_short))
                    tgt_long, tgt_short = held_long[:n], held_short[:n]
            else:
                scores = {t: p.score for t, p in book.items()} | {c.ticker: c.score for c in longs + shorts}
                tgt_long, tgt_short = choose(held_long, held_short, longs, shorts, scores, cfg)
            cand_map = {c.ticker: c for c in longs + shorts}
            pending = (tgt_long, tgt_short, cand_map, exit_reasons)
            if day in signal_days:
                signals.append({"date": day, "long_candidates": len(longs), "short_candidates": len(shorts),
                                "target_long": tgt_long, "target_short": tgt_short})
                if log:
                    log(f"{day.date()} longs={len(longs)} shorts={len(shorts)} -> L{tgt_long} S{tgt_short}")

    for t in list(book):  # close out at the end
        trades.append(_close(book.pop(t), days[-1], _px(closes, t, days[-1]) or 0.0, "end of backtest"))

    capital = float(pc["capital_usd"])
    equity = capital + pnl.cumsum()
    return Result(equity, pnl, gross, trades, signals)


def _px(frame: pd.DataFrame, t: str, day) -> float | None:
    if t not in frame.columns:
        return None
    v = frame.at[day, t] if day in frame.index else np.nan
    return float(v) if pd.notna(v) and v > 0 else None


def _mark(pos: Position, px: float) -> float:
    move = pos.shares * (px - pos.last_price)
    pos.last_price = px
    return move if pos.side == "long" else -move


def _close(pos: Position, day, px: float, reason: str) -> Trade:
    sign = 1 if pos.side == "long" else -1
    return Trade(pos.ticker, pos.side, pos.entry_date, day, pos.entry_price, px, pos.notional,
                 sign * pos.shares * (px - pos.entry_price), reason)
