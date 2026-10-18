from homeseeker.preferences import load_preferences


def test_defaults_load(prefs):
    assert prefs.budget.max_price == 800_000
    assert "Wola" in prefs.locations.excluded


def test_stored_preferences_win(prefs):
    stored = prefs.model_dump(mode="json")
    stored["budget"]["max_price"] = 700_000
    assert load_preferences(stored).budget.max_price == 700_000


def test_invalid_stored_preferences_fall_back_to_defaults(prefs):
    assert load_preferences({"budget": "oops"}).budget.max_price == prefs.budget.max_price
