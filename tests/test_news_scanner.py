from datetime import datetime, timezone
from news_scanner import scan

XML = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
<title>Saab AB receives a new order</title>
<link>https://example.com/saab-order</link>
<pubDate>Sun, 22 Nov 2026 08:00:00 GMT</pubDate>
<description>Saab AB</description>
</item>
<item>
<title>Acconeer signs a contract</title>
<link>https://example.com/acconeer-contract</link>
<pubDate>Sun, 22 Nov 2026 08:01:00 GMT</pubDate>
<description>Acconeer</description>
</item>
</channel></rss>"""


def test_shared_feed_is_fetched_once_and_matched_to_relevant_issuers():
    companies = [
        {"name": "Saab B", "aliases": ["Saab AB", "Saab"], "feeds": ["https://rss.example/feed"]},
        {"name": "Acconeer", "aliases": ["Acconeer"], "feeds": ["https://rss.example/feed"]},
        {"name": "Ovzon", "aliases": ["Ovzon"], "feeds": ["https://rss.example/feed"]},
    ]
    calls = []
    def fetch(url):
        calls.append(url)
        return XML

    now = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)
    matches, failures = scan({"companies": companies}, now=now, fetch=fetch)

    assert calls == ["https://rss.example/feed"]
    assert failures == []
    assert {(m["company"], m["category"]) for m in matches} == {
        ("Saab B", "ORDER/AVTAL – GRANSKA"),
        ("Acconeer", "ORDER/AVTAL – GRANSKA"),
    }


def test_feed_failure_is_reported_without_silent_success():
    companies = [{"name": "Saab B", "aliases": ["Saab"], "feeds": ["https://rss.example/feed"]}]
    def fail(_url):
        raise TimeoutError("offline")

    matches, failures = scan({"companies": companies}, fetch=fail)
    assert matches == []
    assert failures == [("Saab B", "TimeoutError")]


def test_duplicate_feed_urls_are_deduplicated():
    companies = [
        {"name": "Saab B", "aliases": ["Saab"], "feeds": ["https://rss.example/feed", "https://rss.example/feed"]},
    ]
    calls = []
    scan({"companies": companies}, fetch=lambda url: calls.append(url) or b"<rss/>")
    assert calls == ["https://rss.example/feed"]
