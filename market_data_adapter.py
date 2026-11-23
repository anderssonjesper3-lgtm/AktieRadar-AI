"""Provider-neutral streaming market-data normalization and five-minute aggregation.

No fabricated market prices. Only closed candles may enter the signal engine.
"""
from datetime import datetime, timezone
from math import isfinite

def normalize_eodhd_minute(event, received_at=None):
    if not isinstance(event, dict) or event.get("i") != "1m":
        raise ValueError("Expected a one-minute EODHD candle")
    symbol = event.get("s")
    timestamp = event.get("t")
    values = [event.get(k) for k in ("o", "h", "l", "c", "v")]
    if not isinstance(symbol, str) or not symbol or isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise ValueError("Invalid symbol or timestamp")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError("Invalid OHLCV")
    o, h, l, c, v = values
    if min(o, h, l, c) <= 0 or v < 0 or h < max(o, c, l) or l > min(o, c, h):
        raise ValueError("Inconsistent OHLCV")
    return {"provider": "eodhd_cboe_europe", "symbol": symbol, "start_ms": timestamp,
            "open": float(o), "high": float(h), "low": float(l),
            "close": float(c), "volume": float(v),
            "received_at_utc": (received_at or datetime.now(timezone.utc)).isoformat(),
            "realtime_verified": False}

class CandleAggregator:
    """Rolling minute updates replace previous same-minute versions, never sum twice."""
    def __init__(self):
        self.minutes = {}

    def update(self, minute):
        key = (minute["symbol"], minute["start_ms"])
        self.minutes[key] = minute

    def closed_five_minute(self, symbol, now_ms, max_age_ms=120000):
        buckets = {}
        for (s, t), bar in self.minutes.items():
            if s == symbol:
                buckets.setdefault(t // 300000 * 300000, {})[t] = bar
        result = []
        for start, minute_map in sorted(buckets.items()):
            if now_ms < start + 300000 or len(minute_map) != 5:
                continue
            times = sorted(minute_map)
            if times != [start + i * 60000 for i in range(5)]:
                continue
            parts = [minute_map[t] for t in times]
            result.append({"symbol": symbol, "start_ms": start,
                           "open": parts[0]["open"], "high": max(x["high"] for x in parts),
                           "low": min(x["low"] for x in parts), "close": parts[-1]["close"],
                           "volume": sum(x["volume"] for x in parts),
                           "fresh": 0 <= now_ms - (start + 300000) <= max_age_ms,
                           "realtime_verified": False})
        return result
