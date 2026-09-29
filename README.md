# 🧭 Workstream Tracker

A Streamlit dashboard for tracking our workstreams: Nifty lots, Sir's job, Reselling, GTM, AI app/website, and YouTube (on hold).

- **Overview**: headline numbers, a flowchart of what feeds into cashflow (colour = status, dashed = on hold), and a summary table.
- **Workstreams**: edit status, priority, owner, goal, next action, a target metric (e.g. Nifty lots 0/4), risks, what the stream feeds into, and its task list.
- **Update log**: a dated feed of progress notes. Status changes, metric changes, and completed tasks are logged automatically.
- **Manage & backup**: add or remove workstreams, and download or restore a JSON backup.

The starting tasks are in `seed.py`. They are only a first cut, so edit them in the app.

## Run it

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Where data lives

Saved to `data/tracker.json`, which git ignores. Set `TRACKER_FILE` to use a different path.
On Streamlit Community Cloud this file is **wiped on every restart or redeploy**, so download a backup
after big updates. If the tracker needs to be durable and shared, move storage to a database.
