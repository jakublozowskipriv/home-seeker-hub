"""Geographic helpers and a rough tram + walk commute estimate.

The estimate is the fallback when the ZTM timetable (see transit.py) is unavailable: it
uses straight-line distance with a detour factor and average door-to-door tram speed.
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


def walk_seconds(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * ROUTE_FACTOR / WALK_KMH * 3600


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


class GridIndex:
    """Points bucketed in ~1 km cells, for "what is within N metres" lookups."""

    CELL = 0.01  # degrees (about 1.1 km north-south, 0.7 km east-west in Poznań)

    def __init__(self, points: list[tuple[float, float]]):
        self.points = points
        self.cells: dict[tuple[int, int], list[int]] = {}
        for i, (lat, lon) in enumerate(points):
            self.cells.setdefault(self._cell(lat, lon), []).append(i)

    def _cell(self, lat: float, lon: float) -> tuple[int, int]:
        return int(math.floor(lat / self.CELL)), int(math.floor(lon / self.CELL))

    def near(self, lat: float, lon: float, radius_m: float) -> list[tuple[int, float]]:
        """(point index, distance in metres) of points within the radius, nearest first."""
        reach_lat = int(radius_m / 111_000 / self.CELL) + 1
        reach_lon = int(radius_m / (111_000 * math.cos(math.radians(lat))) / self.CELL) + 1
        cy, cx = self._cell(lat, lon)
        out = []
        for y in range(cy - reach_lat, cy + reach_lat + 1):
            for x in range(cx - reach_lon, cx + reach_lon + 1):
                for i in self.cells.get((y, x), ()):
                    plat, plon = self.points[i]
                    d = haversine_km(lat, lon, plat, plon) * 1000
                    if d <= radius_m:
                        out.append((i, d))
        return sorted(out, key=lambda t: t[1])


def to_puwg1992(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 -> EPSG:2180 (PUWG 1992), the Polish cadastre's system: (easting, northing).

    Transverse Mercator on GRS80 (ETRS89 and WGS84 differ by centimetres).
    """
    a, f = 6378137.0, 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0, lon0, fe, fn = 0.9993, math.radians(19.0), 500000.0, -5300000.0
    phi, lam = math.radians(lat), math.radians(lon)
    n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    t = math.tan(phi) ** 2
    c = ep2 * math.cos(phi) ** 2
    aa = (lam - lon0) * math.cos(phi)
    e4, e6 = e2 * e2, e2 * e2 * e2
    m = a * (
        (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
        - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
        + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
        - (35 * e6 / 3072) * math.sin(6 * phi)
    )
    x = (
        k0
        * n
        * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * ep2) * aa**5 / 120)
    )
    y = k0 * (
        m
        + n
        * math.tan(phi)
        * (
            aa * aa / 2
            + (5 - t + 9 * c + 4 * c * c) * aa**4 / 24
            + (61 - 58 * t + t * t + 600 * c - 330 * ep2) * aa**6 / 720
        )
    )
    return x + fe, y + fn
