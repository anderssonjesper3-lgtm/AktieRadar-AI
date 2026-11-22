from news_scanner import extract_items

HTML = b"""<html><body>
<div>2026-11-19 14:00:00</div>
<a href="/a/scandinavian-astor-group/astor-group-subsidiary-oscilion-to-develop-hpm">Astor Group subsidiary Oscilion to develop HPM demonstrator for FMV</a>
</body></html>"""


def test_mfn_company_archive_extracts_dated_article():
    items = extract_items(HTML, source_url="https://www.mfn.se/all/a/scandinavian-astor-group.iframe")
    assert len(items) == 1
    assert "Oscilion" in items[0]["title"]
    assert items[0]["date"].isoformat() == "2026-11-19T14:00:00+00:00"
    assert items[0]["link"].startswith("https://www.mfn.se/a/")
