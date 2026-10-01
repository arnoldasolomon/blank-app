import math

import pytest

from catalyst_ls import config, rules

CFG = config.load()


def good_long(**over):
    m = dict(rev_qoq=0.35, rev_yoy=0.8, eps=1.2, eps_prior_year=1.0, eps_yoy=0.20, cfo_ttm=50e6,
             fcf_ttm=30e6, capex_ratio=0.05, net_cash=100e6, runway_years=math.inf, runway_is_payback=False)
    m.update(over)
    return m


PRICE_DOWN = {"drawdown": 0.20}


def test_long_passes_when_every_rule_holds():
    v = rules.long_setup(good_long(), PRICE_DOWN, "Technology", CFG)
    assert v.passed, v.reasons


@pytest.mark.parametrize("override, price", [
    ({"rev_qoq": 0.29}, PRICE_DOWN),                       # revenue growth below 30%
    ({"eps_yoy": 0.10, "eps": 1.1}, PRICE_DOWN),           # EPS growth below 15%
    ({"cfo_ttm": -1.0}, PRICE_DOWN),                       # negative operating cash flow
    ({"fcf_ttm": -1.0}, PRICE_DOWN),                       # negative FCF, low capex
    ({"net_cash": -10e6, "runway_years": 8.0, "runway_is_payback": True}, PRICE_DOWN),  # debt takes 8y of FCF
    ({}, {"drawdown": 0.10}),                              # only 10% off the high
])
def test_long_fails_each_rule(override, price):
    assert not rules.long_setup(good_long(**override), price, "Technology", CFG).passed


def test_high_capex_exempts_negative_fcf_but_not_negative_cfo():
    assert rules.long_setup(good_long(fcf_ttm=-5e6, capex_ratio=0.30), PRICE_DOWN, "Technology", CFG).passed
    assert not rules.long_setup(good_long(fcf_ttm=-5e6, capex_ratio=0.30, cfo_ttm=-1), PRICE_DOWN, "Technology", CFG).passed


def test_net_debt_allowed_with_runway_or_fast_payback():
    assert rules.long_setup(good_long(net_cash=-10e6, runway_years=3.0, runway_is_payback=True), PRICE_DOWN, "Technology", CFG).passed
    assert rules.long_setup(good_long(net_cash=-10e6, runway_years=6.0, runway_is_payback=False), PRICE_DOWN, "Technology", CFG).passed


def test_eps_turnaround_from_loss_counts():
    m = good_long(eps=0.10, eps_prior_year=-0.20, eps_yoy=float("nan"))
    assert rules.long_setup(m, PRICE_DOWN, "Technology", CFG).passed
    cfg = config.with_overrides(CFG, long__allow_eps_turnaround=False)
    assert not rules.long_setup(m, PRICE_DOWN, "Technology", cfg).passed


def test_sector_specific_thresholds():
    m = good_long(rev_qoq=0.10, eps_yoy=0.12)
    assert not rules.long_setup(m, PRICE_DOWN, "Technology", CFG).passed
    assert rules.long_setup(m, PRICE_DOWN, "Utilities", CFG).passed


def test_yoy_basis_switch():
    cfg = config.with_overrides(CFG, long__revenue_growth_basis="yoy")
    assert rules.long_setup(good_long(rev_qoq=0.01, rev_yoy=0.40), PRICE_DOWN, "Technology", cfg).passed


def test_financials_use_roe_instead_of_cash_rules():
    m = dict(rev_yoy=0.12, eps_yoy=0.20, eps=2.0, roe=0.15, fcf_ttm=-1e9, net_cash=-50e9)
    assert rules.long_setup(m, PRICE_DOWN, "Financials", CFG).passed
    assert not rules.long_setup({**m, "roe": 0.08}, PRICE_DOWN, "Financials", CFG).passed


def bad_short(**over):
    m = dict(rev_yoy=0.05, rev_yoy_prev=0.15, eps=0.8, eps_prior_year=1.0, fcf_ttm=10e6, fcf_ttm_prev=20e6,
             fcf_ttm_prev2=30e6, debt_growth=0.25)
    m.update(over)
    return m


def test_short_needs_two_of_four():
    assert rules.short_fundamentals(bad_short(), "Technology", CFG).conditions_met == 4
    two = bad_short(fcf_ttm=50e6, debt_growth=-0.1)
    assert rules.short_fundamentals(two, "Technology", CFG).passed
    one = bad_short(fcf_ttm=50e6, debt_growth=-0.1, eps=1.5)
    assert not rules.short_fundamentals(one, "Technology", CFG).passed


def test_short_requires_run_up_or_gap():
    m = bad_short()
    assert rules.short_setup(m, {"ret_runup": 0.60, "max_gap": 0.02}, "Technology", CFG, runup_cutoff=0.40).passed
    assert rules.short_setup(m, {"ret_runup": 0.05, "max_gap": 0.36}, "Technology", CFG, runup_cutoff=0.40).passed
    assert not rules.short_setup(m, {"ret_runup": 0.05, "max_gap": 0.05}, "Technology", CFG, runup_cutoff=0.40).passed
