from datetime import date

from homeseeker import districts
from homeseeker.evaluate import Verdict, evaluate
from homeseeker.models import Heating, Market


def test_good_listing_matches(prefs, good_listing):
    ev = evaluate(good_listing, prefs)
    assert ev.verdict == Verdict.MATCH, ev
    assert ev.location_category == "preferred"
    assert ev.score >= 75
    assert set(ev.commute) == {d.name for d in prefs.destinations}


def test_low_floor_rejected(prefs, good_listing):
    good_listing.floor = 1
    ev = evaluate(good_listing, prefs)
    assert ev.verdict == Verdict.REJECTED
    assert "za nisko (1. p.)" in ev.rejections


def test_ground_floor_and_gas_rejected(prefs, good_listing):
    good_listing.floor = 0
    good_listing.heating = Heating.GAS
    ev = evaluate(good_listing, prefs)
    assert ev.rejections == ["parter", "ogrzewanie gazowe"]


def test_price_band(prefs, good_listing):
    good_listing.price = 820_000
    assert evaluate(good_listing, prefs).verdict == Verdict.NEGOTIABLE
    good_listing.price = 850_000
    assert evaluate(good_listing, prefs).verdict == Verdict.REJECTED


def test_studio_rejected(prefs, good_listing):
    good_listing.rooms = 1
    assert evaluate(good_listing, prefs).verdict == Verdict.REJECTED


def test_missing_balcony_needs_review(prefs, good_listing):
    good_listing.has_balcony = None
    ev = evaluate(good_listing, prefs)
    assert ev.verdict == Verdict.REVIEW
    assert ev.missing == ["balkon"]


def test_far_away_rejected(prefs, good_listing):
    good_listing.lat, good_listing.lon = 52.4700, 16.9300  # far north (Morasko area)
    good_listing.district, good_listing.location_text = None, "Poznań"
    ev = evaluate(good_listing, prefs)
    assert ev.verdict == Verdict.REJECTED
    assert any(r.startswith("za daleko") for r in ev.rejections)


def test_far_with_approximate_coords_only_warns(prefs, good_listing):
    good_listing.lat, good_listing.lon = 52.4700, 16.9300
    good_listing.coords_approximate = True
    ev = evaluate(good_listing, prefs)
    assert ev.verdict == Verdict.MATCH
    assert ev.warnings


def test_excluded_estate_wins_over_district(prefs, good_listing):
    good_listing.location_text = "Poznań, Jeżyce, Strzeszyn"
    ev = evaluate(good_listing, prefs)
    assert "lokalizacja: Strzeszyn" in ev.rejections


def test_primary_market_completion_deadline(prefs, good_listing):
    good_listing.market = Market.PRIMARY
    good_listing.completion_date = date(2028, 12, 31)
    assert evaluate(good_listing, prefs).verdict == Verdict.REJECTED
    good_listing.completion_date = date(2027, 12, 31)
    assert evaluate(good_listing, prefs).verdict == Verdict.MATCH


def test_higher_floor_scores_better(prefs, good_listing):
    good_listing.floor = 2
    low = evaluate(good_listing, prefs).score
    good_listing.floor = 6
    assert evaluate(good_listing, prefs).score > low


def test_district_aliases():
    assert districts.classify("Poznań, Grunwald, Św. Łazarz", ["Łazarz"], [], []) == (
        "preferred",
        "Łazarz",
    )
    assert districts.classify("Poznań, Wildeczki", ["Wilda"], [], []) == (None, None)


def test_mortgage_payment_and_red_flags(prefs, good_listing):
    good_listing.price = 600_000
    good_listing.description = "Sprzedaż z najemcą, umowa do końca roku."
    ev = evaluate(good_listing, prefs)
    assert ev.monthly_payment == 3034  # 480 000 zł loan, 6.5%, 30 years
    assert [f["level"] for f in ev.red_flags] == ["high"]
    assert ev.verdict == Verdict.MATCH  # flags inform, they do not reject
