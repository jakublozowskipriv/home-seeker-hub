"""Detect the same apartment advertised several times (other portal, other agency)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import geo
from .models import Listing
from .textparse import fold

MAX_AREA_DIFF = 0.6  # m²
MAX_PRICE_DIFF = 0.03  # 3%
MAX_DISTANCE_KM = 0.4


def is_duplicate(a: Listing, b: Any) -> bool:
    """`b` is a DB row (or anything with the same attributes)."""
    if a.rooms is None or a.area is None or a.price is None:
        return False
    if b.rooms != a.rooms or b.area is None or b.price is None:
        return False
    if abs(b.area - a.area) > MAX_AREA_DIFF:
        return False
    if abs(b.price - a.price) / a.price > MAX_PRICE_DIFF:
        return False
    if a.floor is not None and b.floor is not None and a.floor != b.floor:
        return False
    precise = (
        a.has_coords
        and not a.coords_approximate
        and b.lat is not None
        and b.lon is not None
        and not b.coords_approximate
    )
    if precise:
        return geo.haversine_km(a.lat, a.lon, b.lat, b.lon) <= MAX_DISTANCE_KM
    return bool(a.district and b.district and fold(a.district) == fold(b.district))


def find_group(listing: Listing, candidates: Iterable[Any]) -> str:
    for row in candidates:
        if row.id != listing.id and is_duplicate(listing, row):
            return row.group_id or row.id
    return listing.id
