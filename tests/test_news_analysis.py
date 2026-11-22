from order_analysis import order_ratio
from news_analysis import analyze_news


def test_order_size_compared_to_verified_revenue():
    company = {"name": "ExampleCo", "annual_revenue_sek": 1_000_000_000}
    item = {"title": "ExampleCo receives order worth 250 miljoner kronor",
            "description": "New customer contract", "url": "https://example.com/news"}
    result = analyze_news(item, company)
    assert result["order_amount_sek"] == 250_000_000
    assert result["order_revenue_pct"] == 25.0
    assert result["view"] == "POSITIV"


def test_no_revenue_means_no_invented_order_ratio():
    company = {"name": "ExampleCo", "annual_revenue_sek": None}
    item = {"title": "ExampleCo receives order worth 250 miljoner kronor",
            "description": "", "url": "https://example.com/news"}
    result = analyze_news(item, company)
    assert result["order_amount_sek"] == 250_000_000
    assert result["order_revenue_pct"] is None
    assert any("årsomsättning saknas" in x for x in result["caveats"])


def test_uncertain_nonbinding_agreement_is_not_presented_as_confirmed_positive():
    company = {"name": "ExampleCo", "annual_revenue_sek": None}
    item = {"title": "ExampleCo signs letter of intent for potential order",
            "description": "", "url": "https://example.com/news"}
    result = analyze_news(item, company)
    assert result["view"] == "PRELIMINÄRT POSITIV"
    assert any("osäkerhetsformuleringar" in x for x in result["caveats"])
