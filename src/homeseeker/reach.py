"""Commute reach map: door-to-door minutes from a ~300 m grid over Poznań to each
destination, for the web app's map layer. Recomputed only when the timetable or the
commute preferences change."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING

from .db import Store

if TYPE_CHECKING:
    from .area import Area
    from .preferences import Preferences

log = logging.getLogger(__name__)

BBOX = (52.33, 16.80, 52.48, 17.08)  # south, west, north, east: the city and a margin
STEP = (0.0027, 0.0044)  # degrees: about 300 m × 300 m
KEEP_FACTOR = 1.5  # cells slower than this × the limit are left out (nothing to draw)


def _fingerprint(area: Area, prefs: Preferences) -> str:
    payload = json.dumps(
        [
            area.router.feed.version if area.router else None,
            [d.model_dump() for d in prefs.destinations],
            prefs.commute.model_dump(),
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def compute(area: Area, prefs: Preferences) -> dict:
    limit = prefs.commute.max_minutes
    c = prefs.commute
    south, west, north, east = BBOX
    points = []
    lat = south
    while lat <= north:
        lon = west
        while lon <= east:
            minutes = []
            for dest in prefs.destinations:
                journey = area.journey(
                    lat, lon, dest.lat, dest.lon, c.arrive_by, c.bus_penalty_minutes
                )
                minutes.append(round(journey.minutes) if journey else None)
            if all(m is not None and m <= limit * KEEP_FACTOR for m in minutes):
                points.append([round(lat, 5), round(lon, 5), *minutes])
            lon += STEP[1]
        lat += STEP[0]
    return {
        "cell": list(STEP),
        "limit": limit,
        "destinations": [d.name for d in prefs.destinations],
        "points": points,
    }


def update_reach_map(store: Store, area: Area | None, prefs: Preferences) -> bool:
    """Recompute and store the map when needed; True when it was (re)computed."""
    if area is None or area.router is None or not prefs.destinations:
        return False
    fingerprint = _fingerprint(area, prefs)
    current = store.get_setting("reach_map") or {}
    if current.get("fingerprint") == fingerprint:
        return False
    started = time.monotonic()
    data = compute(area, prefs)
    data["fingerprint"] = fingerprint
    store.set_setting("reach_map", data)
    log.info("Reach map: %s cells in %.0fs", len(data["points"]), time.monotonic() - started)
    return True
