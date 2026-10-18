"""Warning signs in listing descriptions: legal or financial traps worth checking before a
viewing. Rule-based (free); a match is a reason to ask, not to reject.
"""

from __future__ import annotations

import re

from .textparse import fold

HIGH, INFO = "high", "info"

# (level, message, patterns, patterns that cancel the match, e.g. "bez zadłużeń")
RULES: list[tuple[str, str, list[str], list[str]]] = [
    (
        HIGH,
        "licytacja / komornik – inne zasady zakupu, ryzyko lokatorów i długów",
        [r"\blicytac", r"\bkomornik", r"\begzekuc"],
        [],
    ),
    (
        HIGH,
        "sprzedaż udziału, nie całego mieszkania",
        [
            r"\budzia\w* (w|we) (wysokosci|mieszkaniu|lokalu|nieruchomosci)",
            r"\budzial \d+/\d+",
            r"\bsprzeda\w* udzia",
        ],
        [],
    ),
    (
        HIGH,
        "tylko za gotówkę – kredyt może być niemożliwy",
        [
            r"\btylko (za )?gotowk",
            r"\bwylacznie (za )?gotowk",
            r"\bbez mozliwosci kredyt",
            r"\bnie (nadaje sie|jest mozliw\w*) (pod |na |do )?kredyt",
        ],
        [],
    ),
    (
        HIGH,
        "brak księgi wieczystej",
        [
            r"\bbez (ksiegi wieczystej|kw)\b",
            r"\bbrak (ksiegi wieczystej|kw)\b",
            r"\bnie (ma|posiada) (ksiegi wieczystej|kw)\b",
        ],
        [],
    ),
    (
        HIGH,
        "lokal użytkowy, nie mieszkalny – inny kredyt i podatki",
        [r"\blokal\w* uzytkow", r"\b(jest|to|sprzedam|sprzedaz\w*|oferuj\w*) lokal\w* uslugow"],
        [],
    ),
    (
        HIGH,
        "lokal inwestycyjny / hotelowy (condo) – zwykle bez kredytu mieszkaniowego",
        [r"\baparthotel", r"\bcondo\b", r"\bapartament\w* inwestycyjn", r"\bpokoj\w* hotelow"],
        [],
    ),
    (
        HIGH,
        "sprzedaż z lokatorem / najemcą",
        [r"\bz (lokatorem|lokatorami|najemc\w*)\b", r"\bwynajet\w* do\b", r"\bobecnie wynajmowan"],
        [],
    ),
    (
        HIGH,
        "wzmianka o zadłużeniu lub hipotece",
        [r"\bzadluz", r"\bhipotek\w* do (splaty|przejecia)", r"\bobciazon"],
        [
            r"\bbez (zadluz|obciaz)",
            r"\bbrak (zadluz|obciaz)",
            r"\bwolne od (zadluz|obciaz)",
            r"\bnie(obciazon| ma (zadluz|obciaz))",
        ],
    ),
    (
        HIGH,
        "dożywocie / prawo zamieszkania osoby trzeciej",
        [r"\bdozywoci", r"\bprawo (do )?(dozywotniego )?zamieszkani"],
        [],
    ),
    (
        HIGH,
        "TBS / partycypacja – brak pełnej własności",
        [r"\btbs\b", r"\bpartycypac"],
        [],
    ),
    (INFO, "służebność – sprawdź w księdze wieczystej", [r"\bsluzebnos"], []),
    (INFO, "suterena / półpiętro piwniczne", [r"\bsuteren", r"\bpiwniczn\w* mieszkan"], []),
    (
        INFO,
        "użytkowanie wieczyste gruntu – roczna opłata",
        [r"\buzytkowani\w* wieczyst"],
        [],
    ),
    (
        INFO,
        "do generalnego remontu – doliczyć koszt",
        [r"\bdo (generalnego|kapitalnego|calkowitego) remontu", r"\bdo remontu\b"],
        [r"\bnie (wymaga|potrzebuje) remontu", r"\bbez (koniecznosci )?remontu"],
    ),
]

_COMPILED = [
    (level, message, [re.compile(p) for p in pats], [re.compile(p) for p in negs])
    for level, message, pats, negs in RULES
]


def find_red_flags(*texts: str | None) -> list[dict[str, str]]:
    text = fold(" ".join(t for t in texts if t))
    if not text:
        return []
    out = []
    for level, message, patterns, negations in _COMPILED:
        if any(p.search(text) for p in patterns) and not any(n.search(text) for n in negations):
            out.append({"level": level, "text": message})
    return out
