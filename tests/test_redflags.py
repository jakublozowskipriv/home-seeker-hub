from homeseeker.redflags import find_red_flags


def texts(*args):
    return [f["text"].split(" – ")[0] for f in find_red_flags(*args)]


def test_typical_traps():
    assert texts("Sprzedam udział 1/2 w mieszkaniu, tylko za gotówkę.") == [
        "sprzedaż udziału, nie całego mieszkania",
        "tylko za gotówkę",
    ]
    assert texts("Licytacja komornicza, lokal z lokatorem.") == [
        "licytacja / komornik",
        "sprzedaż z lokatorem / najemcą",
    ]
    assert texts("Aparthotel, apartament inwestycyjny w systemie condo") == [
        "lokal inwestycyjny / hotelowy (condo)"
    ]
    assert texts("Mieszkanie bez księgi wieczystej (spółdzielcze).") == ["brak księgi wieczystej"]


def test_negations_and_harmless_mentions():
    assert texts("Mieszkanie bez zadłużeń, nie wymaga remontu.") == []
    assert texts("Na parterze budynku lokale usługowe, obok przedszkole.") == []
    assert texts("Stan prawny: pełna własność, księga wieczysta założona, brak obciążeń.") == []


def test_info_level():
    flags = find_red_flags("Grunt w użytkowaniu wieczystym, mieszkanie do remontu.")
    assert [f["level"] for f in flags] == ["info", "info"]
