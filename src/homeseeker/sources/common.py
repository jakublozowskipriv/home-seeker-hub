"""Shared value parsing for portal data."""

from __future__ import annotations

import re
from datetime import datetime

from .. import textparse
from ..models import Heating

FLOOR_WORDS = {
    "ground": 0,
    "ground_floor": 0,
    "parter": 0,
    "cellar": -1,
    "suterena": -1,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "above_tenth": 11,
    "floor_higher_10": 11,
    "higher_10": 11,
}
ROOM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "more": 11,
}


def to_float(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    s = re.sub(r"[^\d,.\-]", "", str(value)).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_int(value) -> int | None:
    f = to_float(value)
    return int(f) if f is not None else None


def parse_floor(value) -> int | None:
    """Handle 'floor_3', 'THIRD', 'ground_floor', '3', 'garret'."""
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
        if value is None:
            return None
    s = str(value).strip().lower()
    if s in FLOOR_WORDS:
        return FLOOR_WORDS[s]
    if s in ("garret", "poddasze"):
        return None  # top floor, number unknown
    if m := re.search(r"(\d+)", s):
        return int(m.group(1))
    return None


def parse_rooms(value) -> int | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ROOM_WORDS:
        return ROOM_WORDS[s]
    return to_int(s)


HEATING_CODES = {
    "urban": Heating.DISTRICT,
    "miejskie": Heating.DISTRICT,
    "district": Heating.DISTRICT,
    "gas": Heating.GAS,
    "gazowe": Heating.GAS,
    "electrical": Heating.ELECTRIC,
    "electric": Heating.ELECTRIC,
    "elektryczne": Heating.ELECTRIC,
    "heat_pump": Heating.HEAT_PUMP,
    "boiler_room": Heating.OTHER,
    "kotlownia": Heating.OTHER,
    "tiled_stove": Heating.OTHER,
    "other": Heating.OTHER,
}


def parse_heating(value) -> Heating | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if not value:
        return None
    return HEATING_CODES.get(textparse.fold(str(value)))


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
