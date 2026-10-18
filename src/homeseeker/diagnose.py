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


def otodom_pagination() -> None:
    """Why do later Otodom result pages contain only a handful of items?"""
    from collections import Counter
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    from .http import Http, dig
    from .preferences import load_preferences
    from .sources import otodom

    prefs = load_preferences()
    http = Http(delay=1.0)

    def with_params(url: str, **changes) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        for key, value in changes.items():
            if value is None:
                query.pop(key, None)
            else:
                query[key] = value
        return urlunsplit(parts._replace(query=urlencode(query)))

    seen: set = set()
    experiments = [
        ("latest", {}, [1, 2, 6, 12, 16, 22, 31]),
        ("default-sort", {"by": None, "direction": None}, [1, 12, 22]),
        ("limit36", {"limit": "36"}, [12, 24, 40]),
        ("no-rooms-filter", {"roomsNumber": None}, [1, 12]),
    ]
    try:
        for name, changes, pages in experiments:
            seen.clear()
            for page in pages:
                url = with_params(otodom.search_url(prefs, page), **changes)
                try:
                    data = http.get_next_data(url)
                except Exception as e:  # diagnostic: report and go on
                    print(f"[{name}] page {page}: ERROR {e}")
                    continue
                search = dig(data, "props", "pageProps", "data", "searchAds") or {}
                items = search.get("items") or []
                ids = [i.get("id") for i in items]
                overlap = len(set(ids) & seen)
                seen.update(ids)
                estates = Counter(i.get("estate") for i in items)
                promoted = sum(1 for i in items if i.get("isPromoted"))
                units = sum(i.get("investmentUnitsNumber") or 0 for i in items)
                print(
                    f"[{name}] page {page}: items={len(items)} unique={len(set(ids))} "
                    f"overlap_prev={overlap} estates={dict(estates)} promoted={promoted} "
                    f"investment_units={units} pagination={search.get('pagination')}"
                )
                if name == "latest" and page == 12:
                    print("   searchAds keys:", list(search.keys()))
                    print("   data keys:", list(dig(data, "props", "pageProps", "data") or {}))
    finally:
        http.close()


def otodom_investment() -> None:
    """Print the structure of an Otodom investment page and its list of units."""
    from .cli import _key_tree
    from .http import Http, dig
    from .preferences import load_preferences
    from .sources import otodom

    prefs = load_preferences()
    http = Http(delay=1.0)
    try:
        investment = None
        for page in (12, 16, 22):
            data = http.get_next_data(otodom.search_url(prefs, page))
            items = dig(data, "props", "pageProps", "data", "searchAds", "items") or []
            investment = next((i for i in items if i.get("estate") == "INVESTMENT"), None)
            if investment:
                break
        if not investment:
            print("no investment found")
            return
        print("\n".join(_key_tree(investment, "inv", max_depth=3)))
        url = f"{otodom.BASE}/pl/oferta/{investment['slug']}"
        ad = dig(http.get_next_data(url), "props", "pageProps", "ad") or {}
        print("ad keys:", list(ad))
        for key in ("paginatedUnits", "unitGroups"):
            print("\n".join(_key_tree(ad.get(key), f"ad.{key}", max_depth=6)[:120]))
        print("\n".join(_key_tree(ad.get("attributes"), "ad.attributes", max_depth=2)))
        print("ad.location.coordinates:", dig(ad, "location", "coordinates"))
    finally:
        http.close()
