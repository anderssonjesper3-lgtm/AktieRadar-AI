from datetime import datetime, timezone, timedelta
from verify_avanza import assess_identity, assess_quote


def test_identity_requires_matching_configured_id_and_name():
    company = {"name": "Saab B", "aliases": ["Saab AB", "Saab"]}
    rows = [{"orderBookId": "5401", "name": "Saab AB ser. B"}]
    status, match = assess_identity(company, "5401", rows)
    assert status == "ID_AND_NAME_MATCH"
    assert match["orderBookId"] == "5401"


def test_identity_does_not_accept_another_instrument_id():
    company = {"name": "Saab B", "aliases": ["Saab AB", "Saab"]}
    status, _ = assess_identity(company, "5401", [{"orderBookId": "9999", "name": "Saab AB ser. B"}])
    assert status == "ID_NOT_FOUND_IN_SEARCH"


def test_quote_is_live_only_with_explicit_provider_flag_and_fresh_timestamp():
    now = datetime.now(timezone.utc)
    raw = {"isRealTime": True, "timeOfLast": now.isoformat()}
    assert assess_quote(raw, now)["status"] == "LIVE"


def test_quote_without_realtime_flag_is_unknown():
    now = datetime.now(timezone.utc)
    assert assess_quote({"timeOfLast": now.isoformat()}, now)["status"] == "UNKNOWN"


def test_quote_explicitly_delayed_is_never_live():
    now = datetime.now(timezone.utc)
    assert assess_quote({"isRealTime": False, "timeOfLast": now.isoformat()}, now)["status"] == "DELAYED"


def test_stale_quote_is_not_live():
    now = datetime.now(timezone.utc)
    old = (now - timedelta(minutes=10)).isoformat()
    assert assess_quote({"isRealTime": True, "timeOfLast": old}, now)["status"] == "STALE"
