"""SEC EDGAR client with on-disk caching and the SEC's fair-access rate limit."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

DAY = 86400


class SecClient:
    def __init__(self, cache_dir: str | Path, user_agent: str, max_rps: float = 8, max_age_days: float = 1):
        self.cache = Path(cache_dir) / "sec"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.min_interval = 1.0 / max_rps
        self.max_age = max_age_days * DAY
        self._last = 0.0

    def _get(self, url: str) -> bytes:
        for attempt in range(4):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                raise FileNotFoundError(url)
            if resp.status_code in (429, 503):
                time.sleep(2 ** (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.content
        resp.raise_for_status()
        return resp.content

    def _cached(self, key: str, url: str, max_age: float | None) -> bytes:
        path = self.cache / key
        if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
            return path.read_bytes()
        data = self._get(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    def tickers(self) -> list[dict]:
        raw = json.loads(self._cached("company_tickers_exchange.json", TICKERS_URL, self.max_age))
        return [dict(zip(raw["fields"], row)) for row in raw["data"]]

    def submissions(self, cik: int) -> dict:
        """Company metadata plus every filing, merging the paginated history files."""
        name = f"CIK{cik:010d}.json"
        sub = json.loads(self._cached(f"submissions/{name}", SUBMISSIONS_URL.format(name=name), self.max_age))
        filings = {k: list(v) for k, v in sub["filings"]["recent"].items()}
        for extra in sub["filings"].get("files", []):
            # Older pages never change, so cache them forever.
            page = json.loads(self._cached(f"submissions/{extra['name']}", SUBMISSIONS_URL.format(name=extra["name"]), None))
            for k, v in page.items():
                filings.setdefault(k, []).extend(v)
        sub["all_filings"] = filings
        return sub

    def company_facts(self, cik: int) -> dict:
        return json.loads(self._cached(f"facts/CIK{cik:010d}.json", FACTS_URL.format(cik=cik), self.max_age))

    def archive_document(self, cik: int, accession: str, document: str) -> bytes:
        # primaryDocument for XML forms points at the XSL-rendered view; the raw XML sits one level up.
        if "/" in document and document.split("/")[0].startswith("xsl"):
            document = document.split("/", 1)[1]
        acc = accession.replace("-", "")
        url = ARCHIVE_URL.format(cik=int(cik), accession=acc, document=document)
        return self._cached(f"archive/{cik}/{acc}/{document}", url, None)
