"""Why are listings matching a phrase (an estate, a street) rated the way they are?

Reads stored listings and their evaluations; prints only data from the public adverts
(prices, addresses, reasons), safe for public CI logs.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .db import Store
from .textparse import fold


def _fields(row: Any) -> dict[str, str]:
    raw = row.raw or {}
    investment = (raw.get("investment") or {}).get("title") or ""
    return {
        "lokalizacja": fold(" ".join(x for x in (row.district, row.location_text) if x)),
        "tytuł": fold(row.title),
        "inwestycja": fold(investment),
        "opis": fold(row.description),
    }


def explain(store: Store, phrase: str, limit: int = 40) -> str:
    needle = fold(phrase)
    hits: list[tuple[Any, list[str]]] = []
    for row in store.all_listings():
        where = [name for name, text in _fields(row).items() if needle in text]
        if where:
            hits.append((row, where))
    active = [(r, w) for r, w in hits if r.active]
    lines = [f"# „{phrase}”: {len(hits)} ofert w bazie, aktywnych {len(active)}", ""]
    lines.append(f"Gdzie pada fraza: {dict(Counter(f for _, w in active for f in w))}")
    lines.append(f"Werdykty (aktywne): {dict(Counter(r.verdict for r, _ in active))}")
    reasons: Counter = Counter()
    locations: Counter = Counter()
    for r, _ in active:
        ev = r.evaluation or {}
        reasons.update(ev.get("rejections") or [])
        locations[f"{ev.get('location_category')}: {ev.get('location_name')}"] += 1
    lines.append(f"Kategoria lokalizacji: {dict(locations.most_common())}")
    lines.append("Powody odrzucenia:")
    lines += [f"  {n:>4} × {reason}" for reason, n in reasons.most_common(25)]
    lines.append("")
    lines.append(
        "| werdykt | wynik | cena | m² | pok. | piętro | rynek | dzielnica / adres | "
        "dojazd | powody / braki |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    key = {"match": 0, "review": 1, "negotiable": 2, "rejected": 3}
    for r, where in sorted(active, key=lambda t: (key.get(t[0].verdict, 9), -(t[0].score or 0)))[
        :limit
    ]:
        ev = r.evaluation or {}
        commute = ", ".join(
            f"{name.split(' (')[0]} {m:.0f}"
            for name, m in sorted((ev.get("commute") or {}).items())
        )
        if ev.get("commute_method") == "estimate":
            commute += " (szac.)"
        notes = "; ".join(
            (ev.get("rejections") or []) + [f"brak: {m}" for m in ev.get("missing") or []]
        )
        lines.append(
            f"| {r.verdict} | {r.score} | {r.price or '?'} | {r.area or '?'} | {r.rooms or '?'} | "
            f"{r.floor if r.floor is not None else '?'} | {r.market or '?'} | "
            f"{r.district or ''} / {r.location_text or ''}"
            f"{' (fraza tylko w opisie)' if where == ['opis'] else ''} | {commute} | {notes} |"
        )
    if len(active) > limit:
        lines.append(f"… i {len(active) - limit} więcej")
    return "\n".join(lines)
