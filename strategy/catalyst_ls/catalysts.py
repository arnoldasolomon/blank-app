"""Catalyst events detected from free SEC EDGAR filing indexes.

Everything here is keyed by filing date, so it is point-in-time by construction.
Not available for free and therefore NOT covered: analyst estimate revisions,
guidance numbers, buyback announcements (filed under generic 8-K item 8.01).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import pandas as pd

OFFERING_FORMS = {"S-1", "S-3", "S-3ASR", "424B1", "424B2", "424B3", "424B4", "424B5", "424B7"}
LATE_FORMS = {"NT 10-K", "NT 10-Q"}
ACTIVIST_FORMS = {"SC 13D", "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13D/A"}


@dataclass
class Event:
    date: pd.Timestamp
    kind: str
    detail: str
    url: str


def filings_frame(submissions: dict) -> pd.DataFrame:
    f = submissions["all_filings"]
    df = pd.DataFrame({
        "accession": f.get("accessionNumber", []),
        "date": pd.to_datetime(f.get("filingDate", [])),
        "form": f.get("form", []),
        "items": f.get("items", [""] * len(f.get("form", []))),
        "document": f.get("primaryDocument", [""] * len(f.get("form", []))),
    })
    df["items"] = df["items"].fillna("")
    return df.sort_values("date").reset_index(drop=True)


def _url(cik: int, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"


def filing_events(cik: int, filings: pd.DataFrame) -> list[Event]:
    """Events visible from the filing index alone (no document downloads)."""
    events: list[Event] = []
    for r in filings.itertuples():
        url = _url(cik, r.accession)
        items = set(i.strip() for i in r.items.split(",") if i.strip())
        if r.form in ("8-K", "8-K/A"):
            if "2.02" in items:
                events.append(Event(r.date, "earnings_release", "8-K 2.02 results of operations", url))
            if "4.01" in items:
                events.append(Event(r.date, "auditor_change", "8-K 4.01 change of auditor", url))
            if "4.02" in items:
                events.append(Event(r.date, "restatement", "8-K 4.02 non-reliance on prior financials", url))
            if "5.02" in items:
                events.append(Event(r.date, "exec_departure", "8-K 5.02 director/officer change", url))
        elif r.form in ACTIVIST_FORMS:
            events.append(Event(r.date, "activist_13d", f"{r.form} activist stake", url))
        elif r.form in LATE_FORMS:
            events.append(Event(r.date, "late_filing", f"{r.form} late filing notice", url))
        elif r.form in OFFERING_FORMS:
            events.append(Event(r.date, "securities_offering", f"{r.form} securities offering", url))
    return events


def parse_form4(xml: bytes) -> list[dict]:
    """Open-market non-derivative transactions: code P (purchase) or S (sale)."""
    root = ET.fromstring(xml)
    owner = root.findtext("reportingOwner/reportingOwnerId/rptOwnerName") or "unknown"
    out = []
    for tx in root.iter("nonDerivativeTransaction"):
        code = tx.findtext("transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        try:
            shares = float(tx.findtext("transactionAmounts/transactionShares/value") or 0)
            price = float(tx.findtext("transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        out.append({"owner": owner, "code": code, "value": shares * price})
    return out


def insider_events(cik: int, filings: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, fetch) -> list[Event]:
    """Downloads Form 4s filed in [start, end]; `fetch(cik, accession, document) -> bytes`."""
    window = filings[(filings["form"] == "4") & (filings["date"] >= start) & (filings["date"] <= end)]
    sellers: list[tuple[pd.Timestamp, str, float, str]] = []
    events: list[Event] = []
    for r in window.itertuples():
        try:
            txs = parse_form4(fetch(cik, r.accession, r.document))
        except Exception:  # malformed or missing document: skip, don't fail the scan
            continue
        for tx in txs:
            if tx["code"] == "P" and tx["value"] > 0:
                events.append(Event(r.date, "insider_buy", f"{tx['owner']} bought ${tx['value']:,.0f}", _url(cik, r.accession)))
            elif tx["code"] == "S":
                sellers.append((r.date, tx["owner"], tx["value"], _url(cik, r.accession)))
    owners = {s[1] for s in sellers}
    if len(owners) >= 2:
        last = max(sellers, key=lambda s: s[0])
        total = sum(s[2] for s in sellers)
        events.append(Event(last[0], "insider_selling", f"{len(owners)} insiders sold ${total:,.0f}", last[3]))
    return events


def score(events: list[Event], weights: dict) -> tuple[float, list[Event]]:
    """Sum of weights, counting each catalyst kind once."""
    relevant = [e for e in events if e.kind in weights]
    kinds = {e.kind for e in relevant}
    return sum(weights[k] for k in kinds), relevant
