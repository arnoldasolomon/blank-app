---
name: stock-scan
description: Run the catalyst long/short screener (strategy/) for today, or a backtest, and summarise the ranked long and short candidates and any open positions that should be exited. Use when asked to scan, screen, run the daily scan, or backtest the strategy.
---

# Daily catalyst long/short scan

1. Install dependencies once per session: `pip install -q -r strategy/requirements.txt`.
2. If `strategy/config.yaml` still has `sec_user_agent` set to the `contact@example.com` placeholder, ask the user for a contact
   email for SEC requests before running (SEC blocks anonymous clients). Pass it with
   `--set data.sec_user_agent="catalyst-ls research <email>"` rather than guessing one.
3. Run from `strategy/`: `python -m catalyst_ls scan` (add `--date YYYY-MM-DD` for a past date).
   The first run downloads SEC fundamentals for the whole universe and takes a while; later runs use `.cache/`.
4. The report is printed and saved to `strategy/output/scan_<date>.md`. Summarise for the user:
   - how many paired trades are available (a long is only taken together with a short),
   - the top long and short candidates with their catalyst and the rule lines that passed,
   - every open position from `strategy/positions.yaml` marked EXIT, with the failing rule.
   Do not recommend trades beyond what the report shows; the user makes the final call.
5. Rebuild the dashboard with `python -m catalyst_ls dashboard` after a scan or backtest. If an artifact for it was
   published before, republish `strategy/output/dashboard.html` to the same artifact URL.
6. For a backtest: `python -m catalyst_ls backtest [--start YYYY-MM-DD] [--no-insiders]`. Report the
   strategy vs SPY/QQQ/^IXIC table, trade count and the "Known biases" section verbatim.

If SEC or Yahoo requests fail with 403 or connection errors, the environment's network policy is blocking
`*.sec.gov` / `*.yahoo.com`; tell the user rather than retrying.
