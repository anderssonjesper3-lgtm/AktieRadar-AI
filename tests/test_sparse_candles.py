from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from test_avanza_forbattrad import (
    build_candles, consecutive_count, calculate_relative_volume,
)

TZ = ZoneInfo("Europe/Stockholm")


def point(at, price, volume=10):
    return {
        "timestamp": int(at.timestamp() * 1000),
        "open": price, "high": price + 1, "low": price - 1,
        "close": price + 0.5, "totalVolumeTraded": volume,
    }


def test_sparse_minutes_are_retained_without_synthetic_fill():
    start = datetime(2026, 11, 23, 9, 0, tzinfo=TZ)
    points = [point(start, 100), point(start + timedelta(minutes=2), 101),
              point(start + timedelta(minutes=4), 102)]
    candles, gaps = build_candles(points)
    assert len(candles) == 1
    assert candles[0]["source_minutes"] == 3
    assert candles[0]["open"] == 100
    assert candles[0]["close"] == 102.5
    assert candles[0]["volume"] == 30
    assert len(gaps) == 1
    assert len(points) == 3


def test_empty_five_minute_intervals_are_not_fabricated_and_bars_count_as_observed():
    start = datetime(2026, 11, 23, 9, 0, tzinfo=TZ)
    points = [point(start, 100), point(start + timedelta(minutes=10), 102),
              point(start + timedelta(minutes=25), 105)]
    candles, _ = build_candles(points)
    assert [x["time"] for x in candles] == [
        start, start + timedelta(minutes=10), start + timedelta(minutes=25)
    ]
    assert consecutive_count(candles) == 3


def test_relative_volume_uses_previous_observed_bars_across_gaps():
    start = datetime(2026, 11, 23, 9, 0, tzinfo=TZ)
    candles = [
        {"time": start + timedelta(minutes=5*i), "volume": 100}
        for i in range(20)
    ]
    candles[-1]["time"] += timedelta(minutes=35)
    candles.append({"time": start + timedelta(minutes=135), "volume": 200})
    rv = calculate_relative_volume(candles, period=20)
    assert rv[-1] == 2.0


def test_empty_input_returns_no_candles():
    candles, gaps = build_candles([])
    assert candles == []
    assert gaps == []
