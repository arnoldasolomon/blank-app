"""Screen the universe on a date: apply the rules, attach catalysts, rank."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import catalysts, fundamentals, rules
from .universe import Universe


@dataclass
class Candidate:
    ticker: str
    side: str                     # "long" | "short"
    name: str
    sector: str | None
    score: float
    catalyst_score: float
    price: float
    market_cap: float
    reasons: list[str]
    events: list = field(default_factory=list)
    has_catalyst: bool = False


def _row(feats: dict[str, pd.DataFrame], date: pd.Timestamp) -> tuple[pd.Timestamp | None, dict[str, pd.Series]]:
    idx = feats["close"].index
    pos = idx.searchsorted(date, side="right") - 1
    if pos < 0:
        return None, {}
    return idx[pos], {k: v.iloc[pos] for k, v in feats.items()}


def _price_dict(row: dict[str, pd.Series], ticker: str) -> dict | None:
    if ticker not in row["close"].index or pd.isna(row["close"][ticker]):
        return None
    return {k: row[k][ticker] for k in row}


class Screener:
    def __init__(self, universe: Universe, feats: dict[str, pd.DataFrame], cfg: dict, insider_fetch=None):
        self.u, self.feats, self.cfg = universe, feats, cfg
        self.insider_fetch = insider_fetch
        self._insider_cache: dict[tuple[str, pd.Timestamp], list] = {}
        self._eligible_cache: tuple[pd.Timestamp, list] | None = None

    # ---- per-name evaluation -------------------------------------------------
    def _eligible(self, date: pd.Timestamp):
        if self._eligible_cache is not None and self._eligible_cache[0] == date:
            return self._eligible_cache[1]
        out = self._compute_eligible(date)
        self._eligible_cache = (date, out)
        return out

    def _compute_eligible(self, date: pd.Timestamp):
        _, row = _row(self.feats, date)
        if not row:
            return []
        uc = self.cfg["universe"]
        out = []
        seen_cik: set[int] = set()
        for t in sorted(self.u.members(date, self.cfg)):
            p = _price_dict(row, t)
            if p is None:
                continue
            c = self.u.companies[t]
            if c.cik in seen_cik:
                continue  # second share class of the same company (GOOG/GOOGL)
            m = fundamentals.asof(c.snapshots, date)
            if m is None:
                continue
            mcap = m["shares"] * p["raw_close"] if pd.notna(m["shares"]) else np.nan
            p["market_cap"] = mcap
            if not (pd.notna(mcap) and mcap >= uc["min_market_cap"]):
                continue
            if not (pd.notna(p["adv"]) and p["adv"] >= uc["min_avg_dollar_volume"]):
                continue
            seen_cik.add(c.cik)
            out.append((t, c, m.to_dict(), p))
        return out

    def runup_cutoff(self, eligible) -> float | None:
        rets = pd.Series([p["ret_runup"] for _, _, _, p in eligible], dtype=float).dropna()
        if rets.empty:
            return None
        return float(rets.quantile(1 - self.cfg["short"]["runup_top_fraction"]))

    def _events(self, c, date: pd.Timestamp) -> list:
        lookback = pd.Timedelta(days=self.cfg["catalysts"]["lookback_days"])
        start = date - lookback
        events = [e for e in c.events if start < e.date <= date]
        if self.insider_fetch is not None:
            key = (c.ticker, date)
            if key not in self._insider_cache:
                self._insider_cache[key] = catalysts.insider_events(c.cik, c.filings, start, date, self.insider_fetch)
            events += self._insider_cache[key]
        return events

    # ---- public API ----------------------------------------------------------
    def screen(self, date: pd.Timestamp) -> tuple[list[Candidate], list[Candidate]]:
        eligible = self._eligible(date)
        cutoff = self.runup_cutoff(eligible)
        cc = self.cfg["catalysts"]
        growth = self._sector_growth_pct(eligible)
        longs, shorts = [], []
        for t, c, m, p in eligible:
            lv = rules.long_setup(m, p, c.sector, self.cfg)
            if lv.passed:
                cat, ev = catalysts.score(self._events(c, date), cc["long_weights"])
                cand = Candidate(t, "long", c.name, c.sector, cat + growth.get(t, 0.0), cat, p["raw_close"],
                                 p["market_cap"], lv.reasons, ev, cat > 0)
                if cand.has_catalyst or not cc["require_for_long"]:
                    longs.append(cand)
            sv = rules.short_setup(m, p, c.sector, self.cfg, cutoff)
            if sv.passed:
                cat, ev = catalysts.score(self._events(c, date), cc["short_weights"])
                runup = p["ret_runup"] if pd.notna(p["ret_runup"]) else 0.0
                cand = Candidate(t, "short", c.name, c.sector, cat + sv.conditions_met / 4 + min(runup, 2.0) / 2,
                                 cat, p["raw_close"], p["market_cap"], sv.reasons, ev, cat > 0)
                if cand.has_catalyst or not cc["require_for_short"]:
                    shorts.append(cand)
        longs.sort(key=lambda x: -x.score)
        shorts.sort(key=lambda x: -x.score)
        return longs, shorts

    def setup_holds(self, ticker: str, side: str, date: pd.Timestamp, cutoff: float | None = None) -> tuple[bool, list[str]]:
        """Exit test: does the setup (without the catalyst requirement) still hold?"""
        c = self.u.companies.get(ticker)
        _, row = _row(self.feats, date)
        p = _price_dict(row, ticker) if row else None
        m = fundamentals.asof(c.snapshots, date) if c else None
        if c is None or p is None or m is None:
            return False, ["no current data (delisted or stopped filing)"]
        m = m.to_dict()
        mode = self.cfg["portfolio"]["exit_mode"]
        if side == "long":
            v = rules.long_setup(m, p, c.sector, self.cfg)
            if mode == "fundamentals":
                ok = all(r.startswith("PASS") for r in v.reasons[:-1])  # last check is the price drawdown
                return ok, v.reasons
            return v.passed, v.reasons
        if mode == "fundamentals":
            v = rules.short_fundamentals(m, c.sector, self.cfg)
            return v.passed, v.reasons
        if cutoff is None:
            cutoff = self.runup_cutoff(self._eligible(date))
        v = rules.short_setup(m, p, c.sector, self.cfg, cutoff)
        return v.passed, v.reasons

    def _sector_growth_pct(self, eligible) -> dict[str, float]:
        """Percentile of revenue and EPS growth within the sector: keeps ranking peer-relative."""
        basis = self.cfg["long"]["revenue_growth_basis"]
        df = pd.DataFrame([
            {"t": t, "sector": c.sector, "rev": m.get(f"rev_{basis}"), "eps": m.get("eps_yoy")}
            for t, c, m, _ in eligible
        ])
        if df.empty:
            return {}
        df[["rev", "eps"]] = df[["rev", "eps"]].astype(float)
        pct = df.groupby("sector")[["rev", "eps"]].rank(pct=True)
        return dict(zip(df["t"], pct.mean(axis=1).fillna(0.0)))
