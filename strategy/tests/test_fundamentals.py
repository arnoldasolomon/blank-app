import math

import pandas as pd
import pytest

from catalyst_ls import fundamentals
from helpers import growth_company, make_facts


@pytest.fixture
def quarters():
    return growth_company(start_year=2020, years=3)


@pytest.fixture
def table(quarters):
    return fundamentals.quarterly_table(make_facts(quarters))


def test_q4_and_cash_flow_quarters_are_derived_from_year_to_date(quarters, table):
    q4 = table.loc[pd.Timestamp("2021-12-31")]
    assert q4["revenue"] == pytest.approx(quarters[(2021, 4)]["revenue"])
    q2 = table.loc[pd.Timestamp("2021-06-30")]
    assert q2["cfo"] == pytest.approx(quarters[(2021, 2)]["cfo"])
    assert q2["capex"] == pytest.approx(quarters[(2021, 2)]["capex"])


def test_restated_comparatives_filed_later_are_ignored(quarters, table):
    # Q1 2020 is repeated in the Q1 2021 10-Q at +10%; the original value must win.
    assert table.loc[pd.Timestamp("2020-03-31"), "revenue"] == pytest.approx(quarters[(2020, 1)]["revenue"])


def test_available_date_is_filing_date(table):
    assert table.loc[pd.Timestamp("2021-03-31"), "available"] == pd.Timestamp("2021-05-05")
    assert table.loc[pd.Timestamp("2021-12-31"), "available"] == pd.Timestamp("2022-03-01")


def test_snapshot_growth_and_cash_metrics(quarters):
    snaps = fundamentals.snapshots(fundamentals.quarterly_table(make_facts(quarters)))
    m = fundamentals.asof(snaps, pd.Timestamp("2022-06-01"))   # latest public quarter: Q1 2022
    assert m["period_end"] == pd.Timestamp("2022-03-31")
    assert m["rev_qoq"] == pytest.approx(0.10)
    assert m["rev_yoy"] == pytest.approx(1.1 ** 4 - 1)
    assert m["eps_yoy"] == pytest.approx(1.06 ** 4 - 1)
    ttm_rev = sum(quarters[k]["revenue"] for k in [(2021, 2), (2021, 3), (2021, 4), (2022, 1)])
    assert m["revenue_ttm"] == pytest.approx(ttm_rev)
    assert m["fcf_ttm"] == pytest.approx(ttm_rev * 0.20)
    assert m["net_cash"] == pytest.approx(400e6)
    assert math.isinf(m["runway_years"])


def test_asof_never_sees_unfiled_quarter(quarters):
    snaps = fundamentals.snapshots(fundamentals.quarterly_table(make_facts(quarters)))
    assert fundamentals.asof(snaps, pd.Timestamp("2022-05-04"))["period_end"] == pd.Timestamp("2021-12-31")
    assert fundamentals.asof(snaps, pd.Timestamp("2022-05-05"))["period_end"] == pd.Timestamp("2022-03-31")
    assert fundamentals.asof(snaps, pd.Timestamp("2020-01-01")) is None


def test_asof_is_none_when_company_stops_filing(quarters):
    snaps = fundamentals.snapshots(fundamentals.quarterly_table(make_facts(quarters)))
    assert fundamentals.asof(snaps, pd.Timestamp("2024-06-01")) is None


def test_runway_for_cash_burner_and_payback_for_indebted_earner():
    burner = growth_company(start_year=2020, years=2, cfo_margin=-0.10, cash=500e6, debt=600e6)
    m = fundamentals.asof(fundamentals.snapshots(fundamentals.quarterly_table(make_facts(burner))), pd.Timestamp("2022-03-15"))
    burn = -m["fcf_ttm"]
    assert m["runway_years"] == pytest.approx(500e6 / burn)
    assert not m["runway_is_payback"]

    earner = growth_company(start_year=2020, years=2, cash=100e6, debt=600e6)
    m = fundamentals.asof(fundamentals.snapshots(fundamentals.quarterly_table(make_facts(earner))), pd.Timestamp("2022-03-15"))
    assert m["runway_is_payback"]
    assert m["runway_years"] == pytest.approx(500e6 / m["fcf_ttm"])


def test_company_without_debt_tags_is_debt_free():
    q = growth_company(start_year=2020, years=2)
    for v in q.values():
        del v["debt"]
    t = fundamentals.quarterly_table(make_facts(q))
    assert (t["debt"] == 0).all()
