import numpy as np
import pandas as pd
import pytest

from catalyst_ls import backtest, catalysts, config, fundamentals
from catalyst_ls.screen import Candidate, Screener
from catalyst_ls.universe import Company, Universe
from helpers import growth_company, make_facts, price_panel

N = 900
DROP, GAP = 400, 419


def _company(ticker, quarters, events=()):
    snaps = fundamentals.snapshots(fundamentals.quarterly_table(make_facts(quarters)))
    return Company(ticker, abs(hash(ticker)) % 10**9, ticker, "Nasdaq", "Technology", snaps, pd.DataFrame(), list(events))


def _scenario():
    idx = pd.bdate_range("2021-01-04", periods=N)
    aaa = np.full(N, 100.0)
    aaa[DROP:DROP + 20] = np.linspace(100, 70, 20)
    aaa[DROP + 20:DROP + 40] = 70
    aaa[DROP + 40:DROP + 60] = np.linspace(70, 98, 20)
    aaa[DROP + 60:] = 98
    bbb = np.full(N, 100.0)
    bbb[GAP:] = 125.0
    cols = {"AAA": aaa, "BBB": bbb} | {f"F{i}": np.full(N, 50.0) + i for i in range(8)}
    panel = price_panel(cols)

    good = growth_company(start_year=2020, years=4, rev_growth_q=0.10, eps_growth_q=0.06)
    bad = growth_company(start_year=2020, years=4, rev_growth_q=0.02, eps0=1.0, eps_growth_q=-0.05)
    for i, k in enumerate(sorted(bad)):
        bad[k]["debt"] = 100e6 * (1.05 ** i)
    filler = growth_company(start_year=2020, years=4, rev_growth_q=0.01, eps_growth_q=0.01)
    ev = lambda kind, d: catalysts.Event(idx[d], kind, kind, "")  # noqa: E731
    companies = {
        "AAA": _company("AAA", good, [ev("earnings_release", DROP + 15)]),
        "BBB": _company("BBB", bad, [ev("auditor_change", GAP - 2)]),
    } | {f"F{i}": _company(f"F{i}", filler) for i in range(8)}
    return idx, panel, Universe(companies, None, set())


@pytest.fixture
def cfg():
    return config.with_overrides(config.load(), long__revenue_growth_basis="yoy")


def _run(cfg):
    idx, panel, u = _scenario()
    screener = Screener(u, panel.features(cfg), cfg)
    res = backtest.run(screener, panel.adj_open, panel.adj_close, cfg, None, idx[300], idx[-1])
    return idx, res


def test_pair_opens_together_after_weekly_signal(cfg):
    idx, res = _run(cfg)
    by = {(t.ticker, t.side): t for t in res.trades}
    long, short = by[("AAA", "long")], by[("BBB", "short")]
    assert long.entry_date == short.entry_date
    signal_day = idx[idx < long.entry_date][-1]
    assert signal_day.dayofweek == 4                 # Friday signal
    assert long.entry_date > idx[GAP]                # never before the short setup existed
    assert long.notional == short.notional == 1000
    assert {t.ticker for t in res.trades} == {"AAA", "BBB"}   # fillers never qualify


def test_long_exits_when_setup_fails_and_partner_is_closed(cfg):
    _, res = _run(cfg)
    long = next(t for t in res.trades if t.side == "long")
    short = next(t for t in res.trades if t.side == "short")
    assert long.exit_reason.startswith("setup failed")   # recovered to within 15% of its high
    assert long.exit_price > long.entry_price
    assert short.exit_reason == "rebalanced out"         # no long left to pair it with
    assert short.exit_date == long.exit_date


def test_fundamentals_exit_mode_holds_through_price_recovery(cfg):
    _, res = _run(config.with_overrides(cfg, portfolio__exit_mode="fundamentals"))
    long = next(t for t in res.trades if t.side == "long")
    assert long.exit_reason == "end of backtest"


def test_daily_pnl_reconciles_with_trades_when_costs_are_zero(cfg):
    cfg = config.with_overrides(cfg, costs__spread_bps_per_side=0, costs__financing_markup_annual=0,
                                costs__fallback_risk_free=0)
    _, res = _run(cfg)
    assert res.daily_pnl.sum() == pytest.approx(sum(t.pnl for t in res.trades))
    assert res.equity.iloc[-1] == pytest.approx(cfg["portfolio"]["capital_usd"] + res.daily_pnl.sum())


def test_costs_reduce_pnl(cfg):
    _, gross = _run(config.with_overrides(cfg, costs__spread_bps_per_side=0, costs__financing_markup_annual=0))
    _, net = _run(cfg)
    assert net.daily_pnl.sum() < gross.daily_pnl.sum()


def test_no_trades_without_catalyst_when_required(cfg):
    idx, panel, u = _scenario()
    u.companies["BBB"].events = []
    res = backtest.run(Screener(u, panel.features(cfg), cfg), panel.adj_open, panel.adj_close, cfg, None, idx[300], idx[-1])
    assert res.trades == []   # the long has no short partner, so nothing trades


def test_second_share_class_is_skipped(cfg):
    idx, panel, u = _scenario()
    u.companies["F0"].cik = u.companies["F1"].cik
    tickers = [t for t, *_ in Screener(u, panel.features(cfg), cfg)._eligible(idx[500])]
    assert "F0" in tickers and "F1" not in tickers


def _cand(t, side, score=1.0):
    return Candidate(t, side, t, "Technology", score, score, 10.0, 1e9, [])


def test_choose_keeps_books_paired():
    cfg = config.load()
    tl, ts = backtest.choose([], [], [_cand("A", "long"), _cand("B", "long")], [_cand("X", "short")], {}, cfg)
    assert (tl, ts) == (["A"], ["X"])
    tl, ts = backtest.choose(["A"], [], [], [], {}, cfg)
    assert (tl, ts) == ([], [])
    tl, ts = backtest.choose(["A"], ["X"], [_cand("B", "long")], [_cand("Y", "short")], {}, cfg)
    assert (sorted(tl), sorted(ts)) == (["A", "B"], ["X", "Y"])


def test_catalyst_sizing():
    cfg = config.with_overrides(config.load(), portfolio__sizing="catalyst")
    assert backtest.size_for(_cand("A", "long", 1.0), cfg) == 500
    assert backtest.size_for(_cand("A", "long", 3.0), cfg) == 1000
