"""Morizon.pl – the same listings as Gratka.pl (one company, one database), so one source
covers both. Search results and details come from the Nuxt payload in the page."""

from __future__ import annotations

import base64
import json
import logging
import math
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlencode

from .. import textparse
from ..http import FetchError, dig
from ..models import Listing, Market
from ..preferences import Preferences
from .base import Source
from .common import parse_datetime, parse_rooms, to_float, to_int, unflatten_devalue

log = logging.getLogger(__name__)

BASE = "https://www.morizon.pl"
PAGE_SIZE = 35
_NUXT_RE = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)


def search_url(prefs: Preferences, page: int) -> str:
    params: dict[str, Any] = {"ps[price_to]": int(prefs.budget.hard_max)}
    if prefs.area.min:
        params["ps[living_area_from]"] = int(prefs.area.min)
    if prefs.area.max:
        params["ps[living_area_to]"] = int(prefs.area.max + 0.99)
    if page > 1:
        params["page"] = page
    return f"{BASE}/mieszkania/poznan/?{urlencode(params)}"


def nuxt_data(html: str) -> dict:
    m = _NUXT_RE.search(html)
    if not m:
        raise FetchError(f"No Nuxt payload in the page ({len(html)} bytes)")
    data = unflatten_devalue(json.loads(m.group(1)))
    if not isinstance(data, dict):
        raise FetchError("Unexpected Nuxt payload")
    return data


def photo_url(photo: Any) -> str | None:
    """Photo ids are the base64 of the original image URL."""
    pid = photo.get("id") if isinstance(photo, dict) else None
    if not pid:
        return None
    try:
        url = base64.b64decode(pid + "=" * (-len(pid) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return url if url.startswith("http") else None


def parse_floor_text(text: str | None) -> tuple[int | None, int | None]:
    """'piętro 1/4' -> (1, 4); 'parter/5' -> (0, 5); 'parter' -> (0, None)."""
    t = textparse.fold(text)
    if not t:
        return None, None
    total = re.search(r"/\s*(\d+)", t)
    floors_total = int(total.group(1)) if total else None
    if t.startswith("parter"):
        return 0, floors_total
    if m := re.search(r"(\d+)", t):
        return int(m.group(1)), floors_total
    return None, floors_total


def _apply_text(listing: Listing, text: str) -> None:
    listing.has_balcony = textparse.detect_balcony(text)
    listing.has_elevator = textparse.detect_elevator(text)
    listing.heating = textparse.detect_heating(text)
    listing.ownership = textparse.detect_ownership(text)
    listing.build_year = listing.build_year or textparse.detect_build_year(text)
    if listing.market == Market.PRIMARY:
        listing.completion_date = textparse.detect_completion(text)


def parse_node(node: dict) -> Listing:
    names = [x for x in dig(node, "location", "location", default=[]) or [] if x]
    street = dig(node, "location", "street")
    description = textparse.strip_html(node.get("description"))
    title = node.get("advertisementText") or node.get("title") or ""
    floor, floors_total = parse_floor_text(node.get("floorFormatted"))
    url = node.get("url") or ""
    listing = Listing(
        source="morizon",
        source_id=str(node["id"]),
        url=url if url.startswith("http") else BASE + url,
        title=title,
        price=to_float(dig(node, "price", "amount")),
        area=to_float(node.get("area")),
        rooms=parse_rooms(node.get("numberOfRooms")),
        floor=floor,
        floors_total=floors_total,
        market=Market.PRIMARY if node.get("development") else None,
        district=names[2] if len(names) > 2 else None,
        location_text=", ".join([*names[1:], *([street] if street else [])]) or None,
        description=description,
        images=[u for u in (photo_url(p) for p in node.get("photos") or []) if u][:10],
        published_at=parse_datetime(node.get("addedAt")),
        raw={"morizon_id": node.get("idOnFrontend")},
    )
    _apply_text(listing, f"{title}\n{description}")
    return listing


def _texts(items: Any) -> list[str]:
    """Labels and values of 'building information' / 'equipment' lists, whatever shape."""
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append(" ".join(str(v) for v in item.values() if isinstance(v, str | int)))
        elif isinstance(item, str):
            out.append(item)
    return out


def apply_details(listing: Listing, prop: dict) -> Listing:
    lat = to_float(dig(prop, "location", "map", "center", "latitude"))
    lon = to_float(dig(prop, "location", "map", "center", "longitude"))
    if lat and lon:
        listing.lat, listing.lon = lat, lon
    if (floor := to_int(prop.get("floor"))) is not None:
        listing.floor = floor
    _, total = parse_floor_text(prop.get("floorFormatted"))
    listing.floors_total = total or listing.floors_total
    listing.rooms = to_int(prop.get("numberOfRoomsCount")) or listing.rooms
    listing.area = to_float(prop.get("area")) or listing.area
    market = textparse.fold(prop.get("marketType"))
    if "pierwotny" in market:
        listing.market = Market.PRIMARY
    elif "wtorny" in market:
        listing.market = Market.SECONDARY
    if prop.get("description"):
        listing.description = textparse.strip_html(prop["description"])
    extra = _texts(prop.get("buildingDetailedInformation")) + _texts(prop.get("equipments"))
    if m := re.search(r"rok budowy\D{0,5}(\d{4})", textparse.fold(" ".join(extra))):
        listing.build_year = int(m.group(1))
    _apply_text(listing, "\n".join([listing.title, listing.description or "", *extra]))
    listing.details_fetched = True
    return listing


class MorizonSource(Source):
    name = "morizon"

    def search(self, prefs: Preferences, max_pages: int) -> Iterator[Listing]:
        page, pages = 1, 1
        while page <= pages:
            if page > max_pages:
                self.search_complete = False
                return
            try:
                data = nuxt_data(self.http.get(search_url(prefs, page)).text)
            except (FetchError, ValueError) as e:
                self.fail(f"page {page} failed: {e}")
                return
            props = dig(data, "pinia", "listing", "result", "searchResult", "properties") or {}
            nodes = props.get("nodes") or []
            total = props.get("totalCount") or 0
            pages = math.ceil(total / PAGE_SIZE) if total else page
            log.info("Morizon page %s/%s: %s offers (total %s)", page, pages, len(nodes), total)
            for node in nodes:
                try:
                    yield parse_node(node)
                except (KeyError, TypeError, ValueError) as e:
                    log.warning("Morizon: skipping malformed offer %s: %s", node.get("id"), e)
            if not nodes:
                return
            page += 1

    def fetch_details(self, listing: Listing) -> Listing:
        try:
            data = nuxt_data(self.http.get(listing.url).text)
        except ValueError as e:
            raise FetchError(str(e)) from e
        prop = dig(data, "pinia", "details", "propertyData")
        if not isinstance(prop, dict):
            raise FetchError(f"No property data on {listing.url}")
        return apply_details(listing, prop)
