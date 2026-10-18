"""One scraping run: search sources, enrich, evaluate, store, notify."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from . import dedup
from .db import Store, now, row_to_listing
from .evaluate import Evaluation, Verdict, evaluate
from .http import FetchError
from .models import Listing
from .notify.format import listing_html, money
from .notify.telegram import Telegram, TelegramError
from .preferences import Preferences
from .sources.base import Source

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(days=2)
BOOTSTRAP_DIGEST_SIZE = 10


@dataclass
class RunStats:
    seen: Counter = field(default_factory=Counter)  # per source
    statuses: Counter = field(default_factory=Counter)  # new / price_changed / updated / unchanged
    verdicts: Counter = field(default_factory=Counter)
    rejections: Counter = field(default_factory=Counter)
    missing: Counter = field(default_factory=Counter)
    details_fetched: int = 0
    details_failed: int = 0
    details_deferred: int = 0
    notified: int = 0
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

    for listing in source.search(prefs, max_pages):
        if listing.id in seen:
            continue
        seen.add(listing.id)
        stats.seen[source.name] += 1
        existing = store.get(listing.id)

        if existing is not None and existing.details_fetched:
            if existing.price == listing.price or listing.price is None:
                store.touch(listing.id)
                stats.statuses["unchanged"] += 1
                continue
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

        ev = evaluate(listing, prefs)
        group = None
        if ev.verdict != Verdict.REJECTED:
            group = dedup.find_group(listing, candidates)
        status = store.upsert(listing, ev, group)
        stats.statuses[status] += 1
        stats.verdicts[ev.verdict.value] += 1
        for r in ev.rejections:
            stats.rejections[_reason_key(r)] += 1
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

    if not source.search_complete:
        stats.incomplete_sources.append(source.name)
    stats.errors += [f"{source.name}: {e}" for e in source.errors]
    return drops


def _evaluation_from_row(row: Any) -> Evaluation:
    data = dict(row.evaluation or {})
    data["verdict"] = Verdict(data.get("verdict", row.verdict))
    return Evaluation(**data)


def send_notifications(
    store: Store,
    prefs: Preferences,
    telegram: Telegram | None,
    drops: list[PriceDrop],
    stats: RunStats,
) -> None:
    pending = store.pending_notifications(notifiable_verdicts(prefs))
    # Keep only the best listing of each duplicate group, and skip groups already sent.
    chosen, groups = [], set()
    for row in pending:
        group = row.group_id or row.id
        if group in groups or (row.group_id and store.group_notified(row.group_id)):
            continue
        groups.add(group)
        chosen.append(row)

    bootstrap = store.get_setting("bootstrapped") is None
    if telegram is None:
        if not bootstrap:
            log.info("Telegram not configured: %s listings wait for notification", len(chosen))
        return

    try:
        if bootstrap:
            lines = [
                f"👋 <b>Home Seeker Hub działa!</b> Znalazłem {len(chosen)} pasujących "
                f"ofert. Oto {min(len(chosen), BOOTSTRAP_DIGEST_SIZE)} najlepszych - "
                "od teraz będę pisać tylko o nowych ofertach i obniżkach cen."
            ]
            for row in chosen[:BOOTSTRAP_DIGEST_SIZE]:
                listing = row_to_listing(row)
                lines.append(
                    f'• <a href="{listing.url}">{row.score}/100 · '
                    f"{money(listing.price)} · {listing.area:g} m² · "
                    f"{listing.location_text or listing.district or ''}</a>"
                )
            telegram.send_text("\n".join(lines))
            for row in pending:
                store.mark_notified(row.id, row.price)
            store.set_setting("bootstrapped", now().isoformat())
            stats.notified += len(chosen)
            return

        limit = prefs.notifications.max_per_run
        for row in chosen[:limit]:
            listing, ev = row_to_listing(row), _evaluation_from_row(row)
            telegram.send_listing(
                listing_html(listing, ev), listing.images[0] if listing.images else None
            )
            store.mark_notified(row.id, row.price)
            stats.notified += 1
        if len(chosen) > limit:
            telegram.send_text(
                f"…i jeszcze {len(chosen) - limit} ofert - wyślę je przy kolejnym przebiegu."
            )
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
    max_pages: int = 30,
    max_details: int = 60,
) -> RunStats:
    stats = RunStats()
    run_id = store.start_run()
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

    send_notifications(store, prefs, telegram, drops, stats)
    store.finish_run(run_id, stats.to_dict())
    return stats
