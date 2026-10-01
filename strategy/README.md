# Catalyst long/short (S&P 500 + Nasdaq Composite)

A systematic, rules-based screener and backtester. It buys companies with strong fundamentals that have
sold off, and shorts companies whose financials are deteriorating after a run-up. Every trade needs an
SEC-filed catalyst. Longs and shorts are always opened in pairs. The rules produce a ranked list and the
PM makes the final call.

This folder is self-contained (own requirements, config and tests) so it can be moved to its own
repository unchanged. It has nothing to do with the MSME app at the repo root.

## Rules

All thresholds live in [`config.yaml`](config.yaml). Values marked `UNCONFIRMED` are placeholders the PM has
not yet signed off.

**Long** (non-financials, all required):

| Rule | Default |
|---|---|
| Revenue growth, this quarter vs previous quarter (`qoq`) or vs same quarter last year (`yoy`) | ≥ 30% (tech, healthcare, consumer discretionary, communication); lower for other sectors |
| EPS growth, this quarter vs same quarter last year (diluted) | ≥ 15%; a move from a loss to a profit also passes |
| Operating cash flow, trailing 12 months | > 0 |
| Free cash flow, trailing 12 months | > 0, unless capex ≥ 15% of revenue |
| Balance sheet | cash + short-term investments ≥ total debt; or ≥ 5 years of cash runway (cash burners); or net debt repayable from FCF within 5 years |
| Price | ≥ 15% below the 52-week high |
| Catalyst | at least one of: insider open-market buy, activist 13D, earnings release in the last 30 days |

**Short** (at least 2 of the 4 deterioration signals, plus a run-up and a catalyst):

- revenue growth slowing (this quarter's YoY growth below last quarter's)
- EPS below the same quarter last year
- free cash flow negative, or down two quarters in a row
- total debt higher than a year ago
- run-up: 3-month return in the top 10% of the universe, or a one-day jump of ≥ 15% in the last 20 days (the Oracle case)
- catalyst: 8-K non-reliance/restatement, auditor change, late-filing notice, share offering, 2+ insiders selling, executive change, or earnings release

**Financials** (banks, lenders, BNPL): free cash flow and net cash are meaningless for a balance sheet built on
deposits and loans, so longs need revenue YoY ≥ 10%, EPS YoY ≥ 15% and ROE ≥ 12%. For shorts, ROE falling
and book equity shrinking replace the cash-flow and debt signals.

**Ranking** is catalyst score plus the stock's revenue/EPS growth percentile within its own sector, so a
utility is compared with utilities, not with software companies.

**Portfolio**: signals on the last trading day of each week, fills at the next open. At most 2 positions per
side with $1,000 max each, equal-weighted or scaled by catalyst score. A long is only opened alongside a short.
A position closes when its setup fails (`exit_mode: full` re-checks every entry rule except the catalyst;
`fundamentals` re-checks only the financial rules). Costs are a CFD spread per side plus overnight financing.

## Data (free)

- **SEC EDGAR**: XBRL company facts (fundamentals), submissions (SIC code, filing index for catalysts) and Form 4
  XML (insider trades). Values are point-in-time: first-filed figures, usable from the filing date.
- **Yahoo Finance** via `yfinance`: daily prices, benchmarks (SPY, QQQ, ^IXIC) and the 13-week T-bill rate.
- **S&P 500 membership history**: [fja05680/sp500](https://github.com/fja05680/sp500).

## Run

```
cd strategy
pip install -r requirements.txt
python -m catalyst_ls --set data.sec_user_agent="catalyst-ls you@yourdomain.com" scan
python -m catalyst_ls backtest --start 2012-01-01
python -m catalyst_ls --tickers NVDA AMD INTC ORCL scan          # quick check (run-up percentile is then relative to these names only)
python -m catalyst_ls --set long.revenue_growth_basis=yoy backtest   # compare rule variants
python -m catalyst_ls dashboard                                   # output/dashboard.html from the latest scan + backtest
```

The dashboard shows the rules (read live from `config.yaml`), a worked example produced by running the real
engine on synthetic data, the latest scan, the latest backtest and the settings still awaiting sign-off.

SEC rejects requests without a real contact in the User-Agent; set `data.sec_user_agent` in `config.yaml`.
The first run downloads fundamentals for roughly 4,000 companies (rate-limited to 8 requests/second, so expect
tens of minutes). Later runs read from `.cache/`. Reports are written to `output/`.

To check exits on live positions, copy `positions.example.yaml` to `positions.yaml` and list what you hold.

From Claude Code, ask Claude to "run the stock scan" (skill: `.claude/skills/stock-scan`).

## Known limitations

- **Survivorship bias**: the Nasdaq universe is today's listing, and Yahoo has no prices for most delisted
  tickers. Backtests will flatter the long book and miss the best historical shorts (companies that went bust).
  Fixing this needs paid data (e.g. Norgate, Sharadar).
- **Backtest start**: structured XBRL data covers all filers from about 2011, so backtests start in 2012.
- **Catalysts**: analyst estimate revisions, guidance and buyback announcements are not available free and are
  not covered.
- **Derived values**: Q4 and quarterly cash-flow figures are derived from year-to-date filings. Q4 EPS derived as
  annual minus nine months is approximate.
- **Not modelled**: the PM's discretionary final call, and whether eToro/IG will actually let you short a given name.

## Tests

```
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

Tests use synthetic SEC filings and prices, so they run offline.
