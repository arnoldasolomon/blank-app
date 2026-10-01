import json

from catalyst_ls import config, dashboard, rules


def test_example_runs_real_engine_and_pairs_trades():
    ex = dashboard.example_json(config.load())
    assert set(ex["legs"]) == {"long", "short"}
    assert ex["legs"]["long"]["entry_date"] == ex["legs"]["short"]["entry_date"]
    assert ex["costs"] > 0
    json.dumps(ex)  # fully serialisable


def test_build_embeds_data(tmp_path):
    path = dashboard.build(config.load(), tmp_path, data_access="blocked")
    html = path.read_text()
    assert "/*__DATA__*/null" not in html
    payload = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    data = json.loads(payload)
    assert data["scan"] is None and data["backtest"] is None
    assert "data" not in data["config"]          # no SEC contact details in the page
    assert any(u["key"] == "portfolio.exit_mode" for u in data["unconfirmed"])


def test_build_picks_up_latest_scan(tmp_path):
    (tmp_path / "scan_2026-09-01.json").write_text(json.dumps({"date": "2026-09-01"}))
    (tmp_path / "scan_2026-09-30.json").write_text(json.dumps({"date": "2026-09-30"}))
    html = dashboard.build(config.load(), tmp_path).read_text()
    assert '"scan":{"date":"2026-09-30"}' in html


def test_revenue_slowdown_needs_minimum_margin():
    m = dict(rev_yoy=0.080, rev_yoy_prev=0.085, eps=1, eps_prior_year=1, fcf_ttm=1, fcf_ttm_prev=1, fcf_ttm_prev2=1, debt_growth=0)
    assert not rules.short_fundamentals(m, "Technology", config.load()).reasons[0].startswith("PASS")
    m["rev_yoy"] = 0.07
    assert rules.short_fundamentals(m, "Technology", config.load()).reasons[0].startswith("PASS")
