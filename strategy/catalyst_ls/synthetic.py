"""Synthetic SEC company-facts and price data, for tests and the dashboard's worked example."""
from __future__ import annotations

import zlib
from datetime import date, timedelta

import numpy as np
import pandas as pd

Q_ENDS = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _end(y, q):
    m, d = Q_ENDS[q]
    return date(y, m, d)


def _start(y, q):
    return date(y, 3 * (q - 1) + 1, 1)


def make_facts(quarters: dict[tuple[int, int], dict], restate_comparatives: bool = True) -> dict:
    """Build a companyfacts-style dict the way real 10-Q/10-K filings report it.

    quarters[(year, q)] = {revenue, eps, cfo, capex, cash, debt, shares, net_income, equity}
    Income-statement items: 3-month facts in 10-Qs, annual only in the 10-K.
    Cash-flow items: year-to-date only. Balance sheet: instants.
    Each filing also repeats last year's comparative with a later filed date and a
    restated (+10%) value, which point-in-time logic must ignore.
    """
    facts: dict[str, list] = {}

    def add(concept, unit, **fact):
        facts.setdefault((concept, unit), []).append(fact)

    for (y, q), v in sorted(quarters.items()):
        end = _end(y, q)
        filed = end + timedelta(days=60 if q == 4 else 35)
        form = "10-K" if q == 4 else "10-Q"
        base = dict(form=form, filed=filed.isoformat(), fy=y, fp="FY" if q == 4 else f"Q{q}", accn=f"{y}{q}")
        ytd_quarters = [(y, k) for k in range(1, q + 1)]
        has_full_ytd = all(k in quarters for k in ytd_quarters)
        for concept, key in (("Revenues", "revenue"), ("EarningsPerShareDiluted", "eps"), ("NetIncomeLoss", "net_income")):
            unit = "USD/shares" if key == "eps" else "USD"
            if q < 4:
                add(concept, unit, start=_start(y, q).isoformat(), end=end.isoformat(), val=v[key], **base)
            if q >= 3 and has_full_ytd:
                # 9M YTD in Q3 10-Q, FY in 10-K
                total = sum(quarters[k][key] for k in ytd_quarters)
                add(concept, unit, start=date(y, 1, 1).isoformat(), end=end.isoformat(), val=total, **base)
            prior = (y - 1, q)
            if restate_comparatives and prior in quarters and q < 4:
                add(concept, unit, start=_start(y - 1, q).isoformat(), end=_end(y - 1, q).isoformat(),
                    val=quarters[prior][key] * 1.1, **base)
        if has_full_ytd:
            for concept, key in (("NetCashProvidedByUsedInOperatingActivities", "cfo"),
                                 ("PaymentsToAcquirePropertyPlantAndEquipment", "capex")):
                total = sum(quarters[k][key] for k in ytd_quarters)
                add(concept, "USD", start=date(y, 1, 1).isoformat(), end=end.isoformat(), val=total, **base)
        for concept, key in (("CashAndCashEquivalentsAtCarryingValue", "cash"), ("LongTermDebt", "debt"),
                             ("StockholdersEquity", "equity")):
            if key in v:
                add(concept, "USD", end=end.isoformat(), val=v[key], **base)
        if "shares" in v:
            facts.setdefault(("dei:EntityCommonStockSharesOutstanding", "shares"), []).append(
                dict(end=(filed - timedelta(days=5)).isoformat(), val=v["shares"], **base))

    out = {"facts": {"us-gaap": {}, "dei": {}}}
    for (concept, unit), rows in facts.items():
        tax, name = ("dei", concept.split(":")[1]) if concept.startswith("dei:") else ("us-gaap", concept)
        out["facts"][tax][name] = {"units": {unit: rows}}
    return out


def growth_company(start_year=2020, years=4, rev0=100e6, rev_growth_q=0.10, eps0=0.50, eps_growth_q=0.06,
                   cfo_margin=0.25, capex_ratio=0.05, cash=500e6, debt=100e6, shares=50e6, equity=800e6):
    q = {}
    i = 0
    for y in range(start_year, start_year + years):
        for k in range(1, 5):
            rev = rev0 * (1 + rev_growth_q) ** i
            q[(y, k)] = dict(revenue=rev, eps=eps0 * (1 + eps_growth_q) ** i, net_income=rev * 0.2,
                             cfo=rev * cfo_margin, capex=rev * capex_ratio, cash=cash, debt=debt,
                             shares=shares, equity=equity)
            i += 1
    return q


def price_panel(columns: dict[str, np.ndarray], start="2021-01-04"):
    from catalyst_ls.prices import build_panel

    n = len(next(iter(columns.values())))
    idx = pd.bdate_range(start, periods=n)
    close = pd.DataFrame(columns, index=idx)
    vol = pd.DataFrame(1e6, index=idx, columns=close.columns)
    return build_panel(close, close.copy(), close.copy(), vol)


N = 900
DROP, GAP = 400, 419


def _company(ticker, quarters, events=()):
    from . import fundamentals
    from .universe import Company

    snaps = fundamentals.snapshots(fundamentals.quarterly_table(make_facts(quarters)))
    return Company(ticker, zlib.crc32(ticker.encode()), ticker, "Nasdaq", "Technology", snaps, pd.DataFrame(), list(events))


def example_scenario(long_rev_growth_q: float = 0.10):
    """Ten made-up companies: AAA (strong growth, sells off 30%), BBB (deteriorating,
    gaps up 25% then fades) and eight dull fillers. Used by tests and the dashboard."""
    from . import catalysts
    from .universe import Universe

    idx = pd.bdate_range("2021-01-04", periods=N)
    aaa = np.full(N, 100.0)
    aaa[DROP:DROP + 20] = np.linspace(100, 70, 20)
    aaa[DROP + 20:DROP + 40] = 70
    aaa[DROP + 40:DROP + 60] = np.linspace(70, 98, 20)
    aaa[DROP + 60:] = 98
    bbb = np.full(N, 100.0)
    bbb[GAP:GAP + 60] = np.linspace(125, 108, 60)
    bbb[GAP + 60:] = 108
    cols = {"AAA": aaa, "BBB": bbb} | {f"F{i}": np.full(N, 50.0) + i for i in range(8)}
    panel = price_panel(cols)

    good = growth_company(start_year=2020, years=4, rev_growth_q=long_rev_growth_q, eps_growth_q=0.06)
    bad = growth_company(start_year=2020, years=4, rev_growth_q=0.02, eps0=1.0, eps_growth_q=-0.05)
    for i, k in enumerate(sorted(bad)):
        bad[k]["debt"] = 100e6 * (1.05 ** i)
    filler = growth_company(start_year=2020, years=4, rev_growth_q=0.01, eps_growth_q=0.01)

    def ev(kind, d, detail):
        return catalysts.Event(idx[d], kind, detail, "")

    companies = {
        "AAA": _company("AAA", good, [ev("earnings_release", DROP + 15, "8-K 2.02 results of operations")]),
        "BBB": _company("BBB", bad, [ev("auditor_change", GAP - 2, "8-K 4.01 change of auditor")]),
    } | {f"F{i}": _company(f"F{i}", filler) for i in range(8)}
    return idx, panel, Universe(companies, None, set())
