"""Hard filters and weighted 0-100 scoring of a listing against preferences."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum

from . import districts, geo
from .models import Heating, Listing, Market, Ownership
from .preferences import Preferences

# Commute is only estimated for now, so allow some slack before a hard rejection.
COMMUTE_TOLERANCE = 1.25


class Verdict(StrEnum):
    MATCH = "match"  # spełnia wszystkie twarde kryteria
    REVIEW = "review"  # brak kluczowych danych - do sprawdzenia
    NEGOTIABLE = "negotiable"  # cena lekko powyżej budżetu
    REJECTED = "rejected"


@dataclass
class Evaluation:
    verdict: Verdict
    score: int
    rejections: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    location_category: str | None = None
    location_name: str | None = None
    commute: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y1
    return y0 + (y1 - y0) * _clamp((x - x0) / (x1 - x0))


def evaluate(listing: Listing, prefs: Preferences) -> Evaluation:
    rejections: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []
    negotiable = False
    budget = prefs.budget

    # --- price
    if listing.price is None:
        missing.append("cena")
    elif listing.price > budget.hard_max:
        rejections.append(f"cena {listing.price:,.0f} zł powyżej budżetu".replace(",", " "))
    elif listing.price > budget.max_price:
        negotiable = True

    # --- area and rooms
    if listing.area is None:
        missing.append("metraż")
    elif (prefs.area.min and listing.area < prefs.area.min) or (
        prefs.area.max and listing.area > prefs.area.max
    ):
        rejections.append(f"metraż {listing.area:g} m² poza zakresem")
    if listing.rooms is None:
        missing.append("liczba pokoi")
    elif (prefs.rooms.min and listing.rooms < prefs.rooms.min) or (
        prefs.rooms.max and listing.rooms > prefs.rooms.max
    ):
        rejections.append(f"{listing.rooms} pok. poza zakresem")

    # --- floor
    if listing.floor is None:
        missing.append("piętro")
    elif listing.floor < prefs.floor.min:
        rejections.append("parter" if listing.floor == 0 else f"za nisko ({listing.floor}. p.)")

    # --- balcony, heating, ownership
    if prefs.balcony_required:
        if listing.has_balcony is False:
            rejections.append("brak balkonu")
        elif listing.has_balcony is None:
            missing.append("balkon")
    if prefs.exclude_gas_heating and listing.heating == Heating.GAS:
        rejections.append("ogrzewanie gazowe")
    if listing.heating is None:
        warnings.append("nieznane ogrzewanie")
    if listing.ownership == Ownership.COOPERATIVE:
        warnings.append("spółdzielcze własnościowe")

    # --- market and completion date
    if listing.market and listing.market.value not in prefs.markets:
        rejections.append(f"rynek {listing.market.value}")
    if (
        listing.market == Market.PRIMARY
        and prefs.completion_deadline
        and listing.completion_date
        and listing.completion_date > prefs.completion_deadline
    ):
        rejections.append(f"oddanie {listing.completion_date:%m.%Y}")

    # --- location
    loc_text = ", ".join(x for x in (listing.district, listing.location_text) if x)
    category, name = districts.classify(
        loc_text, prefs.locations.preferred, prefs.locations.allowed, prefs.locations.excluded
    )
    if category == "excluded":
        rejections.append(f"lokalizacja: {name}")

    commute: dict[str, float] = {}
    if listing.has_coords:
        for dest in prefs.destinations:
            commute[dest.name] = geo.estimate_commute_minutes(
                listing.lat, listing.lon, dest.lat, dest.lon
            )
        limit = prefs.commute.max_minutes
        too_far = [n for n, m in commute.items() if m > limit * COMMUTE_TOLERANCE]
        if too_far and listing.coords_approximate:
            warnings.append("przybliżona lokalizacja, możliwy długi dojazd")
        elif too_far:
            rejections.append("za daleko: " + ", ".join(too_far))
        elif any(m > limit for m in commute.values()):
            warnings.append("dojazd na granicy limitu")
    elif category is None:
        missing.append("lokalizacja")

    score = _score(listing, prefs, category, commute)

    if rejections:
        verdict = Verdict.REJECTED
    elif negotiable:
        verdict = Verdict.NEGOTIABLE
    elif missing:
        verdict = Verdict.REVIEW
    else:
        verdict = Verdict.MATCH

    return Evaluation(
        verdict=verdict,
        score=score,
        rejections=rejections,
        missing=missing,
        warnings=warnings,
        location_category=category,
        location_name=name,
        commute=commute,
    )


def _score(
    listing: Listing, prefs: Preferences, location_category: str | None, commute: dict[str, float]
) -> int:
    w = prefs.weights
    parts: dict[str, float] = {}

    parts["location"] = {"preferred": 1.0, "allowed": 0.6, "excluded": 0.0}.get(
        location_category or "", 0.3
    )

    if commute:
        limit = prefs.commute.max_minutes
        vals = [_lerp(m, 8, limit * COMMUTE_TOLERANCE, 1.0, 0.0) for m in commute.values()]
        parts["commute"] = sum(vals) / len(vals)
    else:
        parts["commute"] = 0.3

    if listing.floor is None:
        parts["floor"] = 0.3
    else:
        parts["floor"] = {0: 0.0, 1: 0.1, 2: 0.3, 3: 0.6, 4: 0.8}.get(listing.floor, 1.0)

    pref_year = prefs.build_year_preferred_min
    if listing.build_year and pref_year:
        if listing.build_year >= pref_year:
            parts["build_year"] = 1.0
        elif listing.build_year >= pref_year - 10:
            parts["build_year"] = 0.5
        else:
            parts["build_year"] = 0.2
    else:
        parts["build_year"] = 1.0 if listing.market == Market.PRIMARY else 0.4

    budget = prefs.budget
    if listing.price is None:
        parts["price"] = 0.3
    elif listing.price <= budget.max_price:
        parts["price"] = _lerp(listing.price, budget.max_price * 0.8, budget.max_price, 1.0, 0.4)
    else:
        parts["price"] = _lerp(listing.price, budget.max_price, budget.hard_max, 0.4, 0.0)

    parts["elevator"] = {True: 1.0, False: 0.0, None: 0.5}[listing.has_elevator]

    if listing.area and prefs.area.min and prefs.area.max:
        parts["area"] = _lerp(listing.area, prefs.area.min, prefs.area.max, 0.5, 1.0)
    else:
        parts["area"] = 0.5

    parts["rooms"] = {None: 0.5, 2: 0.8}.get(listing.rooms, 1.0 if listing.rooms else 0.5)

    weights = {k: getattr(w, k) for k in parts}
    total = sum(weights.values()) or 1
    return round(100 * sum(parts[k] * weights[k] for k in parts) / total)
