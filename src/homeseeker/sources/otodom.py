"""Otodom.pl - data comes from the Next.js __NEXT_DATA__ JSON embedded in pages."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from urllib.parse import urlencode

from .. import textparse
from ..http import FetchError, dig
from ..models import Listing, Market, Ownership
from ..preferences import Preferences
from .base import Source
from .common import parse_datetime, parse_floor, parse_heating, parse_rooms, to_float, to_int

log = logging.getLogger(__name__)

BASE = "https://www.otodom.pl"
SEARCH_PATH = "/pl/wyniki/sprzedaz/mieszkanie/wielkopolskie/poznan/poznan/poznan"
ROOM_ENUMS = ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX"]
BALCONY_TOKENS = {"balcony", "terrace", "loggia", "balkon", "taras"}
ELEVATOR_TOKENS = {"lift", "winda", "elevator"}


def search_url(prefs: Preferences, page: int) -> str:
    params: dict[str, str | int] = {
        "limit": 72,
        "by": "LATEST",
        "direction": "DESC",
        "viewType": "listing",
        "page": page,
        "priceMax": int(prefs.budget.hard_max),
    }
    if prefs.area.min:
        params["areaMin"] = int(prefs.area.min)
    if prefs.area.max:
        params["areaMax"] = int(prefs.area.max + 0.99)
    lo, hi = int(prefs.rooms.min or 1), int(prefs.rooms.max or 6)
    params["roomsNumber"] = "[" + ",".join(ROOM_ENUMS[lo - 1 : hi]) + "]"
    return f"{BASE}{SEARCH_PATH}?{urlencode(params)}"


def _location_text(location: dict | None) -> tuple[str | None, str | None]:
    """(district, full location text) from an Otodom location object."""
    if not location:
        return None, None
    parts: list[str] = []
    district = None
    for loc in dig(location, "reverseGeocoding", "locations", default=[]) or []:
        name = loc.get("name") or loc.get("fullName")
        if name and name not in parts:
            parts.append(name)
        if loc.get("locationLevel") in ("district", "residential") and name:
            district = name if district is None else district
    addr = location.get("address") or {}
    for key in ("district", "subdistrict"):
        if name := dig(addr, key, "name"):
            parts.append(name)
            district = district or name
    street = dig(addr, "street", "name")
    if street:
        parts.append(street)
    return district, ", ".join(parts) or None


def _images(items) -> list[str]:
    out = []
    for img in items or []:
        if isinstance(img, dict):
            url = img.get("large") or img.get("medium") or img.get("small")
            if url:
                out.append(url)
    return out


def parse_search_item(item: dict) -> Listing | None:
    if item.get("estate") not in (None, "FLAT"):
        return None  # investments are aggregates; their flats are listed separately
    slug = item.get("slug")
    if not slug or not item.get("id"):
        return None
    district, loc_text = _location_text(item.get("location"))
    listing = Listing(
        source="otodom",
        source_id=str(item["id"]),
        url=f"{BASE}/pl/oferta/{slug}",
        title=item.get("title") or "",
        price=to_float(dig(item, "totalPrice", "value")),
        area=to_float(item.get("areaInSquareMeters")),
        rooms=parse_rooms(item.get("roomsNumber")),
        floor=parse_floor(item.get("floorNumber")),
        district=district,
        location_text=loc_text,
        images=_images(item.get("images"))[:5],
        is_private_owner=item.get("isPrivateOwner"),
        agency=dig(item, "agency", "name"),
        published_at=parse_datetime(item.get("dateCreatedFirst") or item.get("dateCreated")),
        description=item.get("shortDescription"),
    )
    if item.get("openDays"):
        listing.raw["open_days"] = item["openDays"]
    return listing


def _tokens(ad: dict) -> tuple[set[str], dict[str, list[str]]]:
    """Collect structured values: {key: [values]} from target/characteristics/info blocks."""
    values: dict[str, list[str]] = {}

    def add(key: str, val) -> None:
        if val is None or val == "":
            return
        vals = val if isinstance(val, list) else [val]
        values.setdefault(key.lower(), []).extend(str(v) for v in vals if v not in (None, ""))

    for key, val in (ad.get("target") or {}).items():
        add(key, val)
    for ch in ad.get("characteristics") or []:
        if isinstance(ch, dict) and ch.get("key"):
            add(ch["key"], ch.get("value"))
    for block in ("additionalInformation", "topInformation"):
        for info in ad.get(block) or []:
            if isinstance(info, dict) and info.get("label"):
                add(info["label"], info.get("values"))
    tokens = {v.lower() for vals in values.values() for v in vals}
    return tokens, values


def _first(values: dict[str, list[str]], *keys: str):
    for k in keys:
        if values.get(k):
            return values[k][0]
    return None


def apply_details(listing: Listing, ad: dict) -> Listing:
    tokens, values = _tokens(ad)
    description = textparse.strip_html(ad.get("description"))
    listing.description = description or listing.description
    listing.title = ad.get("title") or listing.title
    listing.price = to_float(_first(values, "price")) or listing.price
    listing.area = to_float(_first(values, "area", "m")) or listing.area
    listing.rooms = parse_rooms(_first(values, "rooms_num")) or listing.rooms
    floor = parse_floor(_first(values, "floor_no"))
    listing.floor = floor if floor is not None else listing.floor
    listing.floors_total = to_int(_first(values, "building_floors_num"))
    listing.build_year = to_int(_first(values, "build_year"))

    market = (_first(values, "markettype", "market") or ad.get("market") or "").lower()
    if market in ("primary", "secondary"):
        listing.market = Market(market)

    extras_known = any(k in values for k in ("extras_types", "outdoor"))
    if tokens & BALCONY_TOKENS:
        listing.has_balcony = True
    else:
        from_text = textparse.detect_balcony(description)
        listing.has_balcony = (
            from_text if from_text is not None else (False if extras_known else None)
        )
    if tokens & ELEVATOR_TOKENS:
        listing.has_elevator = True
    else:
        listing.has_elevator = textparse.detect_elevator(description)

    listing.heating = parse_heating(_first(values, "heating")) or textparse.detect_heating(
        description
    )
    ownership = (_first(values, "building_ownership") or "").lower()
    if "full" in ownership:
        listing.ownership = Ownership.FULL
    elif "cooperative" in ownership or "limited" in ownership:
        listing.ownership = Ownership.COOPERATIVE
    else:
        listing.ownership = textparse.detect_ownership(description)

    if listing.market == Market.PRIMARY:
        listing.completion_date = textparse.detect_completion(description)

    location = ad.get("location") or {}
    lat = to_float(dig(location, "coordinates", "latitude"))
    lon = to_float(dig(location, "coordinates", "longitude"))
    if lat and lon:
        listing.lat, listing.lon = lat, lon
        listing.coords_approximate = bool(dig(location, "mapDetails", "radius", default=0))
    district, loc_text = _location_text(location)
    listing.district = district or listing.district
    listing.location_text = loc_text or listing.location_text
    listing.images = _images(ad.get("images"))[:10] or listing.images
    listing.agency = dig(ad, "agency", "name") or dig(ad, "owner", "name") or listing.agency
    listing.raw = {**listing.raw, "structured": {k: v[:5] for k, v in values.items()}}
    listing.details_fetched = True

    # Fill gaps from the description.
    if listing.floor is None:
        listing.floor, listing.floors_total = textparse.detect_floor(description)
    if listing.build_year is None:
        listing.build_year = textparse.detect_build_year(description)
    return listing


class OtodomSource(Source):
    name = "otodom"

    def search(self, prefs: Preferences, max_pages: int) -> Iterator[Listing]:
        page, total_pages = 1, 1
        while page <= min(total_pages, max_pages):
            url = search_url(prefs, page)
            try:
                data = self.http.get_next_data(url)
            except FetchError as e:
                self.fail(f"search page {page} failed: {e}")
                return
            search_ads = dig(data, "props", "pageProps", "data", "searchAds")
            if search_ads is None:
                keys = list((dig(data, "props", "pageProps") or {}).keys())
                self.fail(f"unexpected page structure, pageProps keys: {keys}")
                return
            total_pages = to_int(dig(search_ads, "pagination", "totalPages")) or 1
            items = search_ads.get("items") or []
            log.info("Otodom page %s/%s: %s items", page, total_pages, len(items))
            for item in items:
                if listing := parse_search_item(item):
                    yield listing
            page += 1
        if total_pages > max_pages:
            self.search_complete = False

    def fetch_details(self, listing: Listing) -> Listing:
        data = self.http.get_next_data(listing.url)
        ad = dig(data, "props", "pageProps", "ad")
        if not ad:
            raise FetchError(f"No ad object in {listing.url}")
        return apply_details(listing, ad)
