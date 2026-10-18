from types import SimpleNamespace

from homeseeker.dedup import find_group, is_duplicate


def row(**kw):
    base = dict(
        id="otodom:9",
        group_id=None,
        rooms=2,
        area=45.3,
        price=705_000,
        floor=4,
        lat=52.4096,
        lon=16.9107,
        coords_approximate=False,
        district="Jeżyce",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_same_flat_on_other_portal(good_listing):
    assert is_duplicate(good_listing, row())
    assert find_group(good_listing, [row(group_id="otodom:5")]) == "otodom:5"


def test_different_flat(good_listing):
    assert not is_duplicate(good_listing, row(floor=2))
    assert not is_duplicate(good_listing, row(area=48))
    assert not is_duplicate(good_listing, row(lat=52.39, lon=16.95))
    assert find_group(good_listing, [row(floor=2)]) == good_listing.id


def test_falls_back_to_district_without_precise_coords(good_listing):
    assert is_duplicate(good_listing, row(lat=None, lon=None))
    assert not is_duplicate(good_listing, row(lat=None, lon=None, district="Wilda"))
