"""One scraping run: search sources, enrich, evaluate, store, notify."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from . import dedup
from .db import Store, now, row_to_listing
from .evaluate import Evaluation, Verdict, evaluate
from .events import event_message, fetch_fairs, open_day_event
from .http import FetchError, Http
from .models import Listing
from .notify.format import listing_html, money
from .notify.telegram import Telegram, TelegramError
from .preferences import Preferences
from .sources.base import Source
from .textparse import fold

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(days=2)
# Bump when evaluation rules change, so stored listings get re-evaluated.
EVALUATION_VERSION = 1
DIGEST_SIZE = 10


@dataclass
class RunStats:
    seen: Counter = field(default_factory=Counter)  # per source
    statuses: Counter = field(default_factory=Counter)  # new / price_changed / updated / unchanged
    verdicts: Counter = field(default_factory=Counter)
    rejections: Counter = field(default_factory=Counter)
    rejected_locations: Counter = field(default_factory=Counter)
    missing: Counter = field(default_factory=Counter)
    details_fetched: int = 0
    details_failed: int = 0
    details_deferred: int = 0
    notified: int = 0
    events_new: int = 0
    deactivated: int = 0
    incomplete_sources: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: dict(v) if isinstance(v, Counter) else v for k, v in self.__dict__.items()}


@dataclass
class PriceDrop:
    listing: Listing
    evaluation: Evaluation
    old_price: float


def notifiable_verdicts(prefs: Preferences) -> list[str]:
    out = [Verdict.MATCH.value]
    if prefs.notifications.notify_review:
        out.append(Verdict.REVIEW.value)
    if prefs.notifications.notify_negotiable:
        out.append(Verdict.NEGOTIABLE.value)
    return out


REASON_KEYS = [
    "cena",
    "metraż",
    "pok.",
    "parter",
    "za nisko",
    "brak balkonu",
    "ogrzewanie",
    "rynek",
    "oddanie",
    "lokalizacja",
    "za daleko",
]


def _reason_key(text: str) -> str:
    """Group rejection reasons: 'cena 900 000 zł powyżej budżetu' -> 'cena'."""
    return next((k for k in REASON_KEYS if k in text), text)


def collect_open_days(
    listing: Listing,
    verdict: str | None,
    source: Source,
    store: Store,
    known_events: set[str],
    stats: RunStats,
) -> None:
    """Create events for announced open days of a (non-rejected) listing."""
    dates = [d for d in listing.raw.get("open_days") or [] if d >= now().date().isoformat()]
    if not dates or verdict in (None, Verdict.REJECTED.value):
        return
    details = listing.raw.get("open_day")
    for day in dates:
        event = open_day_event(listing, day, None)
        if event["external_id"] in known_events:
            continue
        if not details or details.get("date") != day:
            try:
                details = source.fetch_open_day(listing)
            except FetchError as e:
                log.warning("Open day details failed for %s: %s", listing.url, e)
        if details and details.get("date") == day:
            event = open_day_event(listing, day, details)
        store.upsert_event(event)
        known_events.add(event["external_id"])
        stats.events_new += 1


def process_source(
    source: Source,
    store: Store,
    prefs: Preferences,
    stats: RunStats,
    max_pages: int,
    max_details: int,
    notify_verdicts: list[str],
) -> list[PriceDrop]:
    drops: list[PriceDrop] = []
    seen: set[str] = set()
    details_budget = max_details
    candidates = store.active_candidates()
    known = store.load_source(source.name)
    known_events = store.event_ids()
    unchanged: list[str] = []

    for listing in source.search(prefs, max_pages):
        if listing.id in seen:
            continue
        seen.add(listing.id)
        stats.seen[source.name] += 1
        existing = known.get(listing.id)

        # Fully known (or rejected from search data alone) and same price: nothing to do.
        if (
            existing is not None
            and (existing.details_fetched or existing.verdict == Verdict.REJECTED.value)
            and (existing.price == listing.price or listing.price is None)
        ):
            unchanged.append(listing.id)
            if listing.raw.get("open_days"):
                full = row_to_listing(existing)
                full.raw = {**full.raw, "open_days": listing.raw["open_days"]}
                collect_open_days(full, existing.verdict, source, store, known_events, stats)
            continue
        if existing is not None and existing.details_fetched:
            # Price changed: details are already known, no need to refetch.
            merged = row_to_listing(existing)
            merged.price = listing.price
            listing = merged

        if not listing.details_fetched and not source.complete_search_results:
            pre = evaluate(listing, prefs)
            if pre.verdict != Verdict.REJECTED:
                if details_budget > 0:
                    details_budget -= 1
                    try:
                        listing = source.fetch_details(listing)
                        stats.details_fetched += 1
                    except FetchError as e:
                        stats.details_failed += 1
                        log.warning("Details failed for %s: %s", listing.url, e)
                else:
                    stats.details_deferred += 1

        if listing.has_coords and not listing.coords_approximate:
            _detect_placeholder_coords(listing, store, prefs)

        ev = evaluate(listing, prefs)
        group = None
        if ev.verdict != Verdict.REJECTED:
            group = dedup.find_group(listing, candidates)
        status = store.upsert(listing, ev, group)
        stats.statuses[status] += 1
        collect_open_days(listing, ev.verdict.value, source, store, known_events, stats)
        stats.verdicts[ev.verdict.value] += 1
        for r in ev.rejections:
            stats.rejections[_reason_key(r)] += 1
            if r.startswith("lokalizacja: "):
                stats.rejected_locations[r.removeprefix("lokalizacja: ")] += 1
        for m in ev.missing:
            stats.missing[m] += 1

        if (
            status == "price_changed"
            and existing is not None
            and existing.notified_at
            and existing.notified_price
            and listing.price
            and listing.price < existing.notified_price
            and ev.verdict.value in notify_verdicts
        ):
            drops.append(PriceDrop(listing, ev, existing.notified_price))

    store.touch_many(unchanged)
    stats.statuses["unchanged"] += len(unchanged)
    if not source.search_complete:
        stats.incomplete_sources.append(source.name)
    stats.errors += [f"{source.name}: {e}" for e in source.errors]
    return drops


def _detect_placeholder_coords(listing: Listing, store: Store, prefs: Preferences) -> None:
    """Portals put listings without an exact address on a placeholder point (e.g. the city
    centre). Different addresses sharing identical coordinates means the point is fake."""
    others = [
        r for r in store.same_point(listing) if fold(r.location_text) != fold(listing.location_text)
    ]
    if not others:
        return
    listing.coords_approximate = True
    for row in others:
        if row.coords_approximate:
            continue
        other = row_to_listing(row)
        other.coords_approximate = True
        store.upsert(other, evaluate(other, prefs), row.group_id)


def evaluation_fingerprint(prefs: Preferences) -> str:
    payload = json.dumps([EVALUATION_VERSION, prefs.model_dump(mode="json")], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def reevaluate_if_needed(store: Store, prefs: Preferences) -> int:
    """Re-evaluate every stored listing when preferences or rules changed."""
    fingerprint = evaluation_fingerprint(prefs)
    previous = store.get_setting("evaluation_fingerprint")
    if previous == fingerprint:
        return 0
    updates = []
    if previous is not None:
        for row in store.all_listings():
            ev = evaluate(row_to_listing(row), prefs)
            updates.append(
                {
                    "id": row.id,
                    "verdict": ev.verdict.value,
                    "score": ev.score,
                    "evaluation": ev.to_dict(),
                }
            )
        store.update_evaluations(updates)
        log.info("Preferences or rules changed: re-evaluated %s listings", len(updates))
    store.set_setting("evaluation_fingerprint", fingerprint)
    return len(updates)


def _evaluation_from_row(row: Any) -> Evaluation:
    data = dict(row.evaluation or {})
    data["verdict"] = Verdict(data.get("verdict", row.verdict))
    return Evaluation(**data)


def _digest(chosen: list[Any], header: str) -> str:
    lines = [header]
    for row in chosen[:DIGEST_SIZE]:
        listing = row_to_listing(row)
        lines.append(
            f'• <a href="{listing.url}">{row.score}/100 · '
            f"{money(listing.price)} · {listing.area:g} m² · "
            f"{listing.location_text or listing.district or ''}</a>"
        )
    return "\n".join(lines)


MAX_EVENT_MESSAGES = 10


def send_event_notifications(store: Store, telegram: Telegram, stats: RunStats) -> None:
    """New open days of listings still in the game, and new fairs."""
    pending = store.pending_event_notifications()
    if not pending:
        return
    verdicts = store.verdicts([e.listing_id for e in pending if e.listing_id])
    relevant = [
        e
        for e in pending
        if e.listing_id is None or verdicts.get(e.listing_id) != Verdict.REJECTED.value
    ]
    try:
        if len(relevant) > MAX_EVENT_MESSAGES:
            lines = [f"🗓 <b>{len(relevant)} nowych wydarzeń</b> – najbliższe:"]
            lines += [event_message(e).split("\n")[0] for e in relevant[:MAX_EVENT_MESSAGES]]
            telegram.send_text("\n".join(lines))
        else:
            for e in relevant:
                telegram.send_text(event_message(e))
        stats.notified += len(relevant)
        store.mark_events_notified([e.id for e in pending])
    except TelegramError as e:
        stats.errors.append(str(e))
        log.error("Telegram error: %s", e)


def send_notifications(
    store: Store,
    prefs: Preferences,
    telegram: Telegram | None,
    drops: list[PriceDrop],
    stats: RunStats,
) -> None:
    pending = store.pending_notifications(notifiable_verdicts(prefs))
    # Keep only the best listing of each duplicate group, and skip groups already sent.
    already_sent = store.notified_groups() if pending else set()
    chosen, groups = [], set()
    for row in pending:
        group = row.group_id or row.id
        if group in groups or group in already_sent:
            continue
        groups.add(group)
        chosen.append(row)

    bootstrap = store.get_setting("bootstrapped") is None
    if telegram is None:
        if not bootstrap:
            log.info("Telegram not configured: %s listings wait for notification", len(chosen))
        return

    try:
        if bootstrap and (stats.details_deferred or stats.incomplete_sources):
            # Initial indexing still in progress: collect silently, digest comes at the end.
            log.info("Bootstrap in progress (%s detail pages deferred)", stats.details_deferred)
            return
        if bootstrap or len(chosen) > prefs.notifications.max_per_run:
            # First run, or a big batch at once (e.g. a newly covered group of listings):
            # one summary instead of a flood of messages.
            if bootstrap:
                header = (
                    f"👋 <b>Home Seeker Hub działa!</b> Znalazłem {len(chosen)} pasujących "
                    f"ofert. Oto {min(len(chosen), DIGEST_SIZE)} najlepszych - od teraz będę "
                    "pisać tylko o nowych ofertach i obniżkach cen."
                )
            else:
                header = (
                    f"🆕 <b>{len(chosen)} nowych pasujących ofert</b>. "
                    f"Oto {min(len(chosen), DIGEST_SIZE)} najlepszych:"
                )
            if chosen:
                telegram.send_text(_digest(chosen, header))
            store.mark_notified_many(pending)
            if bootstrap:
                store.set_setting("bootstrapped", now().isoformat())
            stats.notified += len(chosen)
            return

        for row in chosen:
            listing, ev = row_to_listing(row), _evaluation_from_row(row)
            telegram.send_listing(
                listing_html(listing, ev), listing.images[0] if listing.images else None
            )
            stats.notified += 1
        # Duplicates of what was just sent count as notified too.
        store.mark_notified_many(pending)
        for drop in drops:
            prefix = f"📉 Obniżka z {money(drop.old_price)}"
            telegram.send_listing(
                listing_html(drop.listing, drop.evaluation, prefix),
                drop.listing.images[0] if drop.listing.images else None,
            )
            store.mark_notified(drop.listing.id, drop.listing.price)
            stats.notified += 1
    except TelegramError as e:
        stats.errors.append(str(e))
        log.error("Telegram error: %s", e)


def run(
    store: Store,
    sources: list[Source],
    prefs: Preferences,
    telegram: Telegram | None,
    max_pages: int = 50,
    max_details: int = 60,
    fairs_http: Http | None = None,
) -> RunStats:
    stats = RunStats()
    run_id = store.start_run()
    reevaluate_if_needed(store, prefs)
    started = now()
    drops: list[PriceDrop] = []
    verdicts = notifiable_verdicts(prefs)
    for source in sources:
        try:
            drops += process_source(source, store, prefs, stats, max_pages, max_details, verdicts)
        except Exception as e:  # one broken portal must not stop the others
            log.exception("Source %s crashed", source.name)
            stats.errors.append(f"{source.name}: {e}")
            stats.incomplete_sources.append(source.name)

    complete = [s.name for s in sources if s.name not in stats.incomplete_sources]
    if complete:
        stats.deactivated = store.deactivate_stale(complete, started - STALE_AFTER)

    if fairs_http is not None:
        known = store.event_ids()
        for event in fetch_fairs(fairs_http):
            if event["external_id"] not in known:
                store.upsert_event(event)
                stats.events_new += 1

    send_notifications(store, prefs, telegram, drops, stats)
    if telegram is not None:
        send_event_notifications(store, telegram, stats)
    store.finish_run(run_id, stats.to_dict())
    return stats
