"""Point-in-time quarterly fundamentals from SEC XBRL company facts.

Every value is taken from the *first* filing that reported it, and each quarter
carries the date it became public, so a backtest on date D only ever sees
numbers that were filed on or before D. Later restatements are ignored.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT", "10-QT"}

# Concepts tried in priority order; for each period the first one reported wins.
FLOW_CONCEPTS = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
        "InterestAndDividendIncomeOperating",  # banks without a revenue tag
    ],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"],
    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
}

INSTANT_CONCEPTS = {
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ],
    "sti": [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        "AvailableForSaleSecuritiesCurrent",
    ],
    "ltd_total": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligations", "DebtLongtermAndShorttermCombinedAmount"],
    "ltd_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligationsNoncurrent", "ConvertibleNotesPayableNoncurrent"],
    "ltd_current": ["LongTermDebtCurrent", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "st_borrowings": ["ShortTermBorrowings", "CommercialPaper"],
    "leases": ["OperatingLeaseLiability"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}

QUARTER_DAYS = (75, 105)


def _facts(company_facts: dict, concept: str, taxonomy: str = "us-gaap") -> pd.DataFrame:
    node = company_facts.get("facts", {}).get(taxonomy, {}).get(concept)
    if not node:
        return pd.DataFrame()
    rows = [r for unit_rows in node["units"].values() for r in unit_rows]
    df = pd.DataFrame(rows)
    if df.empty or "form" not in df:
        return pd.DataFrame()
    df = df[df["form"].isin(FORMS)].copy()
    if df.empty:
        return df
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    if "start" in df:
        df["start"] = pd.to_datetime(df["start"])
    return df


def _flow_quarters(df: pd.DataFrame) -> pd.DataFrame:
    """Three-month values, using direct quarterly facts or differences of year-to-date facts."""
    if df.empty or "start" not in df:
        return pd.DataFrame(columns=["end", "value", "filed"])
    df = df.dropna(subset=["start"])
    # Earliest filing for each exact period is the point-in-time value.
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="first")
    df = df.assign(days=(df["end"] - df["start"]).dt.days + 1)

    out: dict[pd.Timestamp, tuple[float, pd.Timestamp]] = {}
    direct = df[df["days"].between(*QUARTER_DAYS)]
    for r in direct.itertuples():
        out[r.end] = (r.val, r.filed)

    for _, grp in df.groupby("start"):
        grp = grp.sort_values("end")
        rows = list(grp.itertuples())
        for later in rows:
            if later.end in out:
                continue
            for earlier in rows:
                gap = later.days - earlier.days
                if earlier.end < later.end and QUARTER_DAYS[0] <= gap <= QUARTER_DAYS[1]:
                    out[later.end] = (later.val - earlier.val, max(later.filed, earlier.filed))
                    break
    if not out:
        return pd.DataFrame(columns=["end", "value", "filed"])
    return pd.DataFrame([(e, v, f) for e, (v, f) in out.items()], columns=["end", "value", "filed"])


def _instants(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["end", "value", "filed"])
    df = df.sort_values("filed").drop_duplicates(["end"], keep="first")
    return df.rename(columns={"val": "value"})[["end", "value", "filed"]]


def _merge_concepts(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["end", "value", "filed"])
    merged = pd.concat([f.assign(priority=i) for i, f in enumerate(frames)], ignore_index=True)
    return merged.sort_values(["end", "priority"]).drop_duplicates("end", keep="first").drop(columns="priority")


def quarterly_table(company_facts: dict) -> pd.DataFrame:
    """One row per fiscal quarter end with flows (3-month), instants and an `available` date."""
    series: dict[str, pd.DataFrame] = {}
    for name, concepts in FLOW_CONCEPTS.items():
        series[name] = _merge_concepts([_flow_quarters(_facts(company_facts, c)) for c in concepts])
    for name, concepts in INSTANT_CONCEPTS.items():
        series[name] = _merge_concepts([_instants(_facts(company_facts, c)) for c in concepts])
    shares = _instants(_facts(company_facts, "EntityCommonStockSharesOutstanding", "dei"))

    ends = series["revenue"]["end"]
    if ends.empty:
        return pd.DataFrame()
    table = pd.DataFrame(index=pd.DatetimeIndex(sorted(set(ends)), name="end"))
    filed_cols = []
    for name, s in series.items():
        s = s.set_index("end")
        s = s[~s.index.duplicated()]
        table[name] = s["value"].reindex(table.index)
        table[f"{name}_filed"] = s["filed"].reindex(table.index)
        filed_cols.append(f"{name}_filed")

    # A quarter becomes usable once revenue and EPS for it are public.
    table["available"] = table[["revenue_filed", "eps_filed"]].max(axis=1)
    table = table.dropna(subset=["available"])

    # Debt: total if tagged, else current + noncurrent, plus short-term borrowings.
    parts = table["ltd_noncurrent"].fillna(0) + table["ltd_current"].fillna(0)
    has_parts = table["ltd_noncurrent"].notna() | table["ltd_current"].notna()
    debt = table["ltd_total"].where(table["ltd_total"].notna(), parts.where(has_parts))
    debt = debt + table["st_borrowings"].fillna(0)
    ever_reported_debt = any(
        not series[k].empty for k in ("ltd_total", "ltd_noncurrent", "ltd_current", "st_borrowings")
    )
    # Companies that never tag debt are treated as debt-free; otherwise carry the last known balance.
    table["debt"] = debt.ffill(limit=2) if ever_reported_debt else 0.0
    table["sti"] = table["sti"].fillna(0)
    table["capex"] = table["capex"].fillna(0)

    if not shares.empty:
        sh = shares.set_index("end")["value"]
        sh = sh[~sh.index.duplicated()].sort_index()
        table["shares"] = sh.reindex(table.index, method="ffill", tolerance=pd.Timedelta(days=200))
    else:
        table["shares"] = np.nan
    return table.drop(columns=filed_cols)


def _ratio_growth(cur: float, base: float) -> float:
    if base is None or cur is None or not np.isfinite(base) or not np.isfinite(cur) or base <= 0:
        return np.nan
    return cur / base - 1.0


def _find(prior: pd.DataFrame, end: pd.Timestamp, days: int, tol: int) -> pd.Series | None:
    target = end - pd.Timedelta(days=days)
    cand = prior[(prior.index >= target - pd.Timedelta(days=tol)) & (prior.index <= target + pd.Timedelta(days=tol))]
    return None if cand.empty else cand.iloc[-1]


def _ttm(rows: pd.DataFrame, end: pd.Timestamp, col: str) -> float:
    """Sum of the four quarters ending at `end`, only if all four are present."""
    window = rows[(rows.index <= end) & (rows.index > end - pd.Timedelta(days=365 - 20))][col]
    if len(window) != 4 or window.isna().any():
        return np.nan
    return float(window.sum())


def _metrics_for(rows: pd.DataFrame, end: pd.Timestamp, include_leases: bool) -> dict:
    cur = rows.loc[end]
    prev_q = _find(rows, end, 91, 25)
    prev_y = _find(rows, end, 364, 25)
    prev_y_prev_q = _find(rows, prev_q.name, 364, 25) if prev_q is not None else None

    def g(a, b, col):
        return _ratio_growth(a[col], b[col]) if a is not None and b is not None else np.nan

    m = {
        "period_end": end,
        "revenue": cur["revenue"],
        "eps": cur["eps"],
        "rev_qoq": g(cur, prev_q, "revenue"),
        "rev_yoy": g(cur, prev_y, "revenue"),
        "rev_qoq_prev": g(prev_q, _find(rows, prev_q.name, 91, 25), "revenue") if prev_q is not None else np.nan,
        "rev_yoy_prev": g(prev_q, prev_y_prev_q, "revenue"),
        "eps_prior_year": prev_y["eps"] if prev_y is not None else np.nan,
    }
    m["eps_yoy"] = _ratio_growth(cur["eps"], m["eps_prior_year"])

    for col in ("revenue", "cfo", "capex", "net_income"):
        m[f"{col}_ttm"] = _ttm(rows, end, col)
    m["fcf_ttm"] = m["cfo_ttm"] - m["capex_ttm"]
    m["capex_ratio"] = m["capex_ttm"] / m["revenue_ttm"] if m["revenue_ttm"] and m["revenue_ttm"] > 0 else np.nan
    m["fcf_ttm_prev"] = (_ttm(rows, prev_q.name, "cfo") - _ttm(rows, prev_q.name, "capex")) if prev_q is not None else np.nan
    pq2 = _find(rows, prev_q.name, 91, 25) if prev_q is not None else None
    m["fcf_ttm_prev2"] = (_ttm(rows, pq2.name, "cfo") - _ttm(rows, pq2.name, "capex")) if pq2 is not None else np.nan

    debt = cur["debt"] + (cur["leases"] if include_leases and pd.notna(cur["leases"]) else 0)
    m["cash_total"] = (cur["cash"] if pd.notna(cur["cash"]) else np.nan) + cur["sti"]
    m["debt"] = debt
    m["net_cash"] = m["cash_total"] - debt
    m["debt_prior_year"] = prev_y["debt"] if prev_y is not None else np.nan
    m["debt_growth"] = (
        debt / m["debt_prior_year"] - 1 if pd.notna(m["debt_prior_year"]) and m["debt_prior_year"] > 0
        else (math.inf if pd.notna(m["debt_prior_year"]) and debt > 0 else np.nan)
    )

    # Years of runway: for cash burners, cash / annual burn; for FCF-positive
    # companies with net debt, years of FCF needed to repay the net debt.
    fcf = m["fcf_ttm"]
    if pd.notna(m["net_cash"]) and m["net_cash"] >= 0:
        m["runway_years"] = math.inf
    elif pd.notna(fcf) and fcf < 0:
        m["runway_years"] = m["cash_total"] / -fcf
    elif pd.notna(fcf) and fcf > 0:
        m["runway_years"] = -m["net_cash"] / fcf
        m["runway_is_payback"] = True
    else:
        m["runway_years"] = np.nan
    m.setdefault("runway_is_payback", False)

    eq = cur["equity"]
    eq_y = prev_y["equity"] if prev_y is not None else np.nan
    m["equity"] = eq
    m["equity_growth"] = _ratio_growth(eq, eq_y)
    avg_eq = np.nanmean([eq, eq_y]) if pd.notna(eq) else np.nan
    m["roe"] = m["net_income_ttm"] / avg_eq if pd.notna(avg_eq) and avg_eq > 0 else np.nan
    m["roe_prev"] = np.nan
    if prev_y is not None and pd.notna(prev_y["equity"]) and prev_y["equity"] > 0:
        m["roe_prev"] = _ttm(rows, prev_y.name, "net_income") / prev_y["equity"]
    m["shares"] = cur["shares"]
    return m


def snapshots(table: pd.DataFrame, include_leases: bool = False) -> pd.DataFrame:
    """Metrics as they stood each time a new quarter became public, indexed by that date."""
    if table.empty:
        return pd.DataFrame()
    out = []
    latest_end = pd.Timestamp.min
    for end, row in table.sort_values("available").iterrows():
        if end <= latest_end:
            continue  # a late filing for an older quarter doesn't replace the current picture
        latest_end = end
        known = table[table["available"] <= row["available"]]
        m = _metrics_for(known, end, include_leases)
        m["available"] = row["available"]
        out.append(m)
    return pd.DataFrame(out).set_index("available").sort_index()


def asof(snaps: pd.DataFrame, date: pd.Timestamp) -> pd.Series | None:
    if snaps is None or snaps.empty:
        return None
    pos = snaps.index.searchsorted(date, side="right") - 1
    if pos < 0:
        return None
    row = snaps.iloc[pos]
    # Stale if the company has stopped filing.
    if (date - row["period_end"]).days > 200:
        return None
    return row
