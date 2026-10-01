from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load(path: str | Path | None = None, overrides: list[str] | None = None) -> dict:
    path = Path(path or DEFAULT_PATH)
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    cache = Path(cfg["data"]["cache_dir"])
    if not cache.is_absolute():
        cfg["data"]["cache_dir"] = str(path.resolve().parent / cache)
    for item in overrides or []:
        key, _, raw = item.partition("=")
        set_path(cfg, key, yaml.safe_load(raw))
    return cfg


def set_path(cfg: dict, dotted: str, value) -> None:
    node = cfg
    *parents, leaf = dotted.split(".")
    for part in parents:
        node = node.setdefault(part, {})
    node[leaf] = value


def with_overrides(cfg: dict, **dotted) -> dict:
    out = copy.deepcopy(cfg)
    for key, value in dotted.items():
        set_path(out, key.replace("__", "."), value)
    return out
