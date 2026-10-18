"""OLX.pl - uses the JSON API that powers the OLX website."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from urllib.parse import urlparse

from .. import textparse
from ..http import FetchError, dig
from ..models import Listing, Market
from ..preferences import Preferences
from .base import Source
from .common import parse_datetime, parse_floor, parse_rooms, to_float

log = logging.getLogger(__name__)

API = "https://www.olx.pl/api/v1"
FRIENDLY_PATH = "nieruchomosci,mieszkania,sprzedaz,poznan"
PAGE_SIZE = 50
MAX_OFFSET = 1000  # the API refuses deeper pagination
ROOM_KEYS = ["one", "two", "three", "four"]
# Above this radius (km) OLX coordinates are only a rough area, not the address.
APPROX_RADIUS_KM = 0.5


def _params(offer: dict) -> dict[str, dict]:
    return {p["key"]: p for p in offer.get("params") or [] if isinstance(p, dict) and "key" in p}


def _param_key(params: dict[str, dict], key: str):
    value = dig(params, key, "value")
    if isinstance(value, dict):
        return value.get("key") if value.get("key") is not None else value.get("value")
    return value


def parse_offer(offer: dict) -> Listing | None:
    url = offer.get("url") or ""
    host = urlparse(url).netloc
    if not host.endswith("olx.pl") or offer.get("partner"):
        return None  # cross-posted from Otodom, covered by that source
    params = _params(offer)
    description = textparse.strip_html(offer.get("description"))
    loc = offer.get("location") or {}
    district = dig(loc, "district", "name")
    loc_text = ", ".join(x for x in (dig(loc, "city", "name"), district) if x) or None
    full_text = f"{offer.get('title', '')}\n{description}"

    price = to_float(dig(params, "price", "value", "value"))
    area = to_float(_param_key(params, "m"))
    rooms = parse_rooms(_param_key(params, "rooms"))
    floor = parse_floor(_param_key(params, "floor_select"))
    floors_total = None
    if floor is None:
        floor, floors_total = textparse.detect_floor(full_text)

    market = str(_param_key(params, "market") or "").lower()
    lat, lon = to_float(dig(offer, "map", "lat")), to_float(dig(offer, "map", "lon"))
    radius = to_float(dig(offer, "map", "radius")) or 0
    approx = not dig(offer, "map", "show_detailed", default=False) and radius > APPROX_RADIUS_KM

    photos = []
    for p in offer.get("photos") or []:
        link = p.get("link") if isinstance(p, dict) else None
        if link:
            photos.append(link.replace("{width}", "800").replace("{height}", "600"))

    listing = Listing(
        source="olx",
        source_id=str(offer["id"]),
        url=url,
        title=offer.get("title") or "",
        price=price,
        area=area,
        rooms=rooms,
        floor=floor,
        floors_total=floors_total,
        build_year=textparse.detect_build_year(full_text),
        market=Market(market) if market in ("primary", "secondary") else None,
        has_balcony=textparse.detect_balcony(full_text),
        has_elevator=textparse.detect_elevator(full_text),
        heating=textparse.detect_heating(full_text),
        ownership=textparse.detect_ownership(full_text),
        district=district,
        location_text=loc_text,
        lat=lat,
        lon=lon,
        coords_approximate=approx,
        description=description,
        images=photos[:10],
        is_private_owner=not offer.get("business", False),
        agency=dig(offer, "user", "name") if offer.get("business") else None,
        published_at=parse_datetime(offer.get("created_time")),
        details_fetched=True,
        raw={"params": {k: _param_key(params, k) for k in params}},
    )
    if listing.market == Market.PRIMARY:
        listing.completion_date = textparse.detect_completion(full_text)
    return listing


class OlxSource(Source):
    name = "olx"
    complete_search_results = True

    def _location_ids(self) -> dict:
        data = self.http.get_json(f"{API}/friendly-links/query-params/{FRIENDLY_PATH}")
        ids = data.get("data") if isinstance(data, dict) else None
        if not isinstance(ids, dict) or "category_id" not in ids:
            raise FetchError(f"Unexpected friendly-links response: {str(data)[:300]}")
        return {k: ids[k] for k in ("category_id", "region_id", "city_id") if ids.get(k)}

    def search(self, prefs: Preferences, max_pages: int) -> Iterator[Listing]:
        try:
            ids = self._location_ids()
        except (FetchError, ValueError) as e:
            self.fail(f"cannot resolve Poznań category/location ids: {e}")
            return
        log.info("OLX ids: %s", ids)
        params: dict[str, str | int] = {
            **ids,
            "limit": PAGE_SIZE,
            "sort_by": "created_at:desc",
            "filter_float_price:to": int(prefs.budget.hard_max),
        }
        if prefs.area.min:
            params["filter_float_m:from"] = int(prefs.area.min)
        if prefs.area.max:
            params["filter_float_m:to"] = int(prefs.area.max + 0.99)
        lo, hi = int(prefs.rooms.min or 1), int(prefs.rooms.max or 4)
        for i, key in enumerate(ROOM_KEYS[lo - 1 : hi]):
            params[f"filter_enum_rooms[{i}]"] = key

        offset, pages = 0, 0
        while offset < MAX_OFFSET and pages < max_pages:
            try:
                data = self.http.get_json(f"{API}/offers/", params={**params, "offset": offset})
            except (FetchError, ValueError) as e:
                self.fail(f"offers offset {offset} failed: {e}")
                return
            offers = data.get("data") or []
            total = dig(data, "metadata", "total_elements")
            log.info("OLX offset %s: %s offers (total %s)", offset, len(offers), total)
            for offer in offers:
                try:
                    if listing := parse_offer(offer):
                        yield listing
                except (KeyError, TypeError, ValueError) as e:
                    log.warning("OLX: skipping malformed offer %s: %s", offer.get("id"), e)
            pages += 1
            if not offers or not dig(data, "links", "next", "href"):
                return
            offset += PAGE_SIZE
        self.search_complete = False
