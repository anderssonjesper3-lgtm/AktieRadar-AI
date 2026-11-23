from news_analysis import analyze_news, analyze_analyst_revision

SAAB = {"name": "Saab", "annual_revenue_sek": None}

def test_saab_target_raise_is_positive_but_not_recommendation_upgrade():
    a = analyze_news({"title": "Kepler höjer riktkursen för Saab från 570 till 615 kronor, upprepar behåll", "description": ""}, SAAB)
    assert a["view"] == "POSITIV"
    assert a["analyst_revision"]["target_changed"]
    assert not a["analyst_revision"]["recommendation_changed"]

def test_lower_target_is_negative():
    a = analyze_news({"title": "Bank sänker riktkurs för Saab till 550 kronor", "description": ""}, SAAB)
    assert a["view"] == "NEGATIV"

def test_unchanged_target_is_neutral():
    a = analyze_news({"title": "Bank upprepar riktkurs 615 kronor för Saab", "description": ""}, SAAB)
    assert a["view"] == "NEUTRAL / OTILLRÄCKLIG INFORMATION"

def test_recommendation_upgrade_is_positive():
    assert analyze_analyst_revision("Bank uppgraderar rekommendation till köp")["direction"] == "POSITIV"

def test_mixed_analyst_changes_are_unclear():
    assert analyze_analyst_revision("Bank höjer riktkurs men sänker rekommendation")["direction"] == "OKLAR"
