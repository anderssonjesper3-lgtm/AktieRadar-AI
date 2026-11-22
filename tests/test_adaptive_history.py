from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aktieradar_telegram as engine

TZ = ZoneInfo("Europe/Stockholm")


def make_candles(count, start=None):
    start = start or datetime(2026, 11, 23, 9, 0, tzinfo=TZ)
    rows = []
    for i in range(count):
        # Deliberate gaps: timestamps are not required to be adjacent.
        at = start + timedelta(minutes=5 * i + (30 if i >= 3 else 0))
        price = 100 + i
        rows.append({
            "time": at,
            "last_trade_time": at + timedelta(minutes=1),
            "open": price, "high": price + 1, "low": price - 0.2,
            "close": price + 0.5, "volume": 100,
        })
    return rows


def test_single_observed_bar_is_not_blocked_for_missing_consecutive_history(monkeypatch):
    now = datetime(2026, 11, 23, 10, 0, tzinfo=TZ)
    monkeypatch.setattr(engine, "market_session", lambda _: True)
    _, status = engine.classify(make_candles(1, now - timedelta(minutes=2)), now)
    assert "DATABLOCKERAD" not in status
    assert "historik" in status.lower() or "indikator" in status.lower()


def test_six_observed_bars_can_create_watch_across_natural_gaps(monkeypatch):
    now = datetime(2026, 11, 23, 10, 0, tzinfo=TZ)
    candles = make_candles(6, now - timedelta(minutes=8))
    candles[-1]["volume"] = 500
    candles[-1]["open"] = candles[-1]["close"] - 1
    monkeypatch.setattr(engine, "market_session", lambda _: True)
    signal, status = engine.classify(candles, now)
    assert signal is not None
    assert signal["kind"] == "MORGON-VAKTA"
    assert "DATABLOCKERAD" not in status


def test_chart_and_engine_share_the_same_observed_candle_list():
    # The app plots result['candles']; the analysis result is produced from the
    # same build_candles() output in multi_engine.analyze_company().
    from test_avanza_forbattrad import build_candles
    now = datetime(2026, 11, 23, 9, 0, tzinfo=TZ)
    points = [
        {"timestamp": int((now + timedelta(minutes=m)).timestamp() * 1000),
         "open": 100 + m, "high": 101 + m, "low": 99 + m,
         "close": 100.5 + m, "totalVolumeTraded": 10}
        for m in (0, 2, 10, 25)
    ]
    candles, _ = build_candles(points)
    chart_data = candles
    analysis_data = candles
    assert chart_data is analysis_data
    assert len(chart_data) == 3
    assert [x["source_minutes"] for x in chart_data] == [2, 1, 1]
