"""What surrounds a listing: tram commute (ZTM timetable), nearby stops and shops, and the
land parcel it stands on. Loaded once per run and handed to the evaluation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from . import geo
from .db import Store, now
from .http import FetchError, Http
from .transit import FEED_URL, Journey, Router, parse_feed

log = logging.getLogger(__name__)

# Overpass rejects browser-like clients (HTTP 406): plain client that says who it is.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_AGENT = "home-seeker-hub/1.0 (+https://github.com/jakublozowskipriv/home-seeker-hub)"
POZNAN_BBOX = (52.29, 16.73, 52.52, 17.08)  # south, west, north, east
GROCERY = "supermarket|convenience|greengrocer|bakery|butcher"
SHOPS_QUERY = '[out:json][timeout:90];nwr["shop"~"^({kinds})$"]({s},{w},{n},{e});out center tags;'
SHOPS_REFRESH = timedelta(days=7)
SHOPS_RADIUS_M = 500
ULDK_URL = "https://uldk.gugik.gov.pl/"


def parse_shops(data: dict) -> list[list]:
    """Overpass JSON -> [lat, lon, kind, name] (ways and areas come with a centre point)."""
    out = []
    for el in data.get("elements") or []:
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        tags = el.get("tags") or {}
        if lat is None or lon is None:
            continue
        name = tags.get("brand") or tags.get("name") or ""
        out.append([round(lat, 6), round(lon, 6), tags.get("shop", ""), name])
    return out


def fetch_shops() -> list[list]:
    s, w, n, e = POZNAN_BBOX
    query = SHOPS_QUERY.format(kinds=GROCERY, s=s, w=w, n=n, e=e)
    errors = []
    with httpx.Client(timeout=120, headers={"User-Agent": OVERPASS_AGENT}) as client:
        for url in OVERPASS_URLS:
            try:
                resp = client.post(url, data={"data": query})
                resp.raise_for_status()
                return parse_shops(resp.json())
            except (httpx.HTTPError, ValueError) as err:
                errors.append(f"{httpx.URL(url).host}: {err}")
    raise FetchError("; ".join(errors))


def load_shops(store: Store, http: Http | None) -> tuple[list[list], str | None]:
    """Grocery shops in Poznań from OpenStreetMap, cached in the database for a week."""
    cached = store.get_setting("shops") or {}
    fetched = cached.get("fetched_at")
    if http is not None and (
        not fetched or now() - datetime.fromisoformat(fetched) > SHOPS_REFRESH
    ):
        try:
            items = fetch_shops()
        except FetchError as err:
            log.warning("Shops (OpenStreetMap) not refreshed: %s", err)
        else:
            if items:
                cached = {"fetched_at": now().isoformat(), "items": items}
                store.set_setting("shops", cached)
                log.info("Shops: %s from OpenStreetMap", len(items))
    return cached.get("items") or [], cached.get("fetched_at", "")[:10] or None


def parse_parcel(text: str) -> dict | None:
    """ULDK answer: status line ("0" = found), then "id|region|parcel"."""
    lines = [line.strip() for line in text.strip().splitlines()]
    if len(lines) < 2 or lines[0] != "0":
        return None
    parcel_id, region, number = ([*lines[1].split("|"), "", ""])[:3]
    if not parcel_id:
        return None
    return {"id": parcel_id, "region": region, "number": number}


class Area:
    def __init__(
        self,
        router: Router | None = None,
        shops: list[list] | None = None,
        shops_version: str | None = None,
        http: Http | None = None,
    ):
        self.router = router
        self.shops = shops or []
        self.shops_version = shops_version
        self.shop_index = geo.GridIndex([(s[0], s[1]) for s in self.shops])
        self.http = http

    @property
    def version(self) -> str:
        """Changes when commute times or surroundings may change (re-evaluation trigger)."""
        transit = self.router.feed.version if self.router else "estimate"
        return f"transit:{transit}|shops:{self.shops_version}"

    def journey(
        self, lat: float, lon: float, dest_lat: float, dest_lon: float, arrive_by: str
    ) -> Journey | None:
        if self.router is None:
            return None
        return self.router.journey(lat, lon, dest_lat, dest_lon, arrive_by)

    def nearby(self, lat: float, lon: float) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.router is not None:
            for mode in ("tram", "bus"):
                if stop := self.router.nearest_stop(lat, lon, mode):
                    out[f"{mode}_stop"] = {"name": stop[0], "m": round(stop[1])}
        if self.shops:
            close = self.shop_index.near(lat, lon, 1500)
            supermarkets = [(i, m) for i, m in close if self.shops[i][2] == "supermarket"]
            supermarket = supermarkets[0] if supermarkets else None
            if supermarket:
                i, metres = supermarket
                out["supermarket"] = {"name": self.shops[i][3] or "supermarket", "m": round(metres)}
            out["shops_500m"] = sum(1 for _, m in close if m <= SHOPS_RADIUS_M)
        return out

    def parcel(self, lat: float, lon: float) -> dict | None:
        """Cadastral parcel at a point (GUGiK ULDK). Raises FetchError when unreachable."""
        if self.http is None:
            return None
        x, y = geo.to_puwg1992(lat, lon)
        resp = self.http.get(
            ULDK_URL,
            params={
                "request": "GetParcelByXY",
                "xy": f"{x:.2f},{y:.2f}",
                "result": "id,region,parcel",
            },
            retries=1,
        )
        return parse_parcel(resp.text)


def load_area(store: Store, http: Http, modes: list[str]) -> Area:
    router = None
    try:
        data = http.get(FEED_URL, timeout=120).content
        feed = parse_feed(data, set(modes))
        router = Router(feed)
        log.info(
            "Timetable %s: %s stops, %s connections on %s",
            feed.version,
            len(feed.stops),
            len(feed.connections),
            feed.day,
        )
    except Exception as e:  # commute falls back to the distance estimate
        log.warning("ZTM timetable unavailable, commute is estimated: %s", e)
    shops, shops_version = load_shops(store, http)
    return Area(router, shops, shops_version, http)
