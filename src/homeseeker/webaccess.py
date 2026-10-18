"""Row level security for the web app (Supabase).

The browser talks to Supabase directly with the public anon key, so the database itself
decides who sees what: only people listed in `members` (signed in with that e-mail) can
read listings; only the owner changes preferences, statuses and the member list; everyone
manages their own reactions, comments and visits. The scraper connects as the database
owner and is not affected.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

FUNCTIONS = [
    """
    create or replace function public.hs_email() returns text
    language sql stable as $$
      select lower(coalesce(auth.jwt() ->> 'email', ''))
    $$
    """,
    """
    create or replace function public.hs_is_member() returns boolean
    language sql stable security definer set search_path = public as $$
      select exists (select 1 from public.members m where m.email = public.hs_email())
    $$
    """,
    """
    create or replace function public.hs_is_owner() returns boolean
    language sql stable security definer set search_path = public as $$
      select exists (
        select 1 from public.members m where m.email = public.hs_email() and m.role = 'owner'
      )
    $$
    """,
]

MEMBER = "public.hs_is_member()"
OWNER = "public.hs_is_owner()"
ME = "public.hs_email()"

# (table, policy name, command, using, with check)
POLICIES: list[tuple[str, str, str, str | None, str | None]] = [
    ("listings", "members read", "select", MEMBER, None),
    ("price_history", "members read", "select", MEMBER, None),
    ("runs", "members read", "select", MEMBER, None),
    ("settings", "members read preferences", "select", f"{MEMBER} and key = 'preferences'", None),
    ("settings", "owner reads calendar link", "select", f"{OWNER} and key = 'calendar_url'", None),
    ("settings", "owner adds preferences", "insert", None, f"{OWNER} and key = 'preferences'"),
    (
        "settings",
        "owner edits preferences",
        "update",
        f"{OWNER} and key = 'preferences'",
        f"{OWNER} and key = 'preferences'",
    ),
    ("members", "members read", "select", MEMBER, None),
    ("members", "owner adds", "insert", None, OWNER),
    ("members", "owner edits", "update", OWNER, OWNER),
    ("members", "owner removes", "delete", f"{OWNER} and email <> {ME}", None),
    ("listing_status", "members read", "select", MEMBER, None),
    ("listing_status", "owner adds", "insert", None, OWNER),
    ("listing_status", "owner edits", "update", OWNER, OWNER),
    ("listing_status", "owner removes", "delete", OWNER, None),
    ("reactions", "members read", "select", MEMBER, None),
    ("reactions", "own add", "insert", None, f"{MEMBER} and email = {ME}"),
    ("reactions", "own edit", "update", f"email = {ME}", f"{MEMBER} and email = {ME}"),
    ("reactions", "own remove", "delete", f"email = {ME}", None),
    ("comments", "members read", "select", MEMBER, None),
    ("comments", "own add", "insert", None, f"{MEMBER} and author_email = {ME}"),
    ("comments", "own or owner removes", "delete", f"author_email = {ME} or {OWNER}", None),
    ("events", "members read", "select", MEMBER, None),
    (
        "events",
        "members add own",
        "insert",
        None,
        f"{MEMBER} and created_by = {ME} and source = 'manual'",
    ),
    ("events", "creator or owner removes", "delete", f"created_by = {ME} or {OWNER}", None),
    # One shared checklist per listing: every member ticks items, signed with their e-mail.
    ("viewing_checklists", "members read", "select", MEMBER, None),
    ("viewing_checklists", "members add", "insert", None, f"{MEMBER} and updated_by = {ME}"),
    (
        "viewing_checklists",
        "members edit",
        "update",
        MEMBER,
        f"{MEMBER} and updated_by = {ME}",
    ),
    ("member_visits", "members read", "select", MEMBER, None),
    ("member_visits", "own add", "insert", None, f"{MEMBER} and email = {ME}"),
    ("member_visits", "own edit", "update", f"email = {ME}", f"email = {ME}"),
]

GRANTS = [
    "grant select on public.listings, public.price_history, public.runs to authenticated",
    "grant select, insert, update on public.settings to authenticated",
    "grant select, insert, update, delete on public.members, public.listing_status, "
    "public.reactions, public.comments, public.member_visits, public.events, "
    "public.viewing_checklists to authenticated",
    "grant usage, select on sequence public.comments_id_seq, public.events_id_seq to authenticated",
]


def policy_statements() -> list[str]:
    out = []
    for table, name, command, using, check in POLICIES:
        name = f"hs: {name}"
        out.append(f'drop policy if exists "{name}" on public.{table}')
        sql = f'create policy "{name}" on public.{table} for {command} to authenticated'
        if using:
            sql += f" using ({using})"
        if check:
            sql += f" with check ({check})"
        out.append(sql)
    return out


def apply_policies(conn: Connection) -> None:
    """Idempotent; skipped on plain Postgres without Supabase's auth schema and roles."""
    has_auth = conn.execute(
        text(
            "select to_regnamespace('auth') is not null and "
            "exists (select 1 from pg_roles where rolname = 'authenticated')"
        )
    ).scalar()
    if not has_auth:
        return
    for statement in FUNCTIONS + policy_statements() + GRANTS:
        conn.execute(text(statement))
