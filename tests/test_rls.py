"""Row level security of the web app, checked on a real Postgres with Supabase's auth
emulated (roles `anon`/`authenticated`, `auth.jwt()` reading the request claims).

Runs when HOMESEEKER_TEST_PG_URL points to a Postgres superuser connection, e.g.
postgresql://postgres@127.0.0.1:5432/postgres (CI starts one as a service).
"""

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, insert, text

from homeseeker.db import init_db, listings, make_engine, now, seed_owner, settings

PG_URL = os.environ.get("HOMESEEKER_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="HOMESEEKER_TEST_PG_URL not set")

OWNER, MEMBER, STRANGER = "owner@example.com", "mama@example.com", "obcy@example.com"

SUPABASE_EMULATION = [
    "do $$ begin create role anon nologin; exception when duplicate_object then null; end $$",
    "do $$ begin create role authenticated nologin; exception when duplicate_object then null;"
    " end $$",
    "create schema if not exists auth",
    """create or replace function auth.jwt() returns jsonb language sql stable as $$
         select coalesce(cast(nullif(current_setting('request.jwt.claims', true), '') as jsonb),
                         cast('{}' as jsonb))
       $$""",
    "grant usage on schema auth to authenticated, anon",
    "grant usage on schema public to authenticated, anon",
]


@pytest.fixture(scope="module")
def engine():
    admin = create_engine(
        PG_URL.replace("postgresql://", "postgresql+psycopg://"), isolation_level="AUTOCOMMIT"
    )
    name = f"hs_rls_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(text(f"create database {name}"))
    url = PG_URL.rsplit("/", 1)[0] + f"/{name}"
    eng = make_engine(url)
    with eng.begin() as conn:
        for statement in SUPABASE_EMULATION:
            conn.execute(text(statement))
    init_db(eng)
    init_db(eng)  # idempotent
    seed_owner(eng, OWNER.upper())
    with eng.begin() as conn:
        conn.execute(
            text("insert into members (email, role, created_at) values (:e, 'member', now())"),
            {"e": MEMBER},
        )
        conn.execute(
            insert(listings).values(
                id="otodom:1",
                source="otodom",
                source_id="1",
                url="https://x",
                verdict="match",
                first_seen_at=now(),
                last_seen_at=now(),
                active=True,
                details_fetched=True,
                coords_approximate=False,
            )
        )
        conn.execute(insert(settings).values(key="telegram_chat_id", value=123, updated_at=now()))
    yield eng
    eng.dispose()
    with admin.connect() as conn:
        conn.execute(text(f"drop database {name} with (force)"))


def as_user(engine, email, sql, params=None):
    """Run one statement as a signed-in Supabase user; returns rows (or raises)."""
    with engine.connect() as conn, conn.begin() as tx:
        conn.execute(text("set local role authenticated"))
        conn.execute(
            text("select set_config('request.jwt.claims', :c, true)"),
            {"c": json.dumps({"email": email, "role": "authenticated"})},
        )
        result = conn.execute(text(sql), params or {})
        rows = result.fetchall() if result.returns_rows else result.rowcount
        tx.rollback()
        return rows


def denied(engine, email, sql, params=None) -> bool:
    try:
        result = as_user(engine, email, sql, params)
    except Exception as e:  # RLS violation or missing privilege
        return "row-level security" in str(e) or "permission denied" in str(e)
    return result == 0  # silently filtered update/delete


def test_only_members_read_listings(engine):
    assert len(as_user(engine, MEMBER, "select id from listings")) == 1
    assert len(as_user(engine, OWNER, "select id from listings")) == 1
    assert as_user(engine, STRANGER, "select id from listings") == []
    assert as_user(engine, STRANGER, "select email from members") == []


def test_settings_only_preferences_visible(engine):
    assert as_user(engine, MEMBER, "select key from settings") == []
    assert as_user(engine, OWNER, "select key from settings") == []  # chat id stays hidden


def test_only_owner_changes_preferences_status_and_members(engine):
    prefs = "insert into settings (key, value, updated_at) values ('preferences', '{}', now())"
    assert as_user(engine, OWNER, prefs) == 1
    assert denied(engine, MEMBER, prefs)
    assert denied(
        engine,
        OWNER,
        "insert into settings (key, value, updated_at) values ('telegram_chat_id', '1', now())",
    )

    status = (
        "insert into listing_status (listing_id, status, updated_at) "
        "values ('otodom:1', 'interesting', now())"
    )
    assert as_user(engine, OWNER, status) == 1
    assert denied(engine, MEMBER, status)

    add = "insert into members (email, role, created_at) values ('ciocia@x.pl', 'member', now())"
    assert as_user(engine, OWNER, add) == 1
    assert denied(engine, MEMBER, add)
    assert denied(
        engine, MEMBER, "update members set role = 'owner' where email = :e", {"e": MEMBER}
    )
    assert denied(engine, OWNER, "delete from members where email = :e", {"e": OWNER})
    assert as_user(engine, OWNER, "delete from members where email = :e", {"e": MEMBER}) == 1


def test_reactions_and_comments_are_personal(engine):
    react = (
        "insert into reactions (listing_id, email, reaction, created_at) "
        "values ('otodom:1', :e, 'up', now())"
    )
    assert as_user(engine, MEMBER, react, {"e": MEMBER}) == 1
    assert denied(engine, MEMBER, react, {"e": OWNER})  # cannot react as someone else
    assert denied(engine, STRANGER, react, {"e": STRANGER})

    comment = (
        "insert into comments (listing_id, author_email, body, created_at) "
        "values ('otodom:1', :e, 'Ładna kuchnia', now())"
    )
    assert as_user(engine, MEMBER, comment, {"e": MEMBER}) == 1
    assert denied(engine, MEMBER, comment, {"e": OWNER})


def test_scraper_connection_is_not_restricted(engine):
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from settings")).scalar() >= 1


def test_events_manual_only_from_the_browser(engine):
    add = (
        "insert into events (kind, title, starts_at, source, created_by, created_at) "
        "values ('other', 'Spotkanie z doradcą', now(), :source, :by, now())"
    )
    assert as_user(engine, MEMBER, add, {"source": "manual", "by": MEMBER}) == 1
    assert denied(engine, MEMBER, add, {"source": "otodom", "by": MEMBER})
    assert denied(engine, MEMBER, add, {"source": "manual", "by": OWNER})
    assert denied(engine, STRANGER, add, {"source": "manual", "by": STRANGER})


def test_calendar_link_visible_to_owner_only(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into settings (key, value, updated_at) "
                "values ('calendar_url', '\"https://x\"', now())"
            )
        )
    assert len(as_user(engine, OWNER, "select key from settings where key = 'calendar_url'")) == 1
    assert as_user(engine, MEMBER, "select key from settings where key = 'calendar_url'") == []


def test_checklist_shared_by_members(engine):
    add = (
        "insert into viewing_checklists (listing_id, items, updated_by, updated_at) "
        "values ('otodom:1', '{\"damp\": {\"done\": true}}', :by, now())"
    )
    assert as_user(engine, MEMBER, add, {"by": MEMBER}) == 1
    assert denied(engine, MEMBER, add, {"by": OWNER})  # signed with someone else's e-mail
    assert denied(engine, STRANGER, add, {"by": STRANGER})
    with engine.begin() as conn:
        conn.execute(text(add.replace(":by", "'mama@example.com'")))
    edit = "update viewing_checklists set items = '{}', updated_by = :by, updated_at = now()"
    assert as_user(engine, OWNER, edit, {"by": OWNER}) == 1
    assert denied(engine, STRANGER, edit, {"by": STRANGER})
    assert len(as_user(engine, MEMBER, "select listing_id from viewing_checklists")) == 1
    assert as_user(engine, STRANGER, "select listing_id from viewing_checklists") == []
