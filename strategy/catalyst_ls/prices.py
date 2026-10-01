"""Daily prices from Yahoo Finance (yfinance) with on-disk caching, plus price features."""
from __future__ import annotations

import hashlib
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


def yahoo_symbol(ticker: str) -> str:
    return ticker.upper().replace(".", "-").replace("/", "-")


@dataclass
class PricePanel:
    """Wide frames indexed by date, one column per ticker."""
    adj_close: pd.DataFrame   # split- and dividend-adjusted: use for returns
    adj_open: pd.DataFrame
    raw_close: pd.DataFrame   # as traded on the day: use for market cap
    volume: pd.DataFrame

    def features(self, cfg: dict) -> dict[str, pd.DataFrame]:
        c = self.adj_close
        lc, sc = cfg["long"], cfg["short"]
        high = c.rolling(lc["high_lookback_days"], min_periods=int(lc["high_lookback_days"] * 0.8)).max()
        daily = c.pct_change(fill_method=None)
        return {
            "close": c,
            "drawdown": 1 - c / high,
            "ret_runup": c.pct_change(sc["runup_lookback_days"], fill_method=None),
            "max_gap": daily.rolling(sc["gap_window_days"], min_periods=1).max(),
            "adv": (self.raw_close * self.volume).rolling(20, min_periods=10).mean(),
            "raw_close": self.raw_close,
        }


def download(tickers: list[str], start: str, cache_dir: str | Path, max_age_hours: float = 12,
             chunk: int = 150) -> PricePanel:
    import yfinance as yf

    cache = Path(cache_dir) / "prices"
    cache.mkdir(parents=True, exist_ok=True)
    symbols = sorted({yahoo_symbol(t) for t in tickers})
    digest = hashlib.sha1(",".join(symbols).encode()).hexdigest()[:12]
    key = cache / f"panel_{start}_{digest}.pkl"
    if key.exists() and time.time() - key.stat().st_mtime < max_age_hours * 3600:
        with open(key, "rb") as fh:
            return pickle.load(fh)

    frames = {"Adj Close": [], "Open": [], "Close": [], "Volume": [], "Stock Splits": []}
    for i in range(0, len(symbols), chunk):
        batch = symbols[i:i + chunk]
        data = yf.download(batch, start=start, auto_adjust=False, actions=True, group_by="column",
                           threads=True, progress=False)
        if data.empty:
            continue
        for field in frames:
            if field in data.columns.get_level_values(0):
                part = data[field]
                if isinstance(part, pd.Series):
                    part = part.to_frame(batch[0])
                frames[field].append(part)

    def wide(field):
        return pd.concat(frames[field], axis=1).sort_index() if frames[field] else pd.DataFrame()

    adj, close, opn, vol = wide("Adj Close"), wide("Close"), wide("Open"), wide("Volume")
    splits = wide("Stock Splits").reindex_like(close).fillna(0).replace(0, 1.0)
    panel = build_panel(adj, opn, close, vol, splits)
    with open(key, "wb") as fh:
        pickle.dump(panel, fh)
    return panel


def build_panel(adj: pd.DataFrame, opn: pd.DataFrame, close: pd.DataFrame, vol: pd.DataFrame,
                splits: pd.DataFrame | None = None) -> PricePanel:
    """Yahoo's Close is split-adjusted; undo later splits to recover the price as traded."""
    if splits is None:
        splits = pd.DataFrame(1.0, index=close.index, columns=close.columns)
    # Factor at t = product of split ratios strictly after t.
    future = splits[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    raw_close = close * future
    adj_open = opn * (adj / close)
    return PricePanel(adj_close=adj, adj_open=adj_open, raw_close=raw_close, volume=vol)


def risk_free(cache_dir: str | Path, start: str, fallback: float) -> pd.Series:
    """13-week T-bill yield (^IRX) as an annual decimal; constant fallback if unavailable."""
    try:
        import yfinance as yf
        irx = yf.download("^IRX", start=start, progress=False, auto_adjust=False)["Close"]
        if isinstance(irx, pd.DataFrame):
            irx = irx.iloc[:, 0]
        if not irx.empty:
            return (irx / 100).rename("rf")
    except Exception:
        pass
    return pd.Series(dtype=float, name="rf").fillna(fallback)


