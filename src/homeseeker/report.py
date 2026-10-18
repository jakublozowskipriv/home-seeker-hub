"""Markdown run report (GitHub Actions job summary / console)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from .db import Store, listings, row_to_listing
from .notify.format import facts, headline, money
from .pipeline import RunStats

COVERAGE_FIELDS = [
    "price",
    "area",
    "rooms",
    "floor",
    "build_year",
    "market",
    "has_balcony",
    "has_elevator",
    "heating",
    "lat",
    "district",
]


def _coverage(rows: list[Any]) -> dict[str, str]:
    if not rows:
        return {}
    out = {}
    for f in COVERAGE_FIELDS:
        known = sum(1 for r in rows if getattr(r, f) is not None)
        out[f] = f"{100 * known // len(rows)}%"
    return out


def build_report(store: Store, stats: RunStats, top: int = 15) -> str:
    with store.engine.connect() as conn:
        rows = conn.execute(select(listings)).fetchall()
    detailed = [r for r in rows if r.details_fetched]
    best = sorted(
        (r for r in rows if r.verdict in ("match", "review", "negotiable")),
        key=lambda r: r.score or 0,
        reverse=True,
    )

    lines = ["# Home Seeker Hub - raport", ""]
    lines.append("| | |\n|---|---|")
    lines.append(f"| Oferty wg źródła | {dict(stats.seen)} |")
    lines.append(f"| Status | {dict(stats.statuses)} |")
    lines.append(f"| Werdykty | {dict(stats.verdicts)} |")
    lines.append(f"| Powody odrzucenia | {dict(stats.rejections.most_common())} |")
    lines.append(f"| Odrzucone lokalizacje | {dict(stats.rejected_locations.most_common())} |")
    lines.append(f"| Brakujące dane | {dict(stats.missing.most_common())} |")
    lines.append(
        f"| Szczegóły: pobrane / błędy / odłożone | {stats.details_fetched} / "
        f"{stats.details_failed} / {stats.details_deferred} |"
    )
    lines.append(f"| Powiadomienia | {stats.notified} |")
    lines.append(f"| Nowe wydarzenia (dni otwarte, targi) | {stats.events_new} |")
    if stats.incomplete_sources:
        lines.append(f"| Niepełne źródła | {stats.incomplete_sources} |")
    if stats.errors:
        lines.append(f"| Błędy | {stats.errors} |")
    lines.append("")
    lines.append(
        f"**Kompletność danych** (oferty ze szczegółami: {len(detailed)}): `{_coverage(detailed)}`"
    )
    lines.append("")
    lines.append(f"## Najlepsze oferty ({len(best)} pasujących / do sprawdzenia)")
    lines.append("")
    lines.append("| Wynik | Werdykt | Oferta | Cena | Lokalizacja | Dojazd | Cechy | Braki |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in best[:top]:
        listing = row_to_listing(r)
        ev = r.evaluation or {}
        # Postgres JSONB does not keep key order - label each destination.
        commute = ", ".join(
            f"{name.split(' (')[0]} {m:.0f}"
            for name, m in sorted((ev.get("commute") or {}).items())
        )
        lines.append(
            f"| {r.score} | {r.verdict} | [{headline(listing)}]({listing.url}) | "
            f"{money(listing.price)} | {listing.location_text or ''} | {commute} | "
            f"{', '.join(facts(listing))} | {', '.join(ev.get('missing') or [])} |"
        )
    return "\n".join(lines)
