"""Check which portals are reachable from the current machine and with which client.

Run in CI to see how portals treat datacenter IPs: status code, blocking vendor
headers and a body snippet for each URL x client combination.
"""

from __future__ import annotations

import re

import httpx

from .http import USER_AGENT

URLS = {
    "otodom": "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/wielkopolskie/poznan/poznan/poznan",
    "olx-api": "https://www.olx.pl/api/v1/offers/?limit=1&category_id=14",
    "olx-html": "https://www.olx.pl/nieruchomosci/mieszkania/sprzedaz/poznan/",
    "morizon": "https://www.morizon.pl/mieszkania/poznan/",
    "gratka": "https://gratka.pl/nieruchomosci/mieszkania/poznan/sprzedaz",
    "nieruchomosci-online": "https://poznan.nieruchomosci-online.pl/mieszkania,sprzedaz/",
    "domiporta": "https://www.domiporta.pl/mieszkanie/sprzedam/wielkopolskie/poznan",
    "adresowo": "https://adresowo.pl/mieszkania/poznan/",
    "rynekpierwotny": "https://rynekpierwotny.pl/s/nowe-mieszkania-poznan/",
}

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
    "*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="129", "Not=A?Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

INTERESTING_HEADERS = [
    "server",
    "cf-mitigated",
    "cf-ray",
    "x-datadome",
    "x-amz-cf-pop",
    "akamai-grn",
    "x-cache",
    "set-cookie",
]


def _summary(status: int, headers, body: str) -> str:
    hdrs = {h: headers.get(h)[:60] for h in INTERESTING_HEADERS if headers.get(h)}
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    snippet = (title.group(1).strip() if title else body[:120]).replace("\n", " ")[:120]
    next_data = "__NEXT_DATA__" in body
    return f"{status} next_data={next_data} len={len(body)} {hdrs} | {snippet}"


def _httpx(url: str, headers: dict) -> str:
    with httpx.Client(timeout=20, follow_redirects=True, headers=headers) as c:
        r = c.get(url)
        return _summary(r.status_code, r.headers, r.text)


def _curl_cffi(url: str) -> str:
    from curl_cffi import requests as creq

    r = creq.get(
        url,
        impersonate="chrome",
        timeout=20,
        headers={"Accept-Language": BROWSER_HEADERS["Accept-Language"]},
    )
    return _summary(r.status_code, r.headers, r.text)


def diagnose() -> None:
    clients = {
        "httpx-basic": lambda u: _httpx(u, {"User-Agent": USER_AGENT}),
        "httpx-browser": lambda u: _httpx(u, BROWSER_HEADERS),
        "curl_cffi-chrome": _curl_cffi,
    }
    for name, url in URLS.items():
        print(f"== {name}: {url}")
        for client, fn in clients.items():
            try:
                print(f"   {client:18} {fn(url)}")
            except Exception as e:  # report everything, this is a diagnostic
                print(f"   {client:18} ERROR {type(e).__name__}: {str(e)[:150]}")
