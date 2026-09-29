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

The tracker is one row in the Supabase project **workstream-tracker** (table `public.tracker`,
Mumbai region), so everyone using the app sees and edits the same data.

- Each save re-reads the latest data, applies only that change, and writes it back only if nobody
  saved in between. So two people editing at once don't overwrite each other. The one exception is
  both editing the *same* field or the *same* task list at once: then the later save wins.
- Your partner's changes appear the next time your page reruns (any click, or **Refresh** in the sidebar).
- The log records who made each update, using the "Your name" box in the sidebar.

### Connect it

1. Supabase dashboard → project *workstream-tracker* → **Project Settings → API Keys** → copy a **secret key** (`sb_secret_...`).
2. Streamlit Community Cloud → your app → **Settings → Secrets**, paste the contents of
   `.streamlit/secrets.toml.example` with your key filled in. For local runs, save it as `.streamlit/secrets.toml` (git ignores it).
3. The first load writes the starting data into the table.

The table has row-level security turned on and no public access. Only the secret key can read or write it,
and that key stays on the Streamlit server. That means **anyone who can open the app can edit the tracker**,
so make the app private (Streamlit Cloud → app → **Share** → invite only you and your partner by email).

Without secrets, the app falls back to a local file (`data/tracker.json`, or `TRACKER_FILE`) and says so in the sidebar.
