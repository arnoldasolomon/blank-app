import pandas as pd

from catalyst_ls import catalysts, sectors

SUB = {"all_filings": {
    "accessionNumber": ["0001-24-000001", "0001-24-000002", "0001-24-000003", "0001-24-000004", "0001-24-000005", "0001-24-000006"],
    "filingDate": ["2024-01-10", "2024-01-12", "2024-01-15", "2024-01-20", "2024-01-22", "2024-01-25"],
    "form": ["8-K", "SC 13D", "NT 10-Q", "424B5", "4", "8-K"],
    "items": ["2.02,9.01", "", "", "", "", "4.01,4.02"],
    "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm", "xslF345X05/form4.xml", "e.htm"],
}}

FORM4 = b"""<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId><rptOwnerName>Jane CEO</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>50.5</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>9</value></transactionShares>
        <transactionPricePerShare><value>1</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_filing_index_events():
    kinds = [e.kind for e in catalysts.filing_events(123, catalysts.filings_frame(SUB))]
    assert kinds == ["earnings_release", "activist_13d", "late_filing", "securities_offering", "auditor_change", "restatement"]


def test_form4_open_market_purchase_only():
    txs = catalysts.parse_form4(FORM4)
    assert txs == [{"owner": "Jane CEO", "code": "P", "value": 50500.0}]


def test_insider_events_fetch_raw_xml_within_window():
    seen = []

    def fetch(cik, acc, doc):
        seen.append(doc)
        return FORM4

    filings = catalysts.filings_frame(SUB)
    ev = catalysts.insider_events(123, filings, pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-31"), fetch)
    assert [e.kind for e in ev] == ["insider_buy"]
    assert seen == ["xslF345X05/form4.xml"]
    assert catalysts.insider_events(123, filings, pd.Timestamp("2024-02-01"), pd.Timestamp("2024-02-28"), fetch) == []


def test_score_counts_each_kind_once():
    ev = [catalysts.Event(pd.Timestamp("2024-01-01"), k, "", "") for k in ("insider_buy", "insider_buy", "earnings_release", "auditor_change")]
    total, used = catalysts.score(ev, {"insider_buy": 1.0, "earnings_release": 0.5})
    assert total == 1.5
    assert len(used) == 3


def test_sector_mapping():
    assert sectors.sector_for("7372") == "Technology"
    assert sectors.sector_for(2834) == "Healthcare"
    assert sectors.sector_for(6022) == "Financials"
    assert sectors.sector_for(6798) == "Real Estate"
    assert sectors.sector_for(1311) == "Energy"
    assert sectors.sector_for(6770) is None
    assert sectors.sector_for("7389", "AFRM") == "Financials"
    assert sectors.sector_for(None) is None
