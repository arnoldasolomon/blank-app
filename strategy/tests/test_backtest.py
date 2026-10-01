import pytest

from catalyst_ls import backtest, config, synthetic
from catalyst_ls.screen import Candidate, Screener

DROP, GAP = synthetic.DROP, synthetic.GAP
_scenario = synthetic.example_scenario


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
