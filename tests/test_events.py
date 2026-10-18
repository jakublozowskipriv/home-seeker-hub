import copy
from datetime import datetime, timedelta

from homeseeker.db import Store, init_db, make_engine
from homeseeker.events import WARSAW, open_day_event, parse_fairs
from homeseeker.pipeline import run
from tests.test_pipeline import FakeSource, FakeTelegram

# Shape of the calendar data embedded on targimieszkan.pl (seen live, 2026-10).
FAIRS_PAGE = """
<script>
var calendarOptions = calendarOptions || []
var data = { title: 'Targi Mieszka&#324; i Dom&#243;w Pozna&#324;',
  start: new Date('2026-09-12 00:00:00'), duration: 1000,
  end: new Date('2026-09-13 23:59:59'), address: 'MTP, ul. Głogowska 14', description: '' }
var other = { title: 'Targi Mieszkań i Domów Kraków', start: new Date('2026-09-19 00:00:00'),
  end: new Date('2026-09-20 23:59:59'), address: '' }
</script>
"""


def test_parse_fairs_one_event_per_day_in_poznan_only():
    fairs = parse_fairs(FAIRS_PAGE)
    assert [f["starts_at"].date().isoformat() for f in fairs] == ["2026-09-12", "2026-09-13"]
    sat, sun = fairs
    assert sat["title"] == "Targi Mieszkań i Domów Poznań"
    assert (sat["starts_at"].hour, sat["ends_at"].hour) == (10, 17)
    assert sun["ends_at"].hour == 16  # Sunday closes earlier
    assert sat["location"] == "MTP, ul. Głogowska 14"
    assert sat["starts_at"].tzinfo == WARSAW


def test_open_day_event_uses_listing_page_times(good_listing):
    event = open_day_event(
        good_listing, "2026-10-24", {"date": "2026-10-24", "timeFrom": "11:00", "timeTo": "14:00"}
    )
    assert event["starts_at"] == datetime(2026, 10, 24, 11, 0, tzinfo=WARSAW)
    assert event["ends_at"] == datetime(2026, 10, 24, 14, 0, tzinfo=WARSAW)
    assert event["external_id"] == "test-openday:1:2026-10-24"
    assert event["notes"] is None
    assert open_day_event(good_listing, "2026-10-24", None)["notes"]


class OpenDaySource(FakeSource):
    def __init__(self, listings):
        super().__init__(listings)
        self.detail_calls = 0

    def fetch_open_day(self, listing):
        self.detail_calls += 1
        return {"date": self.day, "timeFrom": "11:00", "timeTo": "14:00"}


def test_open_days_become_events_and_notifications(prefs, good_listing):
    engine = make_engine("sqlite://")
    init_db(engine)
    store = Store(engine)
    tg = FakeTelegram()
    run(store, [FakeSource([good_listing])], prefs, tg)  # listing known, bootstrap done
    tg.messages.clear()

    day = (datetime.now(WARSAW) + timedelta(days=3)).date().isoformat()
    with_open_day = copy.deepcopy(good_listing)
    with_open_day.raw = {"open_days": [day]}
    rejected = copy.deepcopy(good_listing)
    rejected.source_id, rejected.floor, rejected.raw = "2", 0, {"open_days": [day]}
    source = OpenDaySource([with_open_day, rejected])
    source.day = day

    stats = run(store, [source], prefs, tg)
    assert stats.events_new == 1  # the rejected flat's open day is ignored
    assert source.detail_calls == 1  # times fetched for the unchanged listing
    assert any("Dzień otwarty" in m[1] and "11:00–14:00" in m[1] for m in tg.messages)

    tg.messages.clear()
    stats = run(store, [source], prefs, tg)
    assert stats.events_new == 0 and source.detail_calls == 1
    assert not any("Dzień otwarty" in m[1] for m in tg.messages)
