"""Tracker storage: a Supabase row when configured, otherwise a local JSON file.

The whole tracker is one JSON document. Writes go through `commit(mutate)`, which
re-reads the latest document, applies the change, and only writes if nobody else
saved in between (checked with the `rev` counter). On a clash it retries against the
fresh copy, so two people editing different things never overwrite each other.
"""

import copy
import datetime as dt
import json
import os
from pathlib import Path

import requests

from seed import SEED

DATA_FILE = Path(os.environ.get("TRACKER_FILE", Path(__file__).parent / "data" / "tracker.json"))
TIMEOUT = 15


class Conflict(Exception):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class FileStore:
    shared = False
    label = "local file (not shared)"

    def read(self):
        if DATA_FILE.exists():
            with DATA_FILE.open() as f:
                doc = json.load(f)
            return doc["data"], doc["rev"], doc.get("updated_by"), doc.get("updated_at")
        return copy.deepcopy(SEED), 0, None, None

    def write(self, data, rev, who) -> bool:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump({"data": data, "rev": rev + 1, "updated_by": who, "updated_at": _now()}, f, indent=2, default=str)
        tmp.replace(DATA_FILE)
        return True


class SupabaseStore:
    shared = True
    label = "Supabase (shared)"

    def __init__(self, url: str, key: str, table: str = "tracker"):
        self.endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        # New sb_ keys go in `apikey` only; legacy JWT keys also need the Bearer header.
        if not key.startswith("sb_"):
            self.headers["Authorization"] = f"Bearer {key}"

    def _req(self, method, params=None, body=None, prefer=None):
        headers = dict(self.headers, **({"Prefer": prefer} if prefer else {}))
        r = requests.request(method, self.endpoint, params=params, json=body, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json() if r.content else None

    def read(self):
        params = {"id": "eq.1", "select": "data,rev,updated_by,updated_at"}
        rows = self._req("GET", params)
        if not rows:
            # First run: seed the row. ignore-duplicates makes a race with the other user harmless.
            self._req("POST", body={"id": 1, "data": SEED, "rev": 0},
                      prefer="resolution=ignore-duplicates,return=minimal")
            rows = self._req("GET", params)
        row = rows[0]
        return row["data"], row["rev"], row["updated_by"], row["updated_at"]

    def write(self, data, rev, who) -> bool:
        rows = self._req(
            "PATCH",
            params={"id": "eq.1", "rev": f"eq.{rev}"},
            body={"data": data, "rev": rev + 1, "updated_by": who, "updated_at": _now()},
            prefer="return=representation",
        )
        return bool(rows)


def get_store(secrets) -> "FileStore | SupabaseStore":
    try:
        cfg = secrets["supabase"]
        return SupabaseStore(cfg["url"], cfg["key"], cfg.get("table", "tracker"))
    except (KeyError, FileNotFoundError):  # no secrets file, or no [supabase] section
        return FileStore()


def commit(store, mutate, who: str, attempts: int = 4) -> None:
    """Apply `mutate(data)` to the latest copy and save it, retrying if someone else saved first."""
    for _ in range(attempts):
        data, rev, _, _ = store.read()
        mutate(data)
        if store.write(data, rev, who):
            return
    raise Conflict("Someone else kept saving at the same moment. Try again.")
