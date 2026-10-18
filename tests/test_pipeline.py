import copy

import pytest

from homeseeker.db import Store, init_db, make_engine
from homeseeker.pipeline import run
from homeseeker.sources.base import Source


class FakeSource(Source):
    name = "test"
    complete_search_results = True

    def __init__(self, listings):
        super().__init__(http=None)
        self.listings = listings

    def search(self, prefs, max_pages):
        yield from copy.deepcopy(self.listings)


class FakeTelegram:
    def __init__(self):
        self.messages = []

    def send_text(self, html):
        self.messages.append(("text", html))

    def send_listing(self, html, photo_url):
        self.messages.append(("listing", html))


@pytest.fixture
def store():
    engine = make_engine("sqlite://")
    init_db(engine)
    return Store(engine)


def test_bootstrap_digest_then_new_and_price_drop(store, prefs, good_listing):
    tg = FakeTelegram()
    bad = copy.deepcopy(good_listing)
    bad.source_id, bad.floor = "2", 0

    stats = run(store, [FakeSource([good_listing, bad])], prefs, tg)
    assert stats.verdicts == {"match": 1, "rejected": 1}
    assert len(tg.messages) == 1 and "działa" in tg.messages[0][1]  # first run: one digest

    # Second run: nothing new -> silence.
    tg.messages.clear()
    stats = run(store, [FakeSource([good_listing, bad])], prefs, tg)
    assert stats.statuses == {"unchanged": 2}
    assert tg.messages == []

    # New matching flat -> individual notification.
    new = copy.deepcopy(good_listing)
    new.source_id, new.area, new.lat = "3", 41.0, 52.4000
    run(store, [FakeSource([good_listing, new])], prefs, tg)
    assert len(tg.messages) == 1 and "Nowa oferta" in tg.messages[0][1]

    # Price drop on an already notified flat.
    tg.messages.clear()
    cheaper = copy.deepcopy(new)
    cheaper.price = 650_000
    stats = run(store, [FakeSource([good_listing, cheaper])], prefs, tg)
    assert stats.statuses["price_changed"] == 1
    assert len(tg.messages) == 1 and "Obniżka" in tg.messages[0][1]


def test_duplicate_from_other_portal_not_notified_twice(store, prefs, good_listing):
    tg = FakeTelegram()
    run(store, [FakeSource([])], prefs, tg)  # bootstrap with empty DB
    run(store, [FakeSource([good_listing])], prefs, tg)
    tg.messages.clear()

    dup = copy.deepcopy(good_listing)
    dup.source, dup.source_id, dup.price = "other", "77", 702_000
    run(store, [FakeSource([good_listing]), _named(FakeSource([dup]), "other")], prefs, tg)
    assert tg.messages == []


def _named(source, name):
    source.name = name
    return source


def test_stale_listings_deactivated(store, prefs, good_listing):
    from datetime import timedelta

    from sqlalchemy import update

    from homeseeker.db import listings, now

    run(store, [FakeSource([good_listing])], prefs, None)
    with store.engine.begin() as conn:
        conn.execute(update(listings).values(last_seen_at=now() - timedelta(days=3)))
    stats = run(store, [FakeSource([])], prefs, None)
    assert stats.deactivated == 1


def test_bootstrap_waits_for_deferred_details(store, prefs, good_listing):
    class SlowSource(FakeSource):
        complete_search_results = False

        def fetch_details(self, listing):
            return listing

    second = copy.deepcopy(good_listing)
    second.source_id, second.area = "2", 41.0
    tg = FakeTelegram()
    for item in (good_listing, second):
        item.details_fetched = False
    stats = run(store, [SlowSource([good_listing, second])], prefs, tg, max_details=1)
    assert stats.details_deferred == 1
    assert tg.messages == []  # still indexing

    stats = run(store, [SlowSource([good_listing, second])], prefs, tg, max_details=5)
    assert stats.details_deferred == 0
    assert len(tg.messages) == 1 and "działa" in tg.messages[0][1]


def test_probe_key_tree_redacts_personal_data():
    from homeseeker.cli import _key_tree

    lines = _key_tree({"owner": {"name": "Jan", "phone": "+48123"}, "price": 1})
    assert "owner = <redacted>" in lines
    assert not any("Jan" in line or "+48" in line for line in lines)


def test_placeholder_coordinates_are_treated_as_approximate(store, prefs, good_listing):
    from homeseeker.db import row_to_listing

    other = copy.deepcopy(good_listing)
    other.source_id, other.area, other.location_text = "2", 41.0, "Poznań, Rataje, ul. Inna"
    run(store, [FakeSource([good_listing, other])], prefs, None)
    for listing_id in ("test:1", "test:2"):
        row = store.get(listing_id)
        assert row_to_listing(row).coords_approximate is True
        assert row.evaluation["commute"] == {}
