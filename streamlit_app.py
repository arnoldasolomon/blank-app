import datetime as dt
import json
import re

import pandas as pd
import streamlit as st

from seed import CASHFLOW
from store import Conflict, commit, get_store

STATUSES = ["Idea", "Researching", "Active", "Blocked", "On hold", "Done"]
PRIORITIES = ["High", "Medium", "Low"]
STATUS_COLORS = {
    "Idea": "#9aa5b1",
    "Researching": "#4c8dd6",
    "Active": "#2e9e5b",
    "Blocked": "#d64545",
    "On hold": "#c9a227",
    "Done": "#6b5bd6",
}


# ---------- helpers ----------

def add_log(data: dict, ws_id: str, note: str, who: str) -> None:
    data["log"].insert(0, {"date": dt.date.today().isoformat(), "workstream": ws_id, "note": note, "by": who})


def find(data: dict, ws_id: str):
    return next((w for w in data["workstreams"] if w["id"] == ws_id), None)

def task_progress(ws: dict) -> float:
    tasks = ws["tasks"]
    return sum(t["done"] for t in tasks) / len(tasks) if tasks else 0.0


def next_due(ws: dict):
    dues = [t["due"] for t in ws["tasks"] if t["due"] and not t["done"]]
    return min(dues) if dues else None


def metric_text(m: dict) -> str:
    return f"{m['label']}: {m['current']:g}/{m['target']:g}" if m.get("target") else ""


def slug(name: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "ws"
    s, i = base, 2
    while s in taken or s == CASHFLOW:
        s, i = f"{base}_{i}", i + 1
    return s


def flowchart(data: dict) -> str:
    lines = [
        "digraph G {",
        'rankdir=LR; bgcolor="transparent"; nodesep=0.4; ranksep=0.9;',
        'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, fontcolor="white", penwidth=0];',
        'edge [color="#8a94a0", arrowsize=0.7];',
        f'{CASHFLOW} [label="Cashflow", shape=ellipse, fillcolor="#1f2933", fontsize=13];',
    ]
    for ws in data["workstreams"]:
        pct = round(task_progress(ws) * 100)
        m = ws["metric"]
        metric = f"\\n{metric_text(m)}" if m.get("target") else ""
        label = f"{ws['name']}\\n{ws['status']} · {pct}% tasks{metric}".replace('"', "'")
        lines.append(f'{ws["id"]} [label="{label}", fillcolor="{STATUS_COLORS.get(ws["status"], "#9aa5b1")}"];')
    for ws in data["workstreams"]:
        style = ' [style="dashed"]' if ws["status"] == "On hold" else ""
        for target in ws.get("feeds", []):
            if target == CASHFLOW or any(w["id"] == target for w in data["workstreams"]):
                lines.append(f"{ws['id']} -> {target}{style};")
    lines.append("}")
    return "\n".join(lines)


def tasks_df(ws: dict) -> pd.DataFrame:
    df = pd.DataFrame(ws["tasks"], columns=["task", "done", "owner", "due"])
    df["due"] = pd.to_datetime(df["due"], errors="coerce").dt.date
    return df


def df_to_tasks(df: pd.DataFrame) -> list:
    out = []
    for r in df.to_dict("records"):
        if not isinstance(r.get("task"), str) or not r["task"].strip():
            continue
        due = r.get("due")
        out.append({
            "task": r["task"].strip(),
            "done": bool(r.get("done")) if pd.notna(r.get("done")) else False,
            "owner": r.get("owner") if isinstance(r.get("owner"), str) else "",
            "due": due.isoformat() if isinstance(due, dt.date) and pd.notna(due) else None,
        })
    return out


# ---------- UI ----------

st.set_page_config(page_title="Workstream Tracker", page_icon="🧭", layout="wide")
store = get_store(st.secrets)
data, _rev, saved_by, saved_at = store.read()
by_id = {ws["id"]: ws for ws in data["workstreams"]}
names = {ws["id"]: ws["name"] for ws in data["workstreams"]}
names[CASHFLOW] = "Cashflow"
# Form keys change only after this viewer's own save or a Refresh, so a save by the other person
# mid-edit doesn't swap the form out from under a pending submit.
gen = st.session_state.setdefault("gen", 0)


def viewer_email() -> str:
    try:
        return st.user.get("email") or ""
    except Exception:
        return ""


with st.sidebar:
    who = st.text_input("Your name", value=viewer_email(), key="who", help="Shown next to your updates in the log.")
    st.caption(f"Storage: {store.label}")
    if saved_at:
        st.caption(f"Last saved {saved_at[:16].replace('T', ' ')} UTC" + (f" by {saved_by}" if saved_by else ""))
    if st.button("Refresh", help="Pull in your partner's latest changes"):
        st.session_state.gen += 1
        st.rerun()
    if not store.shared:
        st.warning("Not connected to Supabase, so changes stay on this machine only. See README.")


def save(mutate) -> None:
    try:
        commit(store, mutate, who.strip())
    except Conflict as e:
        st.error(str(e))
        return
    st.session_state.gen += 1
    st.rerun()


st.title("🧭 Workstream Tracker")

overview, detail, log_tab, manage = st.tabs(["Overview", "Workstreams", "Update log", "Manage & backup"])

with overview:
    wss = data["workstreams"]
    active = [w for w in wss if w["status"] in ("Active", "Researching", "Blocked")]
    all_tasks = [t for w in wss for t in w["tasks"]]
    overdue = [
        (w["name"], t["task"]) for w in wss for t in w["tasks"]
        if t["due"] and not t["done"] and t["due"] < dt.date.today().isoformat()
    ]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Workstreams", len(wss))
    c2.metric("In motion", len(active))
    c3.metric("Tasks done", f"{sum(t['done'] for t in all_tasks)}/{len(all_tasks)}")
    c4.metric("Overdue tasks", len(overdue))

    if len(active) > 3:
        st.warning(
            f"{len(active)} workstreams are in motion at once. "
            "Consider which one or two actually produce cash first."
        )
    if overdue:
        st.error("Overdue: " + "; ".join(f"**{n}**: {t}" for n, t in overdue))

    st.subheader("Flow")
    st.caption("Arrows show what feeds what (edit under Workstreams → 'Feeds into'). Dashed = on hold.")
    st.graphviz_chart(flowchart(data), width="stretch")
    legend = " ".join(
        f"<span style='background:{c};color:white;padding:2px 8px;border-radius:6px;margin-right:4px'>{s}</span>"
        for s, c in STATUS_COLORS.items()
    )
    st.markdown(legend, unsafe_allow_html=True)

    st.subheader("Summary")
    rows = []
    for w in wss:
        m = w["metric"]
        rows.append({
            "Workstream": w["name"],
            "Status": w["status"],
            "Priority": w["priority"],
            "Owner": w["owner"],
            "Tasks": task_progress(w),
            "Metric": metric_text(m),
            "Next action": w["next_action"],
            "Next due": next_due(w) or "",
        })
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={"Tasks": st.column_config.ProgressColumn("Tasks", min_value=0, max_value=1, format="percent")},
    )

with detail:
    if not data["workstreams"]:
        st.info("No workstreams yet. Add one under Manage & backup.")
    else:
        ws_id = st.selectbox(
            "Workstream",
            [w["id"] for w in data["workstreams"]],
            format_func=lambda i: f"{by_id[i]['name']}  ({by_id[i]['status']})",
        )
        ws = by_id[ws_id]

        p1, p2 = st.columns(2)
        p1.progress(task_progress(ws), text=f"Tasks: {round(task_progress(ws) * 100)}%")
        m = ws["metric"]
        if m.get("target"):
            p2.progress(min(m["current"] / m["target"], 1.0), text=metric_text(m))

        if ws.get("risks"):
            st.warning(ws["risks"])

        with st.form(f"fields_{ws_id}_{gen}"):
            a, b, c = st.columns(3)
            status = a.selectbox("Status", STATUSES, index=STATUSES.index(ws["status"]))
            priority = b.selectbox("Priority", PRIORITIES, index=PRIORITIES.index(ws["priority"]))
            owner = c.text_input("Owner", ws["owner"])
            goal = st.text_area("Goal", ws["goal"], height=70)
            next_action = st.text_input("Next action", ws["next_action"])
            x, y, z = st.columns(3)
            m_label = x.text_input("Metric name", m["label"])
            m_current = y.number_input("Current", value=float(m["current"]), step=1.0)
            m_target = z.number_input("Target (0 = none)", value=float(m["target"]), min_value=0.0, step=1.0)
            feeds = st.multiselect(
                "Feeds into",
                [i for i in names if i != ws_id],
                default=[f for f in ws.get("feeds", []) if f in names and f != ws_id],
                format_func=lambda i: names[i],
            )
            risks = st.text_area("Risks / blockers", ws.get("risks", ""), height=70)
            if st.form_submit_button("Save details", type="primary"):
                def apply(d):
                    w = find(d, ws_id)
                    if w is None:
                        return
                    # Only write fields this form changed, so the other person's edits to
                    # other fields of the same workstream survive.
                    form = dict(
                        status=status, priority=priority, owner=owner, goal=goal,
                        next_action=next_action, feeds=feeds, risks=risks,
                        metric={"label": m_label, "current": m_current, "target": m_target},
                    )
                    changed = {k: v for k, v in form.items() if v != ws.get(k)}
                    changes = []
                    if "status" in changed:
                        changes.append(f"status {w['status']} → {status}")
                    if "metric" in changed and m_current != w["metric"]["current"]:
                        changes.append(f"{m_label} {w['metric']['current']:g} → {m_current:g}")
                    w.update(changed)
                    if changes:
                        add_log(d, ws_id, "; ".join(changes), who)
                save(apply)

        st.subheader("Tasks")
        with st.form(f"tasks_{ws_id}_{gen}"):
            edited = st.data_editor(
                tasks_df(ws),
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                column_config={
                    "task": st.column_config.TextColumn("Task", width="large", required=True),
                    "done": st.column_config.CheckboxColumn("Done", default=False),
                    "owner": st.column_config.TextColumn("Owner"),
                    "due": st.column_config.DateColumn("Due"),
                },
            )
            if st.form_submit_button("Save tasks", type="primary"):
                new_tasks = df_to_tasks(edited)

                def apply(d):
                    w = find(d, ws_id)
                    if w is None:
                        return
                    before = {t["task"] for t in w["tasks"] if t["done"]}
                    w["tasks"] = new_tasks
                    for t in new_tasks:
                        if t["done"] and t["task"] not in before:
                            add_log(d, ws_id, f"done: {t['task']}", who)
                save(apply)

        st.subheader("Recent updates")
        entries = [e for e in data["log"] if e["workstream"] == ws_id][:10]
        for e in entries:
            by = f" — {e['by']}" if e.get("by") else ""
            st.markdown(f"- `{e['date']}` {e['note']}{by}")
        if not entries:
            st.caption("No updates yet.")

with log_tab:
    with st.form(f"log_{gen}", clear_on_submit=True):
        a, b = st.columns([1, 3])
        target = a.selectbox("Workstream", list(names), format_func=lambda i: names[i])
        note = b.text_input("What happened?")
        if st.form_submit_button("Add update", type="primary") and note.strip():
            save(lambda d: add_log(d, target, note.strip(), who))

    filt = st.multiselect("Filter", list(names), format_func=lambda i: names[i])
    entries = [e for e in data["log"] if not filt or e["workstream"] in filt]
    if entries:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Date": e["date"], "Workstream": names.get(e["workstream"], e["workstream"]),
                     "Update": e["note"], "By": e.get("by", "")}
                    for e in entries
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("No updates logged yet.")

with manage:
    st.subheader("Add workstream")
    with st.form(f"add_{gen}", clear_on_submit=True):
        new_name = st.text_input("Name")
        new_goal = st.text_input("Goal")
        if st.form_submit_button("Add") and new_name.strip():
            def apply(d):
                new_id = slug(new_name, {w["id"] for w in d["workstreams"]})
                d["workstreams"].append({
                    "id": new_id, "name": new_name.strip(), "goal": new_goal, "status": "Idea",
                    "priority": "Medium", "owner": "", "next_action": "",
                    "metric": {"label": "Metric", "current": 0, "target": 0},
                    "feeds": [CASHFLOW], "risks": "", "tasks": [],
                })
                add_log(d, new_id, "workstream added", who)
            save(apply)

    st.subheader("Remove workstream")
    if data["workstreams"]:
        with st.form(f"remove_{gen}"):
            rm = st.selectbox("Workstream", list(by_id), format_func=lambda i: by_id[i]["name"])
            confirm = st.checkbox("Yes, delete it and its tasks")
            if st.form_submit_button("Delete") and confirm:
                def apply(d):
                    d["workstreams"] = [w for w in d["workstreams"] if w["id"] != rm]
                    for w in d["workstreams"]:
                        w["feeds"] = [f for f in w.get("feeds", []) if f != rm]
                save(apply)

    st.subheader("Backup")
    st.caption(
        "A snapshot of everything, in case something gets deleted by mistake."
        if store.shared else
        "Data is saved to a file on the machine running this app. On Streamlit Community Cloud that "
        "file is wiped when the app restarts, so connect Supabase or download a backup after updates."
    )
    st.download_button(
        "Download backup (JSON)",
        json.dumps(data, indent=2, default=str),
        file_name=f"tracker-{dt.date.today().isoformat()}.json",
        mime="application/json",
    )
    upload = st.file_uploader("Restore from backup", type="json")
    if upload is not None and st.button("Restore (overwrites current data)"):
        restored = json.load(upload)
        if isinstance(restored, dict) and isinstance(restored.get("workstreams"), list):
            restored.setdefault("log", [])
            restored.pop("rev", None)

            def apply(d):
                d.clear()
                d.update(restored)
            save(apply)
        else:
            st.error("That file doesn't look like a tracker backup.")
