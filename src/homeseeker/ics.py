"""iCalendar (.ics) feed with open days, fairs and planned viewings.

Published to a public Supabase Storage bucket under an unguessable name, so it can be
subscribed to in Google Calendar and Apple Calendar (which cannot sign in).
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .db import Store, now

log = logging.getLogger(__name__)

BUCKET = "calendar"
DEFAULT_DURATION = timedelta(hours=1)
KIND_EMOJI = {
    "open_day": "🏠 Dzień otwarty",
    "fair": "🎪 Targi",
    "other": "📌",
    "viewing": "📅 Oglądanie",
}


def _escape(text: str | None) -> str:
    text = text or ""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a space (RFC 5545)."""
    out, current = [], ""
    for ch in line:
        if len((current + ch).encode()) > 74:
            out.append(current)
            current = " " + ch
        else:
            current += ch
    out.append(current)
    return "\r\n".join(out)


def _dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def event_block(
    uid: str,
    start: datetime,
    end: datetime | None,
    summary: str,
    location: str | None = None,
    description: str | None = None,
    url: str | None = None,
) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@home-seeker-hub",
        f"DTSTAMP:{_dt(now())}",
        f"DTSTART:{_dt(start)}",
        f"DTEND:{_dt(end or start + DEFAULT_DURATION)}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if url:
        lines.append(f"URL:{url}")
    lines.append("END:VEVENT")
    return lines


def build_ics(events: list[Any], viewings: list[Any]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//home-seeker-hub//PL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Mieszkania",
        "X-WR-TIMEZONE:Europe/Warsaw",
        "REFRESH-INTERVAL;VALUE=DURATION:PT3H",
    ]
    for e in events:
        prefix = KIND_EMOJI.get(e.kind, "📌")
        lines += event_block(
            f"event-{e.id}",
            e.starts_at,
            e.ends_at,
            f"{prefix}: {e.title}",
            e.location,
            e.notes,
            e.url,
        )
    for v in viewings:
        what = ", ".join(
            x
            for x in (
                f"{v.rooms} pok." if v.rooms else None,
                f"{v.area:g} m²" if v.area else None,
                f"{v.price:,.0f} zł".replace(",", " ") if v.price else None,
            )
            if x
        )
        lines += event_block(
            f"viewing-{v.listing_id}",
            v.viewing_at,
            None,
            f"{KIND_EMOJI['viewing']}: {v.location_text or v.title}",
            v.location_text,
            "\n".join(x for x in (what, v.note) if x),
            v.url,
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _headers(key: str) -> dict[str, str]:
    headers = {"apikey": key}
    if key.startswith("eyJ"):  # legacy service_role JWT; new sb_secret_ keys go in apikey only
        headers["Authorization"] = f"Bearer {key}"
    return headers


def publish(store: Store) -> str | None:
    """Upload the feed to Supabase Storage; returns its public URL (or None if not set up)."""
    base = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_SERVICE_KEY") or "").strip()
    if not base or not key:
        log.info("Calendar: SUPABASE_URL / SUPABASE_SERVICE_KEY not set, feed not published")
        return None
    base = httpx.URL(base).copy_with(path="/", query=None, fragment=None)
    base_url = str(base).rstrip("/")
    token = store.get_setting("calendar_token")
    if not token:
        token = secrets.token_urlsafe(24)
        store.set_setting("calendar_token", token)
    evs, viewings = store.calendar_entries(now() - timedelta(days=30))
    body = build_ics(evs, viewings)
    with httpx.Client(timeout=30, headers=_headers(key)) as client:
        client.post(
            f"{base_url}/storage/v1/bucket", json={"id": BUCKET, "name": BUCKET, "public": True}
        )  # exists -> 400, fine
        resp = client.post(
            f"{base_url}/storage/v1/object/{BUCKET}/{token}.ics",
            content=body.encode(),
            headers={
                "Content-Type": "text/calendar; charset=utf-8",
                "x-upsert": "true",
                "Cache-Control": "max-age=300",
            },
        )
    if resp.status_code >= 300:
        log.error("Calendar upload failed: HTTP %s %s", resp.status_code, resp.text[:200])
        return None
    url = f"{base_url}/storage/v1/object/public/{BUCKET}/{token}.ics"
    store.set_setting("calendar_url", url)
    log.info("Calendar published: %s events, %s viewings", len(evs), len(viewings))
    return url
