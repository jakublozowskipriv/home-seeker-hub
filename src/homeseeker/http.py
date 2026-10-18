"""Polite HTTP client with retries and a delay between requests.

Otodom and OLX sit behind CloudFront rules that reject non-browser TLS fingerprints,
so requests go through curl_cffi impersonating Chrome.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from curl_cffi import requests as creq
from curl_cffi.requests.exceptions import RequestException

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S
)


class FetchError(RuntimeError):
    pass


class Http:
    def __init__(self, delay: float = 1.5, retries: int = 3, timeout: float = 30):
        self.delay = delay
        self.retries = retries
        self._last = 0.0
        # The impersonation profile sets a matching User-Agent and browser headers.
        self.client = creq.Session(
            impersonate="chrome",
            timeout=timeout,
            headers={"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8"},
        )
        self.requests = 0

    def _wait(self) -> None:
        pause = self.delay * random.uniform(0.7, 1.3) - (time.monotonic() - self._last)
        if pause > 0:
            time.sleep(pause)
        self._last = time.monotonic()

    def get(self, url: str, **kwargs: Any) -> creq.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self._wait()
            self.requests += 1
            try:
                resp = self.client.get(url, **kwargs)
            except RequestException as e:
                last_error = e
            else:
                if resp.status_code == 200:
                    return resp
                if resp.status_code not in (429, 500, 502, 503, 504):
                    raise FetchError(f"HTTP {resp.status_code} for {resp.url}")
                last_error = FetchError(f"HTTP {resp.status_code} for {resp.url}")
            backoff = 2 ** (attempt + 1)
            log.warning("Request failed (%s), retrying in %ss", last_error, backoff)
            time.sleep(backoff)
        raise FetchError(str(last_error))

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    def get_next_data(self, url: str, **kwargs: Any) -> dict:
        """Fetch a Next.js page and return its embedded __NEXT_DATA__ JSON."""
        resp = self.get(url, **kwargs)
        m = _NEXT_DATA_RE.search(resp.text)
        if not m:
            raise FetchError(f"No __NEXT_DATA__ in {resp.url} ({len(resp.text)} bytes)")
        return json.loads(m.group(1))

    def close(self) -> None:
        self.client.close()


def dig(data: Any, *path: str | int, default: Any = None) -> Any:
    """Safe nested lookup: dig(d, "a", 0, "b")."""
    for key in path:
        try:
            data = data[key]
        except (KeyError, IndexError, TypeError):
            return default
        if data is None:
            return default
    return data
