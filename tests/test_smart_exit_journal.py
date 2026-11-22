from datetime import datetime, timezone, timedelta

from performance import evaluate_smart_exit, record_signal, update_open_trades, load_journal


def candles_for_trend(prices, volumes=None):
    start = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
    volumes = volumes or [100] * len(prices)
    rows = []
    for i, price in enumerate(prices):
        previous = prices[i-1] if i else price
        rows.append({
            "time": start + timedelta(minutes=5*i),
            "open": previous,
            "high": max(previous, price) + 0.1,
            "low": min(previous, price) - 0.1,
            "close": price,
            "volume": volumes[i],
        })
    return rows


def test_smart_exit_keeps_strong_uptrend():
    prices = [100 + i * 0.15 for i in range(60)]
    status, _ = evaluate_smart_exit(candles_for_trend(prices))
    assert status == "BEHÅLL / TREND STARK"


def test_two_percent_gain_does_not_close_trade(tmp_path):
    path = tmp_path / "journal.json"
    signal = {
        "kind": "KÖP-KANDIDAT",
        "time": datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
        "close": 100.0,
        "score": 75,
        "reasons": ["test"],
    }
    record_signal("Test AB", "TEST", signal, path=path)
    prices = [100 + i * 0.15 for i in range(60)]
    candles = candles_for_trend(prices)
    update_open_trades({"TEST": 103.2}, candles_by_ticker={"TEST": candles},
                       now=datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc), path=path)
    trade = load_journal(path)["trades"][0]
    assert trade["status"] == "OPEN"


def test_minus_one_percent_stop_closes_trade(tmp_path):
    path = tmp_path / "journal.json"
    signal = {
        "kind": "KÖP-KANDIDAT",
        "time": datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
        "close": 100.0,
        "score": 75,
        "reasons": ["test"],
    }
    record_signal("Test AB", "TEST", signal, path=path)
    closed = update_open_trades({"TEST": 98.5}, candles_by_ticker={},
                                now=datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc), path=path)
    trade = load_journal(path)["trades"][0]
    assert closed == 1
    assert trade["status"] == "CLOSED"
    assert trade["exit_reason"] == "STOP -1%"
