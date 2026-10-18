"""Parsers against synthetic payloads shaped like the portals' JSON.

These document the structure the parsers expect; `homeseeker probe <source>` prints the
real structure when a portal changes.
"""

from homeseeker.models import Heating, Market, Ownership
from homeseeker.sources import olx, otodom

OTODOM_ITEM = {
    "id": 65000001,
    "title": "Nowoczesne 2 pokoje z balkonem",
    "slug": "nowoczesne-2-pokoje-z-balkonem-ID4abcd",
    "estate": "FLAT",
    "transaction": "SELL",
    "location": {
        "address": {"street": {"name": "ul. Kościelna", "number": ""}, "city": {"name": "Poznań"}},
        "reverseGeocoding": {
            "locations": [
                {"fullName": "Poznań, wielkopolskie", "locationLevel": "city", "name": "Poznań"},
                {"fullName": "Jeżyce, Poznań", "locationLevel": "district", "name": "Jeżyce"},
            ]
        },
    },
    "images": [{"medium": "https://img/m.jpg", "large": "https://img/l.jpg"}],
    "isPrivateOwner": False,
    "agency": {"name": "Biuro XYZ"},
    "totalPrice": {"value": 699000, "currency": "PLN"},
    "areaInSquareMeters": 45.5,
    "roomsNumber": "TWO",
    "floorNumber": "FOURTH",
    "createdAtFirst": "2026-10-10T10:00:00+00:00",
    "tags": [{"value": "BALCONY", "weight": 35}, {"value": "LIFT", "weight": 10}],
    "rentPrice": {"value": 650, "currency": "PLN"},
    "openDays": None,
}

OTODOM_AD = {
    "id": 65000001,
    "title": "Nowoczesne 2 pokoje z balkonem",
    "market": "SECONDARY",
    "description": "<p>Mieszkanie w bloku z 2019 r.</p><p>Ogrzewanie miejskie.</p>",
    "attributes": {
        "build_year": "2019",
        "building_floors_num": "5",
        "building_ownership": "full_ownership",
        "extras_types": ["balcony", "lift", "basement"],
        "floor_no": "floor_4",
        "heating": "urban",
        "m": "45.5",
        "market": "secondary",
        "rooms_num": "2",
    },
    "target": {
        "Area": "45.5",
        "Build_year": "2019",
        "Building_floors_num": "5",
        "Building_ownership": ["full_ownership"],
        "Extras_types": ["balcony", "lift", "basement"],
        "Floor_no": ["floor_4"],
        "Heating": ["urban"],
        "MarketType": "secondary",
        "Price": 699000,
        "Rooms_num": ["2"],
    },
    "location": {
        "coordinates": {"latitude": 52.4095, "longitude": 16.9105},
        "mapDetails": {"radius": 500, "zoom": 13},
        "address": {"city": {"name": "Poznań"}, "district": {"name": "Jeżyce"}},
    },
    "images": [{"thumbnail": "t", "medium": "m", "large": "https://img/large.jpg"}],
}


def test_otodom_search_item():
    listing = otodom.parse_search_item(OTODOM_ITEM)
    assert listing.id == "otodom:65000001"
    assert listing.url.endswith("/pl/oferta/nowoczesne-2-pokoje-z-balkonem-ID4abcd")
    assert (listing.price, listing.area, listing.rooms, listing.floor) == (699000, 45.5, 2, 4)
    assert listing.district == "Jeżyce"
    assert "Kościelna" in listing.location_text
    assert listing.images == ["https://img/l.jpg"]
    assert listing.has_balcony is True and listing.has_elevator is True
    assert listing.published_at.year == 2026
    assert listing.raw["rent"] == 650
    assert otodom.parse_search_item({**OTODOM_ITEM, "estate": "INVESTMENT"}) is None


def test_otodom_details():
    listing = otodom.apply_details(otodom.parse_search_item(OTODOM_ITEM), OTODOM_AD)
    assert listing.details_fetched
    assert listing.build_year == 2019
    assert listing.floors_total == 5
    assert listing.market == Market.SECONDARY
    assert listing.has_balcony is True and listing.has_elevator is True
    assert listing.heating == Heating.DISTRICT
    assert listing.ownership == Ownership.FULL
    assert (listing.lat, listing.lon) == (52.4095, 16.9105)
    assert listing.coords_approximate is False  # 500 m circle is precise enough
    assert listing.images == ["https://img/large.jpg"]
    assert listing.raw["attributes"]["heating"] == "urban"


def test_otodom_details_attributes_only_and_primary_completion():
    ad = {
        **OTODOM_AD,
        "target": {},
        "market": "PRIMARY",
        "attributes": {
            **OTODOM_AD["attributes"],
            "market": "primary",
            "free_from": "2027-09-30",
            "heating": "gas",
        },
        "location": {
            "coordinates": {"latitude": 52.4, "longitude": 16.9},
            "mapDetails": {"radius": 5000},
        },
    }
    listing = otodom.apply_details(otodom.parse_search_item(OTODOM_ITEM), ad)
    assert listing.market == Market.PRIMARY
    assert listing.completion_date.isoformat() == "2027-09-30"
    assert listing.heating == Heating.GAS
    assert listing.coords_approximate is True
    assert listing.floor == 4 and listing.build_year == 2019


def test_otodom_extras_without_balcony_means_no_balcony():
    ad = {
        **OTODOM_AD,
        "attributes": {**OTODOM_AD["attributes"], "extras_types": ["lift"]},
        "target": {**OTODOM_AD["target"], "Extras_types": ["lift"]},
    }
    item = {**OTODOM_ITEM, "tags": []}
    listing = otodom.apply_details(otodom.parse_search_item(item), ad)
    assert listing.has_balcony is False


def test_otodom_search_url(prefs):
    url = otodom.search_url(prefs, 2)
    assert "priceMax=840000" in url and "areaMin=38" in url and "page=2" in url
    assert "roomsNumber=%5BTWO%2CTHREE%5D" in url


OLX_OFFER = {
    "id": 912345678,
    "url": "https://www.olx.pl/d/oferta/mieszkanie-wilda-CID3-IDabc.html",
    "title": "Mieszkanie 2 pokoje Wilda, balkon",
    "description": "Sprzedam mieszkanie na 3 piętrze z 4, budynek z 2017 roku. "
    "Ogrzewanie miejskie, winda.",
    "created_time": "2026-10-15T08:00:00+02:00",
    "business": False,
    "user": {"name": "Jan"},
    "params": [
        {"key": "price", "type": "price", "value": {"value": 640000, "currency": "PLN"}},
        {"key": "m", "type": "input", "value": {"key": "44", "label": "44 m²"}},
        {"key": "rooms", "type": "select", "value": {"key": "two", "label": "2 pokoje"}},
        {"key": "floor_select", "type": "select", "value": {"key": "floor_3", "label": "3"}},
        {"key": "market", "type": "select", "value": {"key": "secondary", "label": "Wtórny"}},
    ],
    "map": {"lat": 52.392, "lon": 16.925, "radius": 0, "show_detailed": True},
    "location": {"city": {"name": "Poznań"}, "district": {"name": "Wilda"}},
    "photos": [{"link": "https://img/olx;s={width}x{height}"}],
}


def test_olx_offer():
    listing = olx.parse_offer(OLX_OFFER)
    assert listing.id == "olx:912345678"
    assert (listing.price, listing.area, listing.rooms, listing.floor) == (640000, 44, 2, 3)
    assert listing.market == Market.SECONDARY
    assert listing.has_balcony is True and listing.has_elevator is True
    assert listing.heating == Heating.DISTRICT
    assert listing.build_year == 2017
    assert listing.is_private_owner is True
    assert listing.coords_approximate is False
    assert listing.images == ["https://img/olx;s=800x600"]
    assert listing.location_text == "Poznań, Wilda"


def test_olx_skips_otodom_crossposts_and_flags_approx_coords():
    assert olx.parse_offer({**OLX_OFFER, "url": "https://www.otodom.pl/pl/oferta/x"}) is None
    approx = olx.parse_offer({**OLX_OFFER, "map": {"lat": 52.4, "lon": 16.9, "radius": 2}})
    assert approx.coords_approximate is True


def test_otodom_investment_units():
    investment = {
        "id": 68238735,
        "slug": "unii-lubelskiej-ID4Ck0L",
        "title": "Unii Lubelskiej",
        "estate": "INVESTMENT",
        "investmentEstimatedDelivery": {"quarter": 3, "year": 2028},
        "investmentState": "IN_BUILDING",
        "investmentUnitsNumber": 284,
        "location": OTODOM_ITEM["location"],
        "relatedAds": [
            {**OTODOM_ITEM, "id": 1, "slug": "unit-1-ID1", "location": None},
            {**OTODOM_ITEM, "id": 2, "slug": "unit-2-ID2"},
        ],
    }
    units = otodom.parse_investment_units(investment)
    assert [u.id for u in units] == ["otodom:1", "otodom:2"]
    first = units[0]
    assert first.market == Market.PRIMARY
    assert first.completion_date.isoformat() == "2028-09-30"
    assert first.district == "Jeżyce"  # taken from the investment
    assert first.raw["investment"]["url"].endswith("/pl/inwestycja/unii-lubelskiej-ID4Ck0L")
    assert otodom.parse_search_item(investment) is None
