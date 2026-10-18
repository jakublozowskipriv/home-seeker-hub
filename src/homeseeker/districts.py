"""Matching listings to Poznań districts / estates by name."""

from __future__ import annotations

import re

from .textparse import fold

# Alternative spellings found in listings, folded (no diacritics, lowercase).
ALIASES: dict[str, list[str]] = {
    "lazarz": ["lazarz", "sw. lazarz", "swiety lazarz", "sw lazarz"],
    "stare miasto": ["stare miasto", "starowka"],
    "centrum": ["centrum"],
}


def _patterns(name: str) -> list[str]:
    key = fold(name)
    return ALIASES.get(key, [key])


def matches(name: str, text: str) -> bool:
    return any(re.search(rf"(^|[^a-z]){re.escape(p)}($|[^a-z])", text) for p in _patterns(name))


def classify(
    location_text: str | None, preferred: list[str], allowed: list[str], excluded: list[str]
) -> tuple[str | None, str | None]:
    """Return (category, matched_name) where category is preferred/allowed/excluded/None.

    Only structured location text should be passed (district, address), never the
    description: "10 min do Naramowic" must not exclude a listing.
    """
    text = fold(location_text)
    if not text:
        return None, None
    # Most specific first: an estate name wins over its broader district.
    for category, names in (("excluded", excluded), ("preferred", preferred), ("allowed", allowed)):
        for name in names:
            if matches(name, text):
                return category, name
    return None, None
