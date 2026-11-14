"""Domiporta.pl – result cards from the search page's HTML, details from the JSON-LD of
the listing page."""

from __future__ import annotations

import html as htmllib
import json
import logging
import re
from collections.abc import Iterator

from .. import textparse
from ..http import FetchError, dig
from ..models import Listing
from ..preferences import Preferences
from .base import Source
from .common import parse_datetime, to_float, to_int

log = logging.getLogger(__name__)

BASE = "https://www.domiporta.pl"
SEARCH = f"{BASE}/mieszkanie/sprzedam/wielkopolskie/poznan"
_CARD_START_RE = re.compile(r"<article\b[^>]*>")
MAX_CARD = 20_000  # the last card on a page ends nowhere in particular


def cards(page: str) -> list[tuple[str, str]]:
    """(detail id, card html) of the result cards. A card runs from its opening tag to the
    next card: Domiporta does not always close them, so </article> cannot be relied on."""
    starts = []
    for m in _CARD_START_RE.finditer(page):
        detail = re.search(r'data-detail-id="(\d+)"', m.group(0))
        if detail and "sneakpeak" in m.group(0):
            starts.append((m.start(), m.end(), detail.group(1)))
    out = []
    for k, (_, body_start, detail_id) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(page)
        body = page[body_start : min(end, body_start + MAX_CARD)]
        out.append((detail_id, body.split("</article>")[0]))
    return out


_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def _text(fragment: str | None) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def parse_card(detail_id: str, card: str) -> Listing | None:
    href = re.search(r'href="(/nieruchomosci/[^"]+)"', card)
    if not href:
        return None  # developer projects ("/nowe/...") list many flats, not one
    title_attr = re.search(r'<a title="([^"]+)"', card)
    title = htmllib.unescape(title_attr.group(1)) if title_attr else ""
    price = re.search(r'sneakpeak__price_value">(.*?)</span>', card, re.S)
    area = re.search(r'details_item--area"[^>]*>(.*?)<abbr', card, re.S)
    rooms = re.search(r'details_item--room"[^>]*>(.*?)</span>', card, re.S)
    image = re.search(r'<img[^>]+src="(https://galeria[^"]+)"', card)
    place = re.search(r"(Pozna[nń].*)$", title)
    location = place.group(1) if place else None
    parts = [p.strip() for p in (location or "").split(",")]
    listing = Listing(
        source="domiporta",
        source_id=detail_id,
        url=BASE + href.group(1),
        title=title,
        price=to_float(_text(price.group(1))) if price else None,
        area=to_float(_text(area.group(1))) if area else None,
        rooms=to_int(_text(rooms.group(1))) if rooms else None,
        district=parts[1] if len(parts) > 1 else None,
        location_text=location,
        images=[image.group(1).replace("/small/", "/big/")] if image else [],
    )
    return listing


def _ld_listing(page: str) -> dict | None:
    for block in _LD_RE.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and (
                dig(item, "offers", "price") or dig(item, "itemOffered", "geo")
            ):
                return item
    return None


def apply_details(listing: Listing, item: dict) -> Listing:
    offered = item.get("itemOffered") or {}
    listing.price = to_float(dig(item, "offers", "price")) or listing.price
    if (floor := to_int(offered.get("floorLevel"))) is not None:
        listing.floor = floor
    listing.build_year = to_int(offered.get("yearBuilt")) or listing.build_year
    listing.rooms = to_int(offered.get("numberOfRooms")) or listing.rooms
    listing.area = to_float(dig(offered, "floorSize", "value")) or listing.area
    lat, lon = to_float(dig(offered, "geo", "latitude")), to_float(dig(offered, "geo", "longitude"))
    if lat and lon:
        listing.lat, listing.lon = lat, lon
    street = dig(item, "address", "streetAddress")
    if street and listing.location_text and street not in listing.location_text:
        listing.location_text = f"{listing.location_text}, {street}"
    listing.description = textparse.strip_html(item.get("description")) or listing.description
    images = item.get("image")
    if isinstance(images, list) and images:
        listing.images = [i for i in images if isinstance(i, str)][:10]
    listing.published_at = parse_datetime(item.get("datePosted")) or listing.published_at
    amenities = " ".join(
        str(a.get("name", "")) if isinstance(a, dict) else str(a)
        for a in offered.get("amenityFeature") or []
    )
    text = f"{listing.title}\n{listing.description or ''}\n{amenities}"
    listing.has_balcony = textparse.detect_balcony(text)
    listing.has_elevator = textparse.detect_elevator(text)
    listing.heating = textparse.detect_heating(text)
    listing.ownership = textparse.detect_ownership(text)
    if listing.floor is None:
        listing.floor, listing.floors_total = textparse.detect_floor(text)
    listing.details_fetched = True
    return listing


class DomiportaSource(Source):
    name = "domiporta"

    def search(self, prefs: Preferences, max_pages: int) -> Iterator[Listing]:
        page, pages = 1, 1
        while page <= pages:
            if page > max_pages:
                self.search_complete = False
                return
            url = SEARCH if page == 1 else f"{SEARCH}?PageNumber={page}"
            try:
                page_html = self.http.get(url).text
            except FetchError as e:
                self.fail(f"page {page} failed: {e}")
                return
            numbers = [int(n) for n in re.findall(r"PageNumber=(\d+)", page_html)]
            pages = max([pages, *numbers])
            found = cards(page_html)
            log.info("Domiporta page %s/%s: %s cards", page, pages, len(found))
            if not found:
                title = re.search(r"<title>(.*?)</title>", page_html, re.S)
                if page < pages:
                    self.fail(
                        f"page {page} has no result cards ({len(page_html)} bytes, title "
                        f"{(title.group(1).strip() if title else '?')[:80]!r})"
                    )
                return
            for detail_id, card in found:
                try:
                    if listing := parse_card(detail_id, card):
                        yield listing
                except (TypeError, ValueError) as e:
                    log.warning("Domiporta: skipping malformed card %s: %s", detail_id, e)
            page += 1

    def fetch_details(self, listing: Listing) -> Listing:
        item = _ld_listing(self.http.get(listing.url).text)
        if item is None:
            raise FetchError(f"No listing data on {listing.url}")
        return apply_details(listing, item)
