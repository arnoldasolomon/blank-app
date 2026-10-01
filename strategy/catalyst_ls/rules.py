"""Long and short setup rules. Pure functions: metrics in, verdict and reasons out."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Verdict:
    passed: bool
    reasons: list[str] = field(default_factory=list)   # human-readable checks, passed and failed
    conditions_met: int = 0


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x)) and not pd.isna(x)


def _pct(x) -> str:
    return f"{x:+.0%}" if _ok(x) and math.isfinite(x) else "n/a"


def _check(reasons: list[str], ok: bool, text: str) -> bool:
    reasons.append(("PASS " if ok else "FAIL ") + text)
    return ok


def _rev_growth(m, basis: str, prev: bool = False):
    key = f"rev_{basis}" + ("_prev" if prev else "")
    return m.get(key)


def long_setup(m: dict, price: dict, sector: str | None, cfg: dict) -> Verdict:
    lc = cfg["long"]
    reasons: list[str] = []
    checks = []
    if sector == "Financials":
        fc = cfg["financials"]["long"]
        rev = m.get("rev_yoy")
        checks.append(_check(reasons, _ok(rev) and rev >= fc["min_revenue_growth"],
                             f"revenue YoY {_pct(rev)} >= {fc['min_revenue_growth']:.0%}"))
        eps = m.get("eps_yoy")
        checks.append(_check(reasons, _ok(eps) and eps >= fc["min_eps_growth"],
                             f"EPS YoY {_pct(eps)} >= {fc['min_eps_growth']:.0%}"))
        roe = m.get("roe")
        checks.append(_check(reasons, _ok(roe) and roe >= fc["min_roe"], f"ROE {_pct(roe)} >= {fc['min_roe']:.0%}"))
    else:
        thr = cfg["sector_thresholds"].get(sector or "default", cfg["sector_thresholds"]["default"])
        basis = lc["revenue_growth_basis"]
        rev = _rev_growth(m, basis)
        checks.append(_check(reasons, _ok(rev) and rev >= thr["min_revenue_growth"],
                             f"revenue {basis.upper()} {_pct(rev)} >= {thr['min_revenue_growth']:.0%}"))

        eps, eps_base, eps_now = m.get("eps_yoy"), m.get("eps_prior_year"), m.get("eps")
        turnaround = lc["allow_eps_turnaround"] and _ok(eps_base) and eps_base <= 0 and _ok(eps_now) and eps_now > 0
        eps_ok = (_ok(eps) and eps >= thr["min_eps_growth"]) or turnaround
        label = "turnaround to positive EPS" if turnaround else f"EPS YoY {_pct(eps)} >= {thr['min_eps_growth']:.0%}"
        checks.append(_check(reasons, eps_ok, label))

        cfo = m.get("cfo_ttm")
        checks.append(_check(reasons, _ok(cfo) and cfo > 0, f"operating cash flow TTM {_usd(cfo)} > 0"))

        fcf, capex_ratio = m.get("fcf_ttm"), m.get("capex_ratio")
        exempt = _ok(capex_ratio) and capex_ratio >= lc["capex_exempt_ratio"]
        fcf_ok = (_ok(fcf) and fcf > 0) or exempt
        checks.append(_check(reasons, fcf_ok, f"FCF TTM {_usd(fcf)} > 0"
                             + (f" (exempt: capex {capex_ratio:.0%} of revenue)" if exempt and not (_ok(fcf) and fcf > 0) else "")))

        net_cash, runway = m.get("net_cash"), m.get("runway_years")
        years = lc["min_runway_years"]
        if _ok(net_cash) and net_cash >= 0:
            cash_ok, text = True, f"net cash {_usd(net_cash)}"
        elif m.get("runway_is_payback"):
            cash_ok = _ok(runway) and runway <= years
            text = f"net debt {_usd(-net_cash)} repayable from FCF in {runway:.1f}y <= {years}y" if _ok(runway) else "net debt, payback n/a"
        else:
            cash_ok = _ok(runway) and runway >= years
            text = f"cash runway {runway:.1f}y >= {years}y" if _ok(runway) else "net cash n/a"
        checks.append(_check(reasons, cash_ok, text))

    dd = price.get("drawdown")
    checks.append(_check(reasons, _ok(dd) and dd >= lc["min_drawdown_from_high"],
                         f"{_pct(-dd if _ok(dd) else dd)} from 52-week high (need <= -{lc['min_drawdown_from_high']:.0%})"))
    return Verdict(all(checks), reasons, sum(checks))


def short_fundamentals(m: dict, sector: str | None, cfg: dict) -> Verdict:
    sc = cfg["short"]
    reasons: list[str] = []
    basis = sc["revenue_growth_basis"]
    rev, rev_prev = _rev_growth(m, basis), _rev_growth(m, basis, prev=True)
    slowdown = sc.get("revenue_slowdown_min", 0.0)
    conds = [_check(reasons, _ok(rev) and _ok(rev_prev) and rev <= rev_prev - slowdown,
                    f"revenue growth slowing ({basis.upper()} {_pct(rev)} vs {_pct(rev_prev)} prior quarter)")]
    eps, base = m.get("eps"), m.get("eps_prior_year")
    conds.append(_check(reasons, _ok(eps) and _ok(base) and eps < base, f"EPS falling ({_num(eps)} vs {_num(base)} a year ago)"))

    if sector == "Financials":
        roe, roe_prev = m.get("roe"), m.get("roe_prev")
        conds.append(_check(reasons, _ok(roe) and _ok(roe_prev) and roe < roe_prev, f"ROE falling ({_pct(roe)} vs {_pct(roe_prev)})"))
        eg = m.get("equity_growth")
        conds.append(_check(reasons, _ok(eg) and eg < 0, f"book equity shrinking ({_pct(eg)} YoY)"))
        need = cfg["financials"]["short"]["min_conditions"]
    else:
        fcf, p1, p2 = m.get("fcf_ttm"), m.get("fcf_ttm_prev"), m.get("fcf_ttm_prev2")
        worsening = _ok(fcf) and _ok(p1) and _ok(p2) and fcf < p1 < p2
        conds.append(_check(reasons, (_ok(fcf) and fcf < 0) or worsening,
                            f"free cash flow negative or worsening (TTM {_usd(fcf)}, prior {_usd(p1)}, {_usd(p2)})"))
        dg = m.get("debt_growth")
        conds.append(_check(reasons, _ok(dg) and dg > sc["debt_rise_min"], f"debt rising ({_pct(dg)} YoY)"))
        need = sc["min_conditions"]
    met = sum(conds)
    reasons.append(f"{met} of 4 deterioration signals (need {need})")
    return Verdict(met >= need, reasons, met)


def short_setup(m: dict, price: dict, sector: str | None, cfg: dict, runup_cutoff: float | None) -> Verdict:
    """`runup_cutoff` is the universe-wide 3-month return at the configured top fraction."""
    sc = cfg["short"]
    v = short_fundamentals(m, sector, cfg)
    ret, gap = price.get("ret_runup"), price.get("max_gap")
    top = _ok(ret) and runup_cutoff is not None and ret >= runup_cutoff
    gapped = _ok(gap) and gap >= sc["gap_up_min"]
    ran_up = _check(v.reasons, top or gapped,
                    f"run-up: {sc['runup_lookback_days']}d return {_pct(ret)} (top-{sc['runup_top_fraction']:.0%} cutoff {_pct(runup_cutoff)}),"
                    f" biggest 1-day jump in {sc['gap_window_days']}d {_pct(gap)}")
    return Verdict(v.passed and ran_up, v.reasons, v.conditions_met)


def _usd(x) -> str:
    if not _ok(x) or not math.isfinite(x):
        return "n/a"
    sign = "-" if x < 0 else ""
    x = abs(x)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if x >= div:
            return f"{sign}${x / div:.1f}{unit}"
    return f"{sign}${x:.0f}"


def _num(x) -> str:
    return f"{x:.2f}" if _ok(x) else "n/a"
