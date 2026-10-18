"""Geographic helpers and a rough tram + walk commute estimate.

The estimate is a placeholder until real GTFS routing (ZTM Poznań) is added: it uses
straight-line distance with a detour factor and average door-to-door tram speed.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0

ROUTE_FACTOR = 1.25  # street network vs straight line
WALK_KMH = 5.0
TRAM_KMH = 18.0  # average in-vehicle speed incl. stops
TRAM_OVERHEAD_MIN = 9.0  # walk to stop + wait + walk from stop


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_commute_minutes(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Best of walking and tram, in minutes."""
    km = haversine_km(lat1, lon1, lat2, lon2) * ROUTE_FACTOR
    walk = km / WALK_KMH * 60
    tram = TRAM_OVERHEAD_MIN + km / TRAM_KMH * 60
    return round(min(walk, tram), 1)


def google_maps_url(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"


def apple_maps_url(lat: float, lon: float) -> str:
    return f"https://maps.apple.com/?ll={lat:.6f},{lon:.6f}&q=Mieszkanie"
