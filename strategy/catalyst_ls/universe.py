"""Universe construction and loading of all per-company data."""
from __future__ import annotations

import pickle
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

from . import catalysts, fundamentals, sectors
from .prices import yahoo_symbol
from .sec import SecClient

SP500_HISTORY_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
)


@dataclass
class Company:
    ticker: str
    cik: int
    name: str
    exchange: str
    sector: str | None
    snapshots: pd.DataFrame
    filings: pd.DataFrame
    events: list = field(default_factory=list)  # filing-index catalysts (no Form 4s)


@dataclass
class Universe:
    companies: dict[str, Company]
    sp500_history: pd.DataFrame | None   # index: date, column "tickers" (set of yahoo symbols)
    unmapped_sp500: set[str]             # historical members with no current SEC ticker (survivorship gap)

    def members(self, date: pd.Timestamp, cfg: dict) -> set[str]:
        out = set()
        if cfg["universe"]["include_nasdaq"]:
            out |= {t for t, c in self.companies.items() if c.exchange == "Nasdaq"}
        if cfg["universe"]["include_sp500"] and self.sp500_history is not None:
            pos = self.sp500_history.index.searchsorted(date, side="right") - 1
            if pos >= 0:
                out |= self.sp500_history.iloc[pos]["tickers"] & set(self.companies)
        excluded = set(cfg["universe"]["exclude_sectors"])
        return {t for t in out if self.companies[t].sector is not None and self.companies[t].sector not in excluded}


def load_sp500_history(cache_dir: Path) -> pd.DataFrame:
    path = cache_dir / "sp500_history.csv"
    if not path.exists():
        resp = requests.get(SP500_HISTORY_URL, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    df["tickers"] = df["tickers"].map(lambda s: {yahoo_symbol(t) for t in s.split(",")})
    return df


def build(cfg: dict, sec: SecClient, tickers: list[str] | None = None, log=print) -> Universe:
    cache_dir = Path(cfg["data"]["cache_dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    listing = {}
    for row in sec.tickers():
        sym = yahoo_symbol(row["ticker"])
        listing.setdefault(sym, row)  # first entry per ticker is the primary listing

    sp_hist = load_sp500_history(cache_dir) if cfg["universe"]["include_sp500"] else None
    wanted: set[str] = set()
    unmapped: set[str] = set()
    if tickers:
        wanted = {yahoo_symbol(t) for t in tickers}
    else:
        if cfg["universe"]["include_nasdaq"]:
            wanted |= {t for t, r in listing.items() if r.get("exchange") == "Nasdaq"}
        if sp_hist is not None:
            start = pd.Timestamp(cfg["backtest"]["start"]) - pd.Timedelta(days=30)
            members = set().union(*sp_hist[sp_hist.index >= start]["tickers"])
            wanted |= members & set(listing)
            unmapped = members - set(listing)

    companies: dict[str, Company] = {}
    include_leases = cfg["long"]["include_lease_liabilities"]
    for i, sym in enumerate(sorted(wanted)):
        if sym not in listing:
            continue
        row = listing[sym]
        if i % 200 == 0:
            log(f"  loading fundamentals {i}/{len(wanted)}")
        try:
            company = _load_company(sec, cache_dir, sym, row, include_leases)
        except FileNotFoundError:
            continue  # no XBRL facts: funds, foreign filers on 20-F, very new listings
        except Exception as exc:  # one bad filer must not stop the whole run
            print(f"  skipped {sym}: {exc}", file=sys.stderr)
            continue
        if company is not None:
            companies[sym] = company
    return Universe(companies, sp_hist, unmapped)


def _load_company(sec: SecClient, cache_dir: Path, sym: str, row: dict, include_leases: bool) -> Company | None:
    cik = int(row["cik"])
    sub = sec.submissions(cik)
    proc = cache_dir / "processed" / f"{cik}_{include_leases}.pkl"
    facts_file = sec.cache / f"facts/CIK{cik:010d}.json"
    facts = sec.company_facts(cik)  # refreshes the raw cache when stale
    if proc.exists() and proc.stat().st_mtime >= facts_file.stat().st_mtime:
        with open(proc, "rb") as fh:
            snaps = pickle.load(fh)
    else:
        snaps = fundamentals.snapshots(fundamentals.quarterly_table(facts), include_leases)
        proc.parent.mkdir(parents=True, exist_ok=True)
        with open(proc, "wb") as fh:
            pickle.dump(snaps, fh)
    if snaps.empty:
        return None
    filings = catalysts.filings_frame(sub)
    return Company(
        ticker=sym, cik=cik, name=row.get("name", sym), exchange=row.get("exchange") or "",
        sector=sectors.sector_for(sub.get("sic"), sym), snapshots=snaps, filings=filings,
        events=catalysts.filing_events(cik, filings),
    )
