"""Human-readable (Polish) summaries of listings for messages and reports."""

from __future__ import annotations

from html import escape

from .. import geo
from ..evaluate import Evaluation, Verdict
from ..models import Heating, Market

SOURCE_NAMES = {"otodom": "Otodom", "olx": "OLX"}
HEATING_NAMES = {
    Heating.DISTRICT: "miejskie",
    Heating.GAS: "gazowe",
    Heating.ELECTRIC: "elektryczne",
    Heating.HEAT_PUMP: "pompa ciepła",
    Heating.OTHER: "inne",
}


def money(value: float | None) -> str:
    if value is None:
        return "?"
    return f"{value:,.0f}".replace(",", " ") + " zł"


def floor_text(floor: int | None, total: int | None) -> str:
    if floor is None:
        return "piętro ?"
    label = "parter" if floor == 0 else f"{floor}. p."
    return f"{label} z {total}" if total else label


def headline(listing) -> str:
    rooms = f"{listing.rooms} pok." if listing.rooms else "? pok."
    area = f"{listing.area:g} m²" if listing.area else "? m²"
    return f"{rooms}, {area}, {floor_text(listing.floor, listing.floors_total)}"


def facts(listing) -> list[str]:
    out = []
    if listing.build_year:
        out.append(f"bud. {listing.build_year}")
    if listing.market:
        out.append("pierwotny" if listing.market == Market.PRIMARY else "wtórny")
    if listing.completion_date:
        out.append(f"oddanie {listing.completion_date:%m.%Y}")
    if listing.has_balcony:
        out.append("balkon")
    if listing.has_elevator:
        out.append("winda")
    if listing.heating:
        out.append(f"ogrz. {HEATING_NAMES[listing.heating]}")
    return out


def listing_html(listing, ev: Evaluation, prefix: str = "🏠 Nowa oferta") -> str:
    lines = [f"{prefix}: <b>{escape(headline(listing))}</b>"]
    price = f"💰 <b>{money(listing.price)}</b>"
    if listing.price_per_m2:
        price += f" ({money(listing.price_per_m2)}/m²)"
    if ev.verdict == Verdict.NEGOTIABLE:
        price += " · do negocjacji"
    lines.append(price)
    place = listing.location_text or listing.district
    if place:
        lines.append(f"📍 {escape(place)}")
    if ev.commute:
        approx = " (szacunek)" if not listing.coords_approximate else " (przybl. lokalizacja)"
        lines.append(
            "🚋 " + " · ".join(f"~{m:.0f} min {escape(n)}" for n, m in ev.commute.items()) + approx
        )
    if f := facts(listing):
        lines.append("🏗 " + " · ".join(f))
    lines.append(f"⭐ Dopasowanie: <b>{ev.score}/100</b>")
    if ev.missing:
        lines.append("❓ Do sprawdzenia: " + escape(", ".join(ev.missing)))
    if ev.warnings:
        lines.append("⚠️ " + escape(", ".join(ev.warnings)))
    source = SOURCE_NAMES.get(listing.source, listing.source)
    links = [f'<a href="{escape(listing.url)}">{source}</a>']
    if listing.has_coords:
        links.append(f'<a href="{geo.google_maps_url(listing.lat, listing.lon)}">Google Maps</a>')
        links.append(f'<a href="{geo.apple_maps_url(listing.lat, listing.lon)}">Apple Maps</a>')
    lines.append("🔗 " + " · ".join(links))
    return "\n".join(lines)
