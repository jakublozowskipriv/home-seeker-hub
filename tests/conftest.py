import pytest

from homeseeker.models import Heating, Listing, Market
from homeseeker.preferences import load_preferences


@pytest.fixture
def prefs(monkeypatch):
    monkeypatch.delenv("HOMESEEKER_PREFERENCES", raising=False)
    monkeypatch.delenv("HOMESEEKER_PREFERENCES_FILE", raising=False)
    return load_preferences()


@pytest.fixture
def good_listing():
    """A listing that should match the default preferences (Jeżyce, near the centre)."""
    return Listing(
        source="test",
        source_id="1",
        url="https://example.com/1",
        title="2 pokoje z balkonem",
        price=699_000,
        area=45.5,
        rooms=2,
        floor=4,
        floors_total=5,
        build_year=2019,
        market=Market.SECONDARY,
        has_balcony=True,
        has_elevator=True,
        heating=Heating.DISTRICT,
        district="Jeżyce",
        location_text="Poznań, Jeżyce, ul. Kościelna",
        lat=52.4095,
        lon=16.9105,
        details_fetched=True,
    )
