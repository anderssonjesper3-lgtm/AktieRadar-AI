"""AktieRadar AI – Saab B, datakvalitet och indikativa signaler.

Körs via GitHub Actions. Kräver fastmcp och avanza_mcp.
Inga order läggs. Börsens helgdagar/avvikelser verifieras inte här.
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastmcp import Client
from avanza_mcp import mcp

SWEDEN = ZoneInfo("Europe/Stockholm")
ORDER_BOOK_ID = "5401"
MINUTE_LIMIT = 100
MAX_PAGES = 20
LOOKBACK = 21  # aktuell 5-minutersstapel + 20 tidigare
MAX_AGE_MINUTES = 20

def calculate_ema(values, period):
    # Samma grundprincip som EMA i TradingView:
    # starta med ett glidande medelvärde.
    if len(values) < period:
        return [None] * len(values)

    result = [None] * len(values)
    initial = sum(values[:period]) / period
    result[period - 1] = initial

    multiplier = 2 / (period + 1)
    previous = initial

    for i in range(period, len(values)):
        previous = (
            values[i] * multiplier
            + previous * (1 - multiplier)
        )
        result[i] = previous

    return result

def calculate_rsi(values, period=14):
    result = [None] * len(values)

    if len(values) <= period:
        return result

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [max(change, 0) for change in changes]
    losses = [max(-change, 0) for change in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def rsi_value(gain, loss):
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        rs = gain / loss
        return 100 - 100 / (1 + rs)

    result[period] = rsi_value(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        avg_gain = (
            avg_gain * (period - 1) + gains[i - 1]
        ) / period

        avg_loss = (
            avg_loss * (period - 1) + losses[i - 1]
        ) / period

        result[i] = rsi_value(avg_gain, avg_loss)

    return result

def calculate_macd(values):
    ema12 = calculate_ema(values, 12)
    ema26 = calculate_ema(values, 26)

    macd = [None] * len(values)

    for i in range(len(values)):
        if ema12[i] is not None and ema26[i] is not None:
            macd[i] = ema12[i] - ema26[i]

    valid = [v for v in macd if v is not None]
    signal_valid = calculate_ema(valid, 9)

    signal = [None] * len(values)
    histogram = [None] * len(values)

    j = 0
    for i, value in enumerate(macd):
        if value is not None:
            signal[i] = signal_valid[j]

            if signal[i] is not None:
                histogram[i] = value - signal[i]

            j += 1

    return macd, signal, histogram

def detect_candlestick_patterns(candles):
    results = []

    for i, candle in enumerate(candles):
        op = candle["open"]
        cl = candle["close"]
        hi = candle["high"]
        lo = candle["low"]

        body = abs(cl - op)
        upper_wick = hi - max(op, cl)
        lower_wick = min(op, cl) - lo

        # Gron hammer enligt var ursprungliga strategi
        hammer = (
            cl > op
            and lower_wick >= 2 * max(body, 0.01)
            and upper_wick <= max(body, 0.01)
        )

        engulfing = False

        if i > 0:
            previous = candles[i - 1]

            # Jamfor bara intilliggande 5-minutersljus
            consecutive = (
                candle["time"] - previous["time"]
            ).total_seconds() == 300

            engulfing = (
                consecutive
                and cl > op
                and previous["close"] < previous["open"]
                and cl >= previous["open"]
                and op <= previous["close"]
            )

        results.append({
            "time": candle["time"],
            "hammer": hammer,
            "engulfing": engulfing
        })

    return results

def calculate_signal_scores(
    candles, ema9, ema21, rsi14,
    macd_hist, relative_volume, patterns
):
    scores = []

    for i, candle in enumerate(candles):
        score = 0
        reasons = []

        # Vi behöver tillräcklig historik.
        if i == 0:
            scores.append(None)
            continue

        required = (
            ema9[i], ema21[i],
            rsi14[i], rsi14[i - 1],
            macd_hist[i], macd_hist[i - 1],
            relative_volume[i]
        )

        if any(value is None for value in required):
            scores.append(None)
            continue

        # Bullish engulfing: 20 poang
        if patterns[i]["engulfing"]:
            score += 20
            reasons.append("Engulfing")

        # Hammer: 15 poang
        if patterns[i]["hammer"]:
            score += 15
            reasons.append("Hammer")

        # RSI stiger och ligger mellan 50 och 70: 15
        if (
            50 < rsi14[i] < 70
            and rsi14[i] > rsi14[i - 1]
        ):
            score += 15
            reasons.append("Stark RSI")

        # MACD-histogram positivt och stigande: 15
        if (
            macd_hist[i] > 0
            and macd_hist[i] > macd_hist[i - 1]
        ):
            score += 15
            reasons.append("Stark MACD")

        # Volym over 1,5 ganger genomsnittet: 20
        if relative_volume[i] > 1.5:
            score += 20
            reasons.append("Stark volym")

        # Kurs over EMA9 och EMA9 over EMA21: 10
        if (
            candle["close"] > ema9[i] > ema21[i]
        ):
            score += 10
            reasons.append("Positiv EMA-trend")

        scores.append({
            "time": candle["time"],
            "score": score,
            "reasons": reasons
        })

    return scores

def check_buy_signal(score, data_quality_ok):
    if not data_quality_ok:
        return "BLOCKERAD - OTILLRACKLIG SAMMANHANGANDE DATA"

    if score is None:
        return "BLOCKERAD - INDIKATORER SAKNAS"

    if score >= 70:
        return "KOP? - KANDIDAT"

    if score >= 50:
        return "VAKTA - INTRESSANT LAGE"

    return "AVVAKTA"

def check_local_data_quality(candles, index, lookback=20):
    if index < lookback - 1:
        return False

    from datetime import timedelta

    start_index = index - lookback + 1

    for i in range(start_index + 1, index + 1):
        previous = candles[i - 1]["time"]
        current = candles[i]["time"]

        if current - previous != timedelta(minutes=5):
            return False

    return True

def calculate_relative_volume(candles, period=20):
    result = [None] * len(candles)
    for i in range(period, len(candles)):
        window = candles[i-period:i+1]
        if not check_local_data_quality(candles, i, lookback=period+1):
            continue
        avg = sum(c["volume"] for c in window[:-1]) / period
        if avg > 0:
            result[i] = window[-1]["volume"] / avg
    return result


def consecutive_count(candles):
    if not candles:
        return 0
    count = 1
    for i in range(len(candles)-1, 0, -1):
        if candles[i]["time"] - candles[i-1]["time"] != timedelta(minutes=5):
            break
        count += 1
    return count


def build_candles(points):
    groups = defaultdict(dict)
    for p in points:
        dt = datetime.fromtimestamp(p["timestamp"] / 1000, tz=timezone.utc).astimezone(SWEDEN)
        minute = dt.replace(second=0, microsecond=0)
        start = minute.replace(minute=(minute.minute // 5) * 5)
        groups[start][minute] = p

    candles, gaps = [], []
    for start, minutes in sorted(groups.items()):
        expected = [start + timedelta(minutes=j) for j in range(5)]
        missing = [m for m in expected if m not in minutes]
        if missing:
            gaps.append((start, missing))
            continue
        values = [minutes[m] for m in expected]
        candles.append({
            "time": start,
            "open": values[0]["open"],
            "high": max(v["high"] for v in values),
            "low": min(v["low"] for v in values),
            "close": values[-1]["close"],
            "volume": sum(v.get("totalVolumeTraded", 0) for v in values),
        })
    return candles, gaps


async def fetch_points(order_book_id=None):
    points = []
    resolutions = set()
    async with Client(mcp) as client:
        for page in range(MAX_PAGES):
            result = await client.call_tool("get_stock_chart", {
                "order_book_id": order_book_id or ORDER_BOOK_ID,
                "time_period": "today",
                "offset": page * MINUTE_LIMIT,
                "limit": MINUTE_LIMIT,
            })
            payload = result.structured_content or {}
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
                raise ValueError("Oväntat svar från Avanza: saknar data")
            body = payload["data"]
            resolution = body.get("metadata", {}).get("resolution", {}).get("chartResolution")
            resolutions.add(resolution)
            if resolution != "minute":
                raise ValueError(f"Fel upplösning: {resolution!r}; kräver minute")
            batch = body.get("ohlc")
            if not isinstance(batch, list):
                raise ValueError("Oväntat Avanza-svar: ohlc saknas")
            points.extend(batch)
            if not payload.get("pagination", {}).get("has_more", False):
                break
        else:
            raise ValueError("Sidgräns uppnådd – historiken kan vara ofullständig")
    unique = {p["timestamp"]: p for p in points}
    return sorted(unique.values(), key=lambda p: p["timestamp"]), len(points)


async def main():
    now = datetime.now(SWEDEN)
    print("=== AKTIERADAR AI | SAAB B ===")
    print("Körning:", now.strftime("%Y-%m-%d %H:%M:%S %Z"))
    try:
        points, fetched = await fetch_points()
    except Exception as exc:
        print("SIGNALSTATUS: BLOCKERAD - DATAHAMTNING MISSLYCKADES")
        print("ORSAK:", exc)
        raise

    candles, gaps = build_candles(points)
    print("Minutposter:", fetched, "| unika:", len(points))
    print("Kompletta 5-minutersstaplar:", len(candles))
    print("Ofullständiga perioder:", len(gaps))
    for start, missing in gaps[:10]:
        print("  Lucka", start.strftime("%Y-%m-%d %H:%M"),
              "saknar", ", ".join(m.strftime("%H:%M") for m in missing))
    if len(gaps) > 10:
        print("  ... ytterligare", len(gaps)-10, "luckor")

    if not candles:
        print("SIGNALSTATUS: BLOCKERAD - INGA KOMPLETTA STAPLAR")
        return

    closes = [c["close"] for c in candles]
    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    rsi14 = calculate_rsi(closes, 14)
    _, _, hist = calculate_macd(closes)
    rv = calculate_relative_volume(candles)
    patterns = detect_candlestick_patterns(candles)
    scores = calculate_signal_scores(candles, ema9, ema21, rsi14, hist, rv, patterns)
    last = candles[-1]
    end = last["time"] + timedelta(minutes=5)
    completed = now >= end
    age = (now - end).total_seconds() / 60
    continuous = consecutive_count(candles)
    quality_ok = continuous >= LOOKBACK
    score = scores[-1]["score"] if scores and scores[-1] is not None else None
    best = max((s["score"] for s in scores if s is not None), default=None)
    # Detta är en normal-tidskontroll, inte en verifierad börskalender.
    normal_hours = now.weekday() < 5 and (9, 0) <= (now.hour, now.minute) < (17, 30)
    same_day = last["time"].date() == now.date()

    status = check_buy_signal(score, quality_ok)
    if not quality_ok:
        status = "BLOCKERAD - OTILLRACKLIG SAMMANHANGANDE DATA"
    elif score is None:
        status = "BLOCKERAD - INDIKATORER SAKNAS"
    if not completed:
        status = "BLOCKERAD - STAPEL EJ FARDIG"
    if not same_day or age > MAX_AGE_MINUTES or age < 0:
        status = "BLOCKERAD - GAMMAL ELLER OGILTIG KURSDATA"
    if not normal_hours:
        status = "BLOCKERAD - UTANFOR NORMAL HANDELSTID"

    print("Senaste stapel:", last["time"].strftime("%Y-%m-%d %H:%M"))
    print("Stapelns tidsperiod avslutad:", completed)
    print("Kursdata från idag:", same_day)
    print("Ålder från stapelns slut (min):", round(age, 1))
    print("Sammanhängande staplar:", continuous, "/", LOOKBACK)
    print("Relativ volym:", round(rv[-1], 2) if rv[-1] is not None else "saknas")
    print("Senaste poäng:", score if score is not None else "saknas")
    print("Högsta historiska poäng:", best if best is not None else "saknas")
    print("SIGNALSTATUS:", status)
    print("OBS: Kandidatsignal är inte handelsrekommendation. Börshelgdagar och datans realtidsstatus verifieras inte.")


if __name__ == "__main__":
    asyncio.run(main())
