"""Rule-based extraction of apartment features from free-text descriptions."""

from __future__ import annotations

import html
import re
import unicodedata
from datetime import date

from .models import Heating, Ownership

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<(br|/p|/li|/div)[^>]*>", "\n", text, flags=re.I)
    return html.unescape(_TAG_RE.sub(" ", text)).strip()


def fold(text: str | None) -> str:
    """Lowercase, strip Polish diacritics and collapse whitespace."""
    if not text:
        return ""
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _WS_RE.sub(" ", text.lower()).strip()


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


_NO_BALCONY = [r"\bbez balkon", r"\bbrak balkon", r"\bnie (ma|posiada) balkon"]
_BALCONY = [r"\bbalkon", r"\blogi[ai]", r"\blodzi[ai]", r"\btaras", r"\bloggi"]


def detect_balcony(text: str | None) -> bool | None:
    t = fold(text)
    if not t:
        return None
    if _any(_NO_BALCONY, t):
        return False
    if _any(_BALCONY, t):
        return True
    return None


_GAS_HEATING = [
    r"\bpiec(yk|a|em)? (gazow|dwufunkcyjn|co\b)",
    r"\bkocio\w* (gazow|dwufunkcyjn|kondensacyjn)",
    r"\bogrzewani\w* (jest |mieszkania )?(:\s*)?(gazow|z pieca|z kotla|indywidualn\w* gazow)",
    r"\bgazow\w* ogrzewani",
    r"\bc\.? ?o\.? (i c\.? ?w\.? ?u\.? )?(gazow|z pieca|z kotla)",
    r"\bogrzewani\w*:?\s*gaz\b",
]
_DISTRICT_HEATING = [
    r"\bogrzewani\w* (jest )?(:\s*)?(miejsk|z sieci|sieciow|z mpec|z veolii|centraln\w* miejsk)",
    r"\bmiejsk\w* (ogrzewani|siec\w* cieplown|c\.? ?o\b)",
    r"\bsiec\w* cieplown",
    r"\bmpec\b",
    r"\bveolia\b",
    r"\bwezel cieplown",
]
_HEAT_PUMP = [r"\bpomp\w* ciepla"]
_ELECTRIC = [r"\bogrzewani\w* (:\s*)?elektryczn"]


def detect_heating(text: str | None) -> Heating | None:
    t = fold(text)
    if not t:
        return None
    gas = _any(_GAS_HEATING, t)
    district = _any(_DISTRICT_HEATING, t)
    if gas and district:
        return None  # ambiguous, needs a human look
    if gas:
        return Heating.GAS
    if district:
        return Heating.DISTRICT
    if _any(_HEAT_PUMP, t):
        return Heating.HEAT_PUMP
    if _any(_ELECTRIC, t):
        return Heating.ELECTRIC
    return None


def detect_elevator(text: str | None) -> bool | None:
    t = fold(text)
    if not t:
        return None
    if _any([r"\bbez wind", r"\bbrak wind", r"\bnie ma wind"], t):
        return False
    if _any([r"\bwind(a|y|e|ą|a osobow)", r"\bwinda\b", r"\bdzwig osobow"], t):
        return True
    return None


_YEAR = r"(18[5-9]\d|19\d\d|20[0-3]\d)"


def detect_build_year(text: str | None) -> int | None:
    t = fold(text)
    patterns = [
        rf"\brok\w* budowy:?\s*{_YEAR}",
        rf"\bwybudowan\w* (w )?(roku |r\. ?)?{_YEAR}",
        rf"\b(budyn|kamienic|blok|apartamentow)\w* z (roku |r\. ?)?{_YEAR}",
        rf"\boddan\w* do uzytku (w )?(roku |r\. ?)?{_YEAR}",
    ]
    for p in patterns:
        if m := re.search(p, t):
            return int(m.groups()[-1])
    return None


def detect_ownership(text: str | None) -> Ownership | None:
    t = fold(text)
    if re.search(r"\bspoldzielcz\w* (wlasnosciow|prawo)", t):
        return Ownership.COOPERATIVE
    if re.search(r"\b(pelna|odrebna) wlasnosc|\bodrebn\w* wlasnosc", t):
        return Ownership.FULL
    return None


_ORDINALS = {
    "parter": 0,
    "pierwsz": 1,
    "drugi": 2,
    "drugie": 2,
    "trzeci": 3,
    "czwart": 4,
    "piat": 5,
    "szost": 6,
    "siodm": 7,
    "osm": 8,
    "dziewiat": 9,
    "dziesiat": 10,
}


def detect_floor(text: str | None) -> tuple[int | None, int | None]:
    """Return (floor, floors_total) mentioned in text, e.g. '3 piętro z 5' or '3/5'."""
    t = fold(text)
    if not t:
        return None, None
    if m := re.search(r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*(p\b|pietr)", t):
        return int(m.group(1)), int(m.group(2))
    floor_re = r"\b(\d{1,2})\.?\s*(-?te|-?ym)?\s*pietr\w*(\s*(z|na|w budynku)\s*(\d{1,2}))?"
    if m := re.search(floor_re, t):
        total = int(m.group(5)) if m.group(5) else None
        return int(m.group(1)), total
    if m := re.search(r"\bpietro:?\s*(\d{1,2})", t):
        return int(m.group(1)), None
    if m := re.search(r"\b(na )?parterze\b|\bparter\b", t):
        return 0, None
    for word, n in _ORDINALS.items():
        if word != "parter" and re.search(rf"\b(na )?{word}\w* pietrz?", t):
            return n, None
    return None, None


_QUARTERS = {"i": 3, "1": 3, "ii": 6, "2": 6, "iii": 9, "3": 9, "iv": 12, "4": 12}


def _quarter_end(q: str, year: int) -> date:
    month = _QUARTERS[q]
    return date(year, month, 30 if month in (6, 9) else 31)


def detect_completion(text: str | None) -> date | None:
    """Planned completion date for primary-market listings ('oddanie IV kw. 2027')."""
    t = fold(text)
    ctx = r"(termin oddania|oddanie|zakonczenie budowy|odbior|przekazanie kluczy|gotowe)"
    quarter = r"\b(iv|iii|ii|i|[1-4])\s*(kw|kwartal)\w*\.?\s*(20[2-3]\d)"
    if m := re.search(rf"{ctx}\w*[^.\n]{{0,25}}?{quarter}", t):
        return _quarter_end(m.group(2), int(m.group(4)))
    if m := re.search(rf"{ctx}\w*[^.\n]{{0,25}}?\b(20[2-3]\d)", t):
        return date(int(m.group(2)), 12, 31)
    return None


# Księga wieczysta: court code (e.g. PO1P for Poznań), 8 digits, check digit.
_LAND_REGISTER_RE = re.compile(r"\b([A-Z]{2}\d[A-Z])\s*/\s*(\d{8})\s*/\s*(\d)\b", re.I)


def find_land_register(text: str | None) -> str | None:
    m = _LAND_REGISTER_RE.search(text or "")
    return f"{m.group(1).upper()}/{m.group(2)}/{m.group(3)}" if m else None
