"""Morizon (= Gratka) and Domiporta parsers, on payloads shaped like the live pages."""

# ruff: noqa: E501 - the HTML fixture keeps the portal's own line lengths

import base64
import json

from homeseeker.models import Market
from homeseeker.sources import domiporta, morizon
from homeseeker.sources.common import unflatten_devalue


def flatten(value):
    """Encode like Nuxt's devalue: every value in its own slot, referenced by index."""
    slots: list = []

    def put(v):
        index = len(slots)
        slots.append(None)
        if isinstance(v, dict):
            slots[index] = {k: put(x) for k, x in v.items()}
        elif isinstance(v, list):
            slots[index] = [put(x) for x in v]
        else:
            slots[index] = v
        return index

    put(value)
    return slots


PHOTO = base64.b64encode(b"https://d-gr.cdngr.pl/kadry/k/r/gr-ogl/94/b1/1.jpg").decode()
NODE = {
    "id": 2048392596,
    "idOnFrontend": "mzn2048392596",
    "url": "/oferta/sprzedaz-mieszkanie-poznan-jezyce-dabrowskiego-43m2-mzn2048392596",
    "advertisementText": "Sprzedam mieszkanie z balkonem",
    "area": "43",
    "price": {"amount": "475000.00", "currency": "PLN"},
    "numberOfRooms": "2 pokoje",
    "floorFormatted": "piętro 3/4",
    "location": {"location": ["wielkopolskie", "Poznań", "Jeżyce"], "street": "Dąbrowskiego"},
    "description": "<p>Mieszkanie z balkonem, ogrzewanie miejskie.</p>",
    "development": None,
    "photos": [{"id": PHOTO}],
    "addedAt": "2026-11-10T08:00:00+01:00",
}


def page(data) -> str:
    payload = json.dumps(flatten(data))
    return f'<script type="application/json" id="__NUXT_DATA__" data-ssr="true">{payload}</script>'


def test_devalue_round_trip():
    data = {"a": [1, {"b": "x"}], "c": None}
    assert unflatten_devalue(flatten(data)) == data


def test_morizon_search_node():
    data = {
        "pinia": {
            "listing": {
                "result": {"searchResult": {"properties": {"totalCount": 1, "nodes": [NODE]}}}
            }
        }
    }
    nodes = morizon.nuxt_data(page(data))["pinia"]["listing"]["result"]["searchResult"]
    listing = morizon.parse_node(nodes["properties"]["nodes"][0])
    assert listing.id == "morizon:2048392596"
    assert listing.url.startswith("https://www.morizon.pl/oferta/")
    assert (listing.price, listing.area, listing.rooms) == (475000, 43, 2)
    assert (listing.floor, listing.floors_total) == (3, 4)
    assert listing.district == "Jeżyce"
    assert listing.location_text == "Poznań, Jeżyce, Dąbrowskiego"
    assert listing.has_balcony is True and listing.heating is not None
    assert listing.images == ["https://d-gr.cdngr.pl/kadry/k/r/gr-ogl/94/b1/1.jpg"]
    assert not listing.details_fetched


def test_morizon_details_and_floor_text():
    listing = morizon.parse_node(NODE)
    prop = {
        "floor": 3,
        "floorFormatted": "piętro 3/4",
        "numberOfRoomsCount": 2,
        "area": "43",
        "marketType": "Rynek wtórny",
        "description": "<p>Blok z 1964 roku, winda.</p>",
        "location": {"map": {"center": {"latitude": 52.4157, "longitude": 16.8886}}},
        "buildingDetailedInformation": [],
        "equipments": ["balkon"],
    }
    morizon.apply_details(listing, prop)
    assert (listing.lat, listing.lon) == (52.4157, 16.8886)
    assert listing.market == Market.SECONDARY and listing.build_year == 1964
    assert listing.has_balcony is True and listing.details_fetched
    assert morizon.parse_floor_text("parter/5") == (0, 5)
    assert morizon.parse_floor_text("parter") == (0, None)


CARD = """<article class="sneakpeak " data-detail-id="156923854" >
<a title="mieszkanie na sprzeda&#x17C; 64m2 mieszkanie Pozna&#x144;, Marcelin, Le&#x15B;nych Skrzat&#xF3;w"
 href="/nieruchomosci/sprzedam-mieszkanie-trzypokojowe-poznan-marcelin-lesnych-skrzatow-64m2/156923854">
<img loading="lazy" class="sneakpeak__picture_cover " src="https://galeria.domiporta.pl/pictures/small/15/a.jpg" alt="" />
</a><div class="sneakpeak__priceRolled"><span class="sneakpeak__price_value"> 869&#xA0;000 z&#x142; </span></div>
<span class="sneakpeak__details_item sneakpeak__details_item--area" title="Powierzchnia"> 64,01&nbsp;<abbr>m<sup>2</sup></abbr></span>
<span class="sneakpeak__details_item sneakpeak__details_item--room" title="Liczba pokoi"> 3 </span>
</article>
<article class="sneakpeak " data-detail-id="660961" >
<a class="sneakpeak__button" href="/nowe/ogloszenie/naramowicka_100_poznan-winogrady_660961">Więcej</a>
</article>"""


def test_domiporta_cards_skip_developer_projects():
    cards = domiporta.cards(CARD)
    assert len(cards) == 2
    listings = [x for x in (domiporta.parse_card(i, c) for i, c in cards) if x]
    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "domiporta:156923854"
    assert (listing.price, listing.area, listing.rooms) == (869000, 64.01, 3)
    assert listing.location_text == "Poznań, Marcelin, Leśnych Skrzatów"
    assert listing.district == "Marcelin"
    assert listing.images == ["https://galeria.domiporta.pl/pictures/big/15/a.jpg"]


def test_domiporta_details_from_json_ld():
    listing = domiporta.parse_card(*domiporta.cards(CARD)[0])
    ld = {
        "@type": "Product",
        "description": "Mieszkanie z balkonem i windą, ogrzewanie miejskie.",
        "datePosted": "2026-11-12",
        "image": ["https://galeria.domiporta.pl/pictures/big/1.jpg"],
        "address": {"streetAddress": "Leśnych Skrzatów"},
        "offers": {"price": "869000", "priceCurrency": "PLN"},
        "itemOffered": {
            "yearBuilt": 2025,
            "floorLevel": "0",
            "geo": {"latitude": 52.4118772, "longitude": 16.850985},
        },
    }
    html = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    domiporta.apply_details(listing, domiporta._ld_listing(html))
    assert (listing.floor, listing.build_year) == (0, 2025)
    assert (listing.lat, listing.lon) == (52.4118772, 16.850985)
    assert listing.has_balcony is True and listing.has_elevator is True and listing.details_fetched


def test_domiporta_empty_page_before_the_last_marks_the_search_incomplete():
    class FakeHttp:
        def get(self, url):
            class R:
                text = (
                    CARD + '<a href="?PageNumber=3">3</a>'
                    if "PageNumber" not in url
                    else "<title>Chwileczkę…</title>"
                )

            return R()

    from homeseeker.preferences import load_preferences

    source = domiporta.DomiportaSource(FakeHttp())
    listings = list(source.search(load_preferences(), max_pages=10))
    assert len(listings) == 1
    assert source.search_complete is False and "no result cards" in source.errors[0]


def test_domiporta_cards_without_closing_tags():
    unclosed = CARD.replace("</article>", "")
    assert [i for i, _ in domiporta.cards(unclosed)] == [i for i, _ in domiporta.cards(CARD)]
    listings = [x for x in (domiporta.parse_card(i, c) for i, c in domiporta.cards(unclosed)) if x]
    assert len(listings) == 1 and listings[0].price
