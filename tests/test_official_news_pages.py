from datetime import datetime, timezone
import json
from pathlib import Path

from news_scanner import extract_items, load_config


def test_official_company_news_page_extracts_dated_release():
    html = b"""<!doctype html><html><body>
    <article>
      <time datetime="2026-11-20T08:00:00+00:00">20 Nov 2026 08:00</time>
      <a href="/newsroom/press-releases/saab-signs-new-agreement">
        Saab signs new agreement for advanced defence systems
      </a>
    </article>
    </body></html>"""
    items = extract_items(html, source_url="https://www.saab.com/newsroom")
    assert len(items) == 1
    assert "Saab signs" in items[0]["title"]
    assert items[0]["date"] == datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)
    assert items[0]["link"] == "https://www.saab.com/newsroom/press-releases/saab-signs-new-agreement"


def test_watchlist_uses_ten_company_specific_official_pages():
    config = load_config()
    companies = config["companies"]
    assert len(companies) == 10
    assert all(len(company["feeds"]) == 1 for company in companies)
    assert all(company.get("source_type") == "official_investor_relations" for company in companies)
    assert not any("api.news.eu.nasdaq.com/news/rss" in company["feeds"][0] for company in companies)
