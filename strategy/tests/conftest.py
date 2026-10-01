import sys
from pathlib import Path

try:
    import pandas  # noqa: F401
    import requests  # noqa: F401
    import yaml  # noqa: F401
except ImportError:  # strategy deps not installed (e.g. running the repo-root test suite)
    collect_ignore_glob = ["*"]

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
