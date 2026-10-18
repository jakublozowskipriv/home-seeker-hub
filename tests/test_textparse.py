from datetime import date

import pytest

from homeseeker import textparse as tp
from homeseeker.models import Heating, Ownership


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Mieszkanie z przestronnym balkonem od południa", True),
        ("Do mieszkania przynależy loggia", True),
        ("Duży taras", True),
        ("Niestety brak balkonu", False),
        ("Mieszkanie bez balkonu, za to z piwnicą", False),
        ("Słoneczne mieszkanie, piwnica", None),
        ("", None),
    ],
)
def test_detect_balcony(text, expected):
    assert tp.detect_balcony(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Ogrzewanie miejskie, kuchenka gazowa", Heating.DISTRICT),
        ("Ogrzewanie gazowe z kotła dwufunkcyjnego", Heating.GAS),
        ("W łazience piecyk gazowy", Heating.GAS),
        ("C.O. gazowe", Heating.GAS),
        ("Budynek podłączony do sieci ciepłowniczej Veolia", Heating.DISTRICT),
        ("Ogrzewanie miejskie, dawniej piec gazowy", None),
        ("Pompa ciepła i fotowoltaika", Heating.HEAT_PUMP),
        ("Ładne mieszkanie", None),
    ],
)
def test_detect_heating(text, expected):
    assert tp.detect_heating(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Mieszkanie na 3 piętrze z 5", (3, 5)),
        ("położone na 4/6 p.", (4, 6)),
        ("Piętro: 2", (2, None)),
        ("Mieszkanie na parterze z ogródkiem", (0, None)),
        ("na trzecim piętrze", (3, None)),
        ("Bez informacji", (None, None)),
    ],
)
def test_detect_floor(text, expected):
    assert tp.detect_floor(text) == expected


def test_detect_build_year():
    assert tp.detect_build_year("Rok budowy: 2018") == 2018
    assert tp.detect_build_year("Budynek wybudowany w 2016 roku") == 2016
    assert tp.detect_build_year("Kamienica z 1905 r.") == 1905
    assert tp.detect_build_year("Cena 2018 zł/m2") is None


def test_detect_elevator():
    assert tp.detect_elevator("W budynku jest winda") is True
    assert tp.detect_elevator("Budynek bez windy") is False
    assert tp.detect_elevator("Duża kuchnia") is None


def test_detect_ownership():
    assert tp.detect_ownership("Spółdzielcze własnościowe prawo") == Ownership.COOPERATIVE
    assert tp.detect_ownership("Pełna własność, księga wieczysta") == Ownership.FULL


def test_detect_completion():
    assert tp.detect_completion("Termin oddania: IV kw. 2027") == date(2027, 12, 31)
    assert tp.detect_completion("Planowane oddanie inwestycji w II kwartale 2028") == date(
        2028, 6, 30
    )
    assert tp.detect_completion("Zakończenie budowy 2027") == date(2027, 12, 31)


def test_strip_html_and_fold():
    assert tp.strip_html("<p>Ładny&nbsp;<b>balkon</b></p>") == "Ładny\xa0 balkon"
    assert tp.fold("Święty ŁAZARZ") == "swiety lazarz"
