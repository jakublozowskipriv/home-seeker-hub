"""Normalized listing model shared by all sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class Market(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class Heating(StrEnum):
    DISTRICT = "district"  # miejskie / sieć ciepłownicza
    GAS = "gas"  # piec / kocioł gazowy w mieszkaniu
    ELECTRIC = "electric"
    HEAT_PUMP = "heat_pump"
    OTHER = "other"


class Ownership(StrEnum):
    FULL = "full"  # pełna własność
    COOPERATIVE = "cooperative"  # spółdzielcze własnościowe
    OTHER = "other"


@dataclass
class Listing:
    source: str
    source_id: str
    url: str
    title: str = ""
    price: float | None = None
    area: float | None = None
    rooms: int | None = None
    floor: int | None = None  # 0 = parter
    floors_total: int | None = None
    build_year: int | None = None
    market: Market | None = None
    has_balcony: bool | None = None
    has_elevator: bool | None = None
    heating: Heating | None = None
    ownership: Ownership | None = None
    completion_date: date | None = None
    district: str | None = None
    location_text: str | None = None
    lat: float | None = None
    lon: float | None = None
    coords_approximate: bool = False  # e.g. OLX shows only an area circle
    description: str | None = None
    images: list[str] = field(default_factory=list)
    is_private_owner: bool | None = None
    agency: str | None = None
    published_at: datetime | None = None
    details_fetched: bool = False
    raw: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def price_per_m2(self) -> float | None:
        if self.price and self.area:
            return round(self.price / self.area)
        return None

    @property
    def has_coords(self) -> bool:
        return self.lat is not None and self.lon is not None
