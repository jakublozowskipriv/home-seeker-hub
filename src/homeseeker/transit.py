"""Door-to-door public transport times from the ZTM Poznań GTFS timetable.

For every destination and arrival time the router runs a backwards Connection Scan: the
latest moment one can leave each stop and still arrive in time. A listing's commute is
then the best of walking straight there or walking to a nearby stop. Arrival times
across the morning are checked every two minutes and averaged, so the time spent
waiting (on average half the interval between trams) is included.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import geo

log = logging.getLogger(__name__)

FEED_URL = "https://www.ztm.poznan.pl/pl/dla-deweloperow/getGTFSFile"
MODES = {0: "tram", 900: "tram", 3: "bus", 700: "bus", 704: "bus"}  # GTFS route_type
MAX_ACCESS_M = 1000  # walking to the first stop / from the last one
TRANSFER_M = 300  # walking between stops when changing
BOARD_BUFFER_S = 60  # be at the stop a minute before departure
MAX_JOURNEY_S = 90 * 60
SAMPLE_EVERY_MIN = 2
SAMPLE_SPAN_MIN = 30  # arrival times from arrive_by - 30 min to arrive_by + 30 min


@dataclass
class Stop:
    id: str
    name: str
    lat: float
    lon: float
    modes: set[str] = field(default_factory=set)


@dataclass
class Feed:
    version: str  # content hash: changes when ZTM publishes a new timetable
    day: date  # weekday the routes are computed for
    stops: list[Stop]
    # (departure s, arrival s, from stop index, to stop index, trip index), by departure
    connections: list[tuple[int, int, int, int, int]]
    trip_lines: list[str]
    trip_modes: list[str]


def _seconds(value: str) -> int:
    h, m, s = (int(x) for x in value.strip().split(":"))
    return h * 3600 + m * 60 + s


def _rows(z: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    if name not in z.namelist():
        return
    with z.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))


def _active_services(
    calendar: dict[str, tuple[str, date, date]],
    exceptions: dict[tuple[str, date], str],
    day: date,
) -> set[str]:
    active = {
        sid
        for sid, (days, start, end) in calendar.items()
        if start <= day <= end and days[day.weekday()] == "1"
    }
    for (sid, d), kind in exceptions.items():
        if d == day:
            (active.add if kind == "1" else active.discard)(sid)
    return active


def _day(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def choose_day(
    calendar: dict[str, tuple[str, date, date]],
    exceptions: dict[tuple[str, date], str],
    trips_per_service: dict[str, int],
    today: date,
) -> date:
    """A regular weekday (Tue-Thu) in the next two weeks; the busiest one avoids holidays."""
    candidates = [today + timedelta(days=k) for k in range(1, 15)]
    candidates = [d for d in candidates if d.weekday() in (1, 2, 3)]

    def trips(d: date) -> int:
        return sum(trips_per_service.get(s, 0) for s in _active_services(calendar, exceptions, d))

    return max(candidates, key=lambda d: (trips(d), -d.toordinal()))


def parse_feed(data: bytes, modes: set[str], today: date | None = None) -> Feed:
    today = today or date.today()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        routes = {}
        for r in _rows(z, "routes.txt"):
            mode = MODES.get(int(r.get("route_type") or -1))
            routes[r["route_id"]] = (r.get("route_short_name") or r["route_id"], mode)
        trips = {t["trip_id"]: (t["route_id"], t["service_id"]) for t in _rows(z, "trips.txt")}
        calendar = {
            c["service_id"]: (
                "".join(
                    c[d]
                    for d in (
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                    )
                ),
                _day(c["start_date"]),
                _day(c["end_date"]),
            )
            for c in _rows(z, "calendar.txt")
        }
        exceptions = {
            (c["service_id"], _day(c["date"])): c["exception_type"]
            for c in _rows(z, "calendar_dates.txt")
        }
        per_service: dict[str, int] = {}
        for _, sid in trips.values():
            per_service[sid] = per_service.get(sid, 0) + 1
        day = choose_day(calendar, exceptions, per_service, today)
        active = _active_services(calendar, exceptions, day)

        stops: list[Stop] = []
        stop_index: dict[str, int] = {}
        for s in _rows(z, "stops.txt"):
            if (s.get("location_type") or "0") not in ("0", ""):
                continue
            stop_index[s["stop_id"]] = len(stops)
            stops.append(
                Stop(s["stop_id"], s["stop_name"], float(s["stop_lat"]), float(s["stop_lon"]))
            )

        trip_index: dict[str, int] = {}
        trip_lines: list[str] = []
        trip_modes: list[str] = []
        timetable: dict[int, list[tuple[int, int, int, int]]] = {}
        for st in _rows(z, "stop_times.txt"):
            trip = trips.get(st["trip_id"])
            stop = stop_index.get(st["stop_id"])
            if trip is None or stop is None:
                continue
            line, mode = routes.get(trip[0], (None, None))
            if mode is None:
                continue
            stops[stop].modes.add(mode)
            if mode not in modes or trip[1] not in active:
                continue
            idx = trip_index.get(st["trip_id"])
            if idx is None:
                idx = trip_index[st["trip_id"]] = len(trip_lines)
                trip_lines.append(line)
                trip_modes.append(mode)
            arr = _seconds(st["arrival_time"] or st["departure_time"])
            dep = _seconds(st["departure_time"] or st["arrival_time"])
            timetable.setdefault(idx, []).append((int(st["stop_sequence"]), arr, dep, stop))

    connections = []
    for idx, calls in timetable.items():
        calls.sort()
        for (_, _, dep, a), (_, arr, _, b) in zip(calls, calls[1:], strict=False):
            connections.append((dep, arr, a, b, idx))
    connections.sort()
    return Feed(
        version=hashlib.sha256(data).hexdigest()[:12],
        day=day,
        stops=stops,
        connections=connections,
        trip_lines=trip_lines,
        trip_modes=trip_modes,
    )


@dataclass
class Journey:
    minutes: float
    legs: list[dict]  # {"mode": "walk", "minutes": 4} / {"mode": "tram", "line", "from", "to"}


@dataclass
class _Profile:
    arrive_at: int
    latest: list[float]  # latest time to leave each stop
    via: list[tuple | None]  # how to continue from each stop


class Router:
    def __init__(self, feed: Feed):
        self.feed = feed
        self.index = geo.GridIndex([(s.lat, s.lon) for s in feed.stops])
        self.served = {i for c in feed.connections for i in (c[2], c[3])}
        self.transfers: dict[int, list[tuple[int, float]]] = {}
        for i in self.served:
            s = feed.stops[i]
            self.transfers[i] = [
                (j, geo.walk_seconds(s.lat, s.lon, feed.stops[j].lat, feed.stops[j].lon))
                for j, _ in self.index.near(s.lat, s.lon, TRANSFER_M)
                if j != i and j in self.served
            ]
        self._backwards = sorted(feed.connections, key=lambda c: c[0], reverse=True)
        self._profiles: dict[tuple[float, float, int], _Profile] = {}

    def _walk_near(self, lat: float, lon: float) -> list[tuple[int, float]]:
        return [
            (i, geo.walk_seconds(lat, lon, self.feed.stops[i].lat, self.feed.stops[i].lon))
            for i, _ in self.index.near(lat, lon, MAX_ACCESS_M)
            if i in self.served
        ]

    def _profile(self, lat: float, lon: float, arrive_at: int) -> _Profile:
        key = (lat, lon, arrive_at)
        if key in self._profiles:
            return self._profiles[key]
        n = len(self.feed.stops)
        latest = [float("-inf")] * n
        via: list[tuple | None] = [None] * n
        for i, secs in self._walk_near(lat, lon):
            latest[i], via[i] = arrive_at - secs, ("end", secs)
        exits: dict[int, int] = {}  # trip -> stop to get off at
        for dep, arr, a, b, trip in self._backwards:
            if dep < arrive_at - MAX_JOURNEY_S:
                break
            if arr > arrive_at:
                continue
            exit_stop = exits.get(trip)
            if exit_stop is None:
                if arr > latest[b]:
                    continue
                exit_stop = exits[trip] = b
            board = dep - BOARD_BUFFER_S
            if board > latest[a]:
                latest[a], via[a] = board, ("ride", trip, exit_stop)
                for j, secs in self.transfers.get(a, ()):
                    if board - secs > latest[j]:
                        latest[j], via[j] = board - secs, ("walk", a, secs)
        profile = self._profiles[key] = _Profile(arrive_at, latest, via)
        return profile

    def _legs(self, profile: _Profile, start: int, access_s: float) -> list[dict]:
        legs: list[dict] = []

        def walk(secs: float) -> None:
            if legs and legs[-1]["mode"] == "walk":
                legs[-1]["seconds"] += secs
            else:
                legs.append({"mode": "walk", "seconds": secs})

        walk(access_s)
        stop = start
        for _ in range(30):
            step = profile.via[stop]
            if step is None:
                break
            if step[0] == "end":
                walk(step[1])
                break
            if step[0] == "walk":
                walk(step[2])
                stop = step[1]
                continue
            _, trip, exit_stop = step
            legs.append(
                {
                    "mode": self.feed.trip_modes[trip],
                    "line": self.feed.trip_lines[trip],
                    "from": self.feed.stops[stop].name,
                    "to": self.feed.stops[exit_stop].name,
                }
            )
            stop = exit_stop
        out = []
        for leg in legs:
            if leg["mode"] == "walk":
                minutes = round(leg.pop("seconds") / 60)
                if minutes < 1:
                    continue
                leg["minutes"] = minutes
            out.append(leg)
        return out

    def journey(
        self, lat: float, lon: float, dest_lat: float, dest_lon: float, arrive_by: str = "08:30"
    ) -> Journey:
        h, m = (int(x) for x in arrive_by.split(":"))
        centre = h * 3600 + m * 60
        span = SAMPLE_SPAN_MIN * 60
        times = range(centre - span, centre + span + 1, SAMPLE_EVERY_MIN * 60)
        direct = geo.walk_seconds(lat, lon, dest_lat, dest_lon)
        access = self._walk_near(lat, lon)
        results = []
        for t in times:
            profile = self._profile(dest_lat, dest_lon, t)
            best_leave, best = t - direct, None
            for i, secs in access:
                if profile.latest[i] - secs > best_leave:
                    best_leave, best = profile.latest[i] - secs, (i, secs)
            results.append((t - best_leave, profile, best))
        mean = sum(r[0] for r in results) / len(results)
        _, profile, best = min(results, key=lambda r: abs(r[0] - mean))  # a typical trip
        if best is None:
            legs = [{"mode": "walk", "minutes": round(direct / 60)}]
        else:
            legs = self._legs(profile, *best)
        return Journey(round(mean / 60, 1), legs)

    def nearest_stop(self, lat: float, lon: float, mode: str) -> tuple[str, float] | None:
        for i, metres in self.index.near(lat, lon, 1500):
            if mode in self.feed.stops[i].modes:
                return self.feed.stops[i].name, metres
        return None
