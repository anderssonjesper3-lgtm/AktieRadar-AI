from datetime import datetime, timezone
from news_history import merge_history, latest_for_company


def test_merge_keeps_newer_headline_and_retains_older_news():
    old = {"id": "old", "company": "PowerCell", "title": "Older",
           "published": datetime(2026, 11, 10, tzinfo=timezone.utc)}
    new = {"id": "new", "company": "PowerCell", "title": "Newer",
           "published": datetime(2026, 11, 20, tzinfo=timezone.utc)}
    rows = merge_history([old], [new])
    assert [row["id"] for row in rows] == ["new", "old"]
    assert latest_for_company(rows, "PowerCell")["title"] == "Newer"


def test_merge_deduplicates_same_news_item():
    first = {"id": "same", "title": "Original", "published": "2026-11-20T07:00:00+00:00"}
    revised = {"id": "same", "title": "Updated", "published": "2026-11-20T07:00:00+00:00"}
    rows = merge_history([first], [revised])
    assert len(rows) == 1
    assert rows[0]["title"] == "Updated"


def test_history_is_bounded():
    rows = [{"id": str(i), "published": f"2026-11-{(i % 20) + 1:02d}T07:00:00+00:00"}
            for i in range(20)]
    assert len(merge_history([], rows, max_items=5)) == 5
