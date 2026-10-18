"""User search preferences: schema, defaults and loading."""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "config" / "preferences.default.yaml"


class Budget(BaseModel):
    max_price: float
    negotiable_max_price: float | None = None
    monthly_payment_min: float | None = None
    monthly_payment_max: float | None = None

    @property
    def hard_max(self) -> float:
        return max(self.max_price, self.negotiable_max_price or 0)


class Range(BaseModel):
    min: float | None = None
    max: float | None = None


class FloorPrefs(BaseModel):
    min: int = 0
    elevator_preferred: bool = True


class Locations(BaseModel):
    preferred: list[str] = Field(default_factory=list)
    allowed: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


class Destination(BaseModel):
    name: str
    lat: float
    lon: float


class Commute(BaseModel):
    max_minutes: float = 20


class Weights(BaseModel):
    location: float = 20
    commute: float = 20
    floor: float = 15
    build_year: float = 15
    price: float = 15
    elevator: float = 5
    area: float = 5
    rooms: float = 5


class Notifications(BaseModel):
    notify_review: bool = True
    notify_negotiable: bool = False
    max_per_run: int = 15  # above this, one digest message instead of single messages


class Preferences(BaseModel):
    city: str = "Poznań"
    budget: Budget
    area: Range = Field(default_factory=Range)
    rooms: Range = Field(default_factory=Range)
    floor: FloorPrefs = Field(default_factory=FloorPrefs)
    balcony_required: bool = False
    exclude_gas_heating: bool = False
    markets: list[Literal["primary", "secondary"]] = Field(
        default_factory=lambda: ["primary", "secondary"]
    )
    completion_deadline: date | None = None
    build_year_preferred_min: int | None = None
    locations: Locations = Field(default_factory=Locations)
    destinations: list[Destination] = Field(default_factory=list)
    commute: Commute = Field(default_factory=Commute)
    weights: Weights = Field(default_factory=Weights)
    notifications: Notifications = Field(default_factory=Notifications)


def parse_preferences(text: str) -> Preferences:
    return Preferences.model_validate(yaml.safe_load(text))


def load_preferences(stored: dict | None = None) -> Preferences:
    """Resolve preferences: stored in DB > HOMESEEKER_PREFERENCES > file > default file.

    Invalid preferences saved from the web app fall back to the defaults (logged) rather
    than stopping the scraper.
    """
    if stored:
        try:
            return Preferences.model_validate(stored)
        except ValidationError as e:
            log.error("Stored preferences are invalid, using defaults: %s", e)
    if text := os.environ.get("HOMESEEKER_PREFERENCES"):
        return parse_preferences(text)
    path = Path(os.environ.get("HOMESEEKER_PREFERENCES_FILE") or DEFAULT_FILE)
    return parse_preferences(path.read_text(encoding="utf-8"))
