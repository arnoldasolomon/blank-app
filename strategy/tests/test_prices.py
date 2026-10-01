import pandas as pd
import pytest

from catalyst_ls import config
from catalyst_ls.prices import build_panel, yahoo_symbol


def test_raw_close_undoes_later_splits_only():
    idx = pd.bdate_range("2024-01-01", periods=4)
    close = pd.DataFrame({"X": [50.0, 50, 50, 50]}, index=idx)   # Yahoo: split-adjusted
    splits = pd.DataFrame({"X": [1.0, 1, 2, 1]}, index=idx)       # 2-for-1 effective on day 3
    p = build_panel(close, close, close, close * 0 + 1e6, splits)
    assert p.raw_close["X"].tolist() == [100, 100, 50, 50]


def test_features_drawdown_and_gap():
    idx = pd.bdate_range("2023-01-02", periods=300)
    s = pd.Series(100.0, index=idx)
    s.iloc[-30:] = 80.0
    s.iloc[-5:] = 96.0
    close = s.to_frame("X")
    f = build_panel(close, close, close, close * 0 + 1e6).features(config.load())
    assert f["drawdown"]["X"].iloc[-6] == pytest.approx(0.20)
    assert f["max_gap"]["X"].iloc[-1] == pytest.approx(0.20)


def test_yahoo_symbol():
    assert yahoo_symbol("brk.b") == "BRK-B"
