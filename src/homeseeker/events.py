"""Open days (from listings) and housing fairs (from the organiser's site)."""

from __future__ import annotations

import html
import logging
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .http import FetchError, Http
from .models import Listing
from .notify.format import headline

log = logging.getLogger(__name__)

WARSAW = ZoneInfo("Europe/Warsaw")
FAIRS_URL = "https://targimieszkan.pl/"
# The organiser's page only gives dates; typical opening hours (Sat / Sun).
FAIR_HOURS = {5: (time(10), time(17)), 6: (time(10), time(16))}


def local(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=WARSAW)


def _parse_time(value: str | None) -> time | None:
    if value and (m := re.match(r"(\d{1,2}):(\d{2})", value)):
        return time(int(m.group(1)), int(m.group(2)))
    return None


def open_day_event(listing: Listing, day: str, details: dict | None) -> dict:
    """Event row for an open day of a listing; times from the listing page when known."""
    d = date.fromisoformat(day[:10])
    start_t = _parse_time((details or {}).get("timeFrom"))
    end_t = _parse_time((details or {}).get("timeTo"))
    notes = None if start_t else "Godzina do sprawdzenia w ogłoszeniu."
    start = local(d, start_t or time(10))
    end = local(d, end_t) if end_t else start + timedelta(hours=1)
    return {
        "kind": "open_day",
        "title": f"{headline(listing)} · {listing.district or listing.location_text or ''}",
        "starts_at": start,
        "ends_at": end,
        "location": listing.location_text,
        "url": listing.url,
        "listing_id": listing.id,
        "source": listing.source,
        "external_id": f"{listing.source}-openday:{listing.source_id}:{d.isoformat()}",
        "notes": notes,
    }


_FAIR_RE = re.compile(
    r"title:\s*'(?P<title>[^']*)',\s*start:\s*new Date\('(?P<start>[^']+)'\)"
    r".*?end:\s*new Date\('(?P<end>[^']+)'\)(?:.*?address:\s*'(?P<address>[^']*)')?",
    re.S,
)


def parse_fairs(page: str, city: str = "Pozna") -> list[dict]:
    """Fairs announced on targimieszkan.pl (calendar data embedded in the page)."""
    out = []
    for m in _FAIR_RE.finditer(page):
        title = html.unescape(m.group("title")).strip()
        if city not in title:
            continue
        try:
            first = datetime.fromisoformat(m.group("start").strip()).date()
            last = datetime.fromisoformat(m.group("end").strip()).date()
        except ValueError:
            continue
        address = html.unescape(m.group("address") or "").strip() or None
        day = first
        while day <= last and (day - first).days < 5:
            open_t, close_t = FAIR_HOURS.get(day.weekday(), (time(10), time(17)))
            out.append(
                {
                    "kind": "fair",
                    "title": title,
                    "starts_at": local(day, open_t),
                    "ends_at": local(day, close_t),
                    "location": address or "Poznań",
                    "url": FAIRS_URL,
                    "listing_id": None,
                    "source": "fairs",
                    "external_id": f"fair:{title}:{day.isoformat()}",
                    "notes": "Godziny orientacyjne – sprawdź na stronie organizatora.",
                }
            )
            day += timedelta(days=1)
    return out


def fetch_fairs(http: Http) -> list[dict]:
    try:
        return parse_fairs(http.get(FAIRS_URL).text)
    except FetchError as e:
        log.warning("Fairs: %s", e)
        return []


def event_message(event: Any) -> str:
    from html import escape

    def in_warsaw(value: datetime) -> datetime:
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(WARSAW)

    start = in_warsaw(event.starts_at)
    end = in_warsaw(event.ends_at) if event.ends_at else None
    day = ["pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."][start.weekday()]
    when = f"{day} {start:%d.%m, %H:%M}" + (f"–{end:%H:%M}" if end else "")
    icon = {"open_day": "🏠 Dzień otwarty", "fair": "🎪 Targi"}.get(event.kind, "📌")
    lines = [f"{icon}: <b>{escape(event.title)}</b>", f"🗓 {when}"]
    if event.location:
        lines.append(f"📍 {escape(event.location)}")
    if event.url:
        lines.append(f'🔗 <a href="{escape(event.url)}">Szczegóły</a>')
    return "\n".join(lines)
