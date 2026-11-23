from datetime import datetime, timedelta, timezone
from news_momentum import evaluate_news_momentum

NOW = datetime(2026, 11, 23, 11, 0, tzinfo=timezone.utc)
COMPANY = {"name": "PowerCell", "annual_revenue_sek": None}
NEWS = {"company": "PowerCell", "title": "PowerCell signs new contract", "description": "",
        "url": "https://example.org/release", "published": NOW-timedelta(minutes=50)}

def bar(mins, op, close, volume):
    time = NOW-timedelta(minutes=mins)
    return {"time": time, "last_trade_time": time+timedelta(minutes=1),
            "open": op, "close": close, "high": max(op, close),
            "low": min(op, close), "volume": volume}

def test_news_momentum_confirms_with_observed_bars():
    candles = [bar(70, 100, 100, 10), bar(65, 100, 100, 10),
               bar(60, 100, 100, 10), bar(55, 100, 100, 10),
               bar(20, 100, 101, 12), bar(15, 101, 102, 40)]
    result = evaluate_news_momentum(COMPANY, [NEWS], candles, NOW)
    assert result["kind"] == "KÖP-KANDIDAT"
    assert result["volume_confirmed"]

def test_stale_data_cannot_buy():
    candles = [bar(80, 100, 100, 10), bar(70, 100, 100, 10),
               bar(60, 100, 100, 10), bar(55, 100, 100, 10),
               bar(40, 100, 101, 12), bar(35, 101, 102, 40)]
    assert evaluate_news_momentum(COMPANY, [NEWS], candles, NOW)["kind"] != "KÖP-KANDIDAT"

def test_no_news_cannot_buy():
    assert evaluate_news_momentum(COMPANY, [], [bar(5, 100, 102, 40)], NOW)["kind"] != "KÖP-KANDIDAT"
