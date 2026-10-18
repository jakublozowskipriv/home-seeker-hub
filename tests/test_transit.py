import io
import zipfile
from datetime import date

import pytest

from homeseeker.area import Area, parse_parcel, parse_shops
from homeseeker.evaluate import evaluate
from homeseeker.transit import Router, parse_feed

DEST = (52.4085, 16.9342)  # Stary Rynek
STOPS = {
    "A": ("Dębiec", 52.3890, 16.9342),
    "B": ("Wilda", 52.3980, 16.9342),
    "B2": ("Wilda", 52.3982, 16.9344),  # other platform of the same stop
    "C": ("Rynek", 52.4070, 16.9342),
    "D": ("Łazarz", 52.3980, 16.9000),
    "X": ("Pętla autobusowa", 52.3881, 16.9343),
}


def _hms(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:00"


def build_feed(holiday: str | None = None) -> bytes:
    trips, stop_times = [], []

    def line(route: str, calls: list[tuple[str, int]], offset: int) -> None:
        for k in range(24):  # every 10 minutes from 6:00
            trip = f"{route}_{k}"
            trips.append(f"{route},weekday,{trip}")
            start = 6 * 3600 + offset * 60 + k * 600
            for seq, (stop, minute) in enumerate(calls):
                t = _hms(start + minute * 60)
                stop_times.append(f"{trip},{t},{t},{stop},{seq}")

    line("2", [("A", 0), ("B", 4), ("C", 8)], 0)
    line("5", [("D", 0), ("B2", 6)], 3)
    line("170", [("X", 0), ("C", 5)], 1)  # a bus: faster, but not taken by tram fans
    files = {
        "routes.txt": "route_id,route_short_name,route_type\n2,2,0\n5,5,0\n170,170,3\n",
        "trips.txt": "route_id,service_id,trip_id\n" + "\n".join(trips) + "\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\nweekday,1,1,1,1,1,0,0,20260101,20271231\n",
        "calendar_dates.txt": "service_id,date,exception_type\n"
        + (f"weekday,{holiday},2\n" if holiday else ""),
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n"
        + "".join(f"{k},{n},{lat},{lon}\n" for k, (n, lat, lon) in STOPS.items()),
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        + "\n".join(stop_times)
        + "\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


@pytest.fixture(scope="module")
def router():
    return Router(parse_feed(build_feed(), {"tram"}, today=date(2026, 10, 18)))


def test_weekday_is_chosen_and_holidays_avoided():
    assert parse_feed(build_feed(), {"tram"}, today=date(2026, 10, 18)).day == date(2026, 10, 20)
    feed = parse_feed(build_feed(holiday="20261020"), {"tram"}, today=date(2026, 10, 18))
    assert feed.day == date(2026, 10, 21)


def test_direct_tram_ride(router):
    j = router.journey(52.3880, 16.9342, *DEST)  # next to stop A
    assert [leg["mode"] for leg in j.legs] == ["walk", "tram", "walk"]
    assert j.legs[1] == {"mode": "tram", "line": "2", "from": "Dębiec", "to": "Rynek"}
    # walk ~2 + buffer 1 + ride 8 + walk ~3 + on average half a 10-minute headway
    assert 16 <= j.minutes <= 20


def test_change_between_platforms(router):
    j = router.journey(52.3980, 16.8990, *DEST)  # next to stop D
    rides = [leg for leg in j.legs if leg["mode"] == "tram"]
    assert [r["line"] for r in rides] == ["5", "2"]
    assert rides[0]["to"] == "Wilda" and rides[1]["from"] == "Wilda"


def test_walking_wins_when_close(router):
    j = router.journey(52.4080, 16.9330, *DEST)
    assert j.legs == [{"mode": "walk", "minutes": j.legs[0]["minutes"]}]
    assert j.minutes < 3


def test_bus_ignored_unless_enabled(router):
    # stop X is next to A: only the tram counts, the bus stop is still reported nearby
    assert router.journey(52.3881, 16.9343, *DEST).legs[1]["line"] == "2"
    assert router.nearest_stop(52.3881, 16.9343, "bus")[0] == "Pętla autobusowa"


def test_tram_preferred_unless_bus_is_clearly_faster():
    with_bus = Router(parse_feed(build_feed(), {"tram", "bus"}, today=date(2026, 10, 18)))

    def lines(journey):
        return [leg["line"] for leg in journey.legs if leg["mode"] != "walk"]

    fastest = with_bus.journey(52.3881, 16.9343, *DEST)
    tram = with_bus.journey(52.3881, 16.9343, *DEST, modes=frozenset({"tram"}))
    assert lines(fastest) == ["170"] and lines(tram) == ["2"]
    saving = tram.minutes - fastest.minutes
    assert 0 < saving < 5
    assert lines(with_bus.best_journey(52.3881, 16.9343, *DEST, bus_penalty_min=5)) == ["2"]
    assert lines(with_bus.best_journey(52.3881, 16.9343, *DEST, bus_penalty_min=0)) == ["170"]


def test_evaluation_uses_timetable(router, prefs, good_listing):
    shops = [[52.4097, 16.9110, "supermarket", "Biedronka"], [52.4096, 16.9104, "bakery", ""]]
    area = Area(router, shops, "2026-10-18")
    good_listing.description = "Księga wieczysta: PO1P/00123456/7, bez obciążeń."
    ev = evaluate(good_listing, prefs, area)
    assert ev.commute_method == "timetable"
    assert set(ev.commute_routes) == {d.name for d in prefs.destinations}
    assert ev.nearby["supermarket"] == {"name": "Biedronka", "m": 41}
    assert ev.nearby["shops_500m"] == 2
    assert ev.land_register == "PO1P/00123456/7"
    estimated = evaluate(good_listing, prefs)
    assert estimated.commute_method == "estimate" and estimated.commute_routes == {}


def test_bus_route_scores_lower(prefs, good_listing):
    with_bus = Router(parse_feed(build_feed(), {"tram", "bus"}, today=date(2026, 10, 18)))
    area = Area(with_bus)
    good_listing.lat, good_listing.lon = 52.3881, 16.9343
    prefs.commute.bus_penalty_minutes = 0
    by_bus = evaluate(good_listing, prefs, area)
    assert any(leg["mode"] == "bus" for leg in by_bus.commute_routes["Stary Rynek"])
    prefs.commute.bus_penalty_minutes = 3  # still the bus (it saves ~4 min), but scored lower
    penalised = evaluate(good_listing, prefs, area)
    assert penalised.commute_routes == by_bus.commute_routes
    assert penalised.commute == by_bus.commute  # the hard limit uses the real time
    assert penalised.score < by_bus.score


def test_parse_parcel_and_shops():
    assert parse_parcel("0\n306401_1.0021.AR_12.45/3|Jeżyce|45/3\n") == {
        "id": "306401_1.0021.AR_12.45/3",
        "region": "Jeżyce",
        "number": "45/3",
    }
    assert parse_parcel("-1 brak wyników\n") is None
    data = {
        "elements": [
            {
                "type": "node",
                "lat": 52.4,
                "lon": 16.9,
                "tags": {"shop": "convenience", "name": "Żabka"},
            },
            {
                "type": "way",
                "center": {"lat": 52.41, "lon": 16.91},
                "tags": {"shop": "supermarket", "brand": "Lidl", "name": "Lidl Jeżyce"},
            },
        ]
    }
    assert parse_shops(data) == [
        [52.4, 16.9, "convenience", "Żabka"],
        [52.41, 16.91, "supermarket", "Lidl"],
    ]


def test_message_shows_lines_and_shops(router, prefs, good_listing):
    from homeseeker.notify.format import listing_html

    shops = [[52.4097, 16.9110, "supermarket", "Biedronka"]]
    good_listing.lat, good_listing.lon = 52.3880, 16.9342
    html = listing_html(good_listing, evaluate(good_listing, prefs, Area(router, shops, "x")))
    assert "min Stary Rynek (linia 2)" in html
    assert "🚏 Dębiec" in html and "szacunek" not in html
    assert "szacunek" in listing_html(good_listing, evaluate(good_listing, prefs))
