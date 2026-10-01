import numpy as np
import pandas as pd
import pytest

from catalyst_ls import cli, config, metrics
from catalyst_ls.universe import Universe
from test_backtest import _run, _cand


def test_stats_on_known_series():
    r = pd.Series([0.01, -0.01] * 126, index=pd.bdate_range("2023-01-02", periods=252))
    s = metrics.stats(r)
    curve = (1 + r).cumprod()
    assert s["max_drawdown"] == pytest.approx((curve / curve.cummax() - 1).min())
    assert s["total_return"] == pytest.approx(curve.iloc[-1] - 1)
    assert s["volatility"] == pytest.approx(r.std() * np.sqrt(252))


def test_report_renders_with_benchmarks():
    cfg = config.with_overrides(config.load(), long__revenue_growth_basis="yoy")
    idx, res = _run(cfg)
    bench = {"SPY": pd.Series(np.linspace(100, 150, len(idx)), index=idx)}
    text = metrics.report(res, bench, 0.03, cfg)
    assert "| Strategy |" in text and "| SPY |" in text
    assert "only 2 trades" in text


def test_scan_render_lists_candidates_and_exits():
    cfg = config.load()
    text = cli.render_scan(pd.Timestamp("2026-10-01"), [_cand("AAA", "long")], [],
                           [({"ticker": "BBB", "side": "short"}, False, ["FAIL debt rising"])], cfg)
    assert "AAA" in text and "Paired trades available: **0**" in text
    assert "BBB short: **EXIT**" in text


def test_universe_members_point_in_time():
    from catalyst_ls.universe import Company
    comp = lambda t, ex: Company(t, 1, t, ex, "Technology", pd.DataFrame(), pd.DataFrame())  # noqa: E731
    hist = pd.DataFrame({"tickers": [{"OLD", "KEEP"}, {"KEEP", "NEW"}]},
                        index=pd.to_datetime(["2020-01-01", "2022-01-01"]))
    u = Universe({"OLD": comp("OLD", "NYSE"), "KEEP": comp("KEEP", "NYSE"), "NEW": comp("NEW", "NYSE"),
                  "NQ": comp("NQ", "Nasdaq")}, hist, set())
    cfg = config.load()
    assert u.members(pd.Timestamp("2021-06-01"), cfg) == {"OLD", "KEEP", "NQ"}
    assert u.members(pd.Timestamp("2023-06-01"), cfg) == {"KEEP", "NEW", "NQ"}
    cfg = config.with_overrides(cfg, universe__include_nasdaq=False)
    assert u.members(pd.Timestamp("2023-06-01"), cfg) == {"KEEP", "NEW"}
