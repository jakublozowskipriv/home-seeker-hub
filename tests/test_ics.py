from datetime import UTC, datetime
from types import SimpleNamespace

from homeseeker.ics import _fold, build_ics


def test_feed_contains_events_and_viewings():
    event = SimpleNamespace(
        id=7,
        kind="open_day",
        title="Osiedle Zielone; budynek B",
        starts_at=datetime(2026, 10, 25, 9, 0, tzinfo=UTC),
        ends_at=None,
        location="Poznań, ul. Przemysłowa 1",
        notes="Wejście od dziedzińca\nBez zapisów",
        url="https://example.com/dni-otwarte",
    )
    viewing = SimpleNamespace(
        listing_id="otodom:1",
        viewing_at=datetime(2026, 10, 26, 16, 30, tzinfo=UTC),
        location_text="Poznań, Wilda, ul. Rolna",
        title="2 pokoje",
        note="Zapytać o czynsz",
        url="https://www.otodom.pl/pl/oferta/x",
        price=599000.0,
        area=45.5,
        rooms=2,
    )
    ics = build_ics([event], [viewing])
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == 2
    assert "DTSTART:20261025T090000Z" in ics and "DTEND:20261025T100000Z" in ics
    unfolded = ics.replace("\r\n ", "")
    assert r"SUMMARY:🏠 Dzień otwarty: Osiedle Zielone\; budynek B" in unfolded
    assert "DESCRIPTION:Wejście od dziedzińca\\nBez zapisów" in unfolded
    assert "UID:viewing-otodom:1@home-seeker-hub" in unfolded
    assert "599 000 zł" in unfolded


def test_long_lines_are_folded_to_75_octets():
    folded = _fold("DESCRIPTION:" + "ż" * 100)
    assert all(len(line.encode()) <= 75 for line in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == "DESCRIPTION:" + "ż" * 100


def test_publish_rotates_exposed_token_and_removes_old_file(monkeypatch):
    import httpx

    from homeseeker import ics
    from homeseeker.db import Store, init_db, make_engine

    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={})

    real_client = httpx.Client
    monkeypatch.setattr(
        ics.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co/rest/v1/")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_test")
    engine = make_engine("sqlite://")
    init_db(engine)
    store = Store(engine)
    store.set_setting("calendar_token", "old-token")  # published before rotation existed

    url = ics.publish(store)
    new_token = store.get_setting("calendar_token")
    assert new_token != "old-token"
    assert url == f"https://abc.supabase.co/storage/v1/object/public/calendar/{new_token}.ics"
    assert ("DELETE", "/storage/v1/object/calendar/old-token.ics") in calls

    calls.clear()
    assert ics.publish(store) == url  # stable afterwards
    assert not any(method == "DELETE" for method, _ in calls)
