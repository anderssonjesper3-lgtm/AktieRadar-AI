import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

from fastmcp import Client
from avanza_mcp import mcp

SWEDEN = ZoneInfo("Europe/Stockholm")


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
def calculate_relative_volume(candles, period=20):
    result = [None] * len(candles)

    for i in range(period, len(candles)):
        # Jämför med de 20 föregående ljusen
        previous = candles[i-period:i]

        # Beräkna bara när alla ljus är sammanhängande
        continuous = all(
            (
                previous[j]["time"] -
                previous[j-1]["time"]
            ).total_seconds() == 300
            for j in range(1, len(previous))
        )

        continuous = continuous and (
            candles[i]["time"] -
            previous[-1]["time"]
        ).total_seconds() == 300

        if not continuous:
            continue

        average_volume = sum(
            c["volume"] for c in previous
        ) / period

        if average_volume > 0:
            result[i] = (
                candles[i]["volume"] / average_volume
            )

    return result
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
async def main():
    print("AktieRadar AI - Avanza test 8")
    print("Beraknar EMA 9 och EMA 21...")

    points = []

    async with Client(mcp) as client:
        for offset in range(0, 1000, 100):
            result = await client.call_tool(
                "get_stock_chart",
                {
                    "order_book_id": "5401",
                    "time_period": "today",
                    "offset": offset,
                    "limit": 100
                }
            )

            data = result.structured_content
            points.extend(
                data.get("data", {}).get("ohlc", [])
            )

            if not data.get("pagination", {}).get(
                "has_more", False
            ):
                break

    unique = {p["timestamp"]: p for p in points}
    points = sorted(
        unique.values(),
        key=lambda p: p["timestamp"]
    )

    groups = defaultdict(list)

    for point in points:
        dt = datetime.fromtimestamp(
            point["timestamp"] / 1000,
            tz=timezone.utc
        ).astimezone(SWEDEN)

        start = dt.replace(
            minute=(dt.minute // 5) * 5,
            second=0,
            microsecond=0
        )

        groups[start].append((dt, point))

    candles = []
    skipped = []

    for start, group in sorted(groups.items()):
        group.sort(key=lambda item: item[0])

        actual_minutes = {
            dt.replace(second=0, microsecond=0)
            for dt, _ in group
        }

        expected_minutes = {
            start.replace(minute=start.minute + i)
            for i in range(5)
        }

        if actual_minutes != expected_minutes:
            skipped.append(start.strftime("%H:%M"))
            continue

        prices = [p for _, p in group]

        candles.append({
            "time": start,
            "open": prices[0]["open"],
            "high": max(p["high"] for p in prices),
            "low": min(p["low"] for p in prices),
            "close": prices[-1]["close"],
            "volume": sum(
                p.get("totalVolumeTraded", 0)
                for p in prices
            )
        })

    closes = [c["close"] for c in candles]

    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    rsi14 = calculate_rsi(closes, 14)
    macd, macd_signal, macd_hist = calculate_macd(closes)

    print("\nSENASTE FEM RSI- OCH MACD-VARDENA:")

    for i in range(max(0, len(candles) - 5), len(candles)):
        print(
            candles[i]["time"].strftime("%H:%M"),
            "RSI:", round(rsi14[i], 2) if rsi14[i] is not None else None,
            "MACD:", round(macd[i], 4) if macd[i] is not None else None,
            "SIGNAL:", round(macd_signal[i], 4) if macd_signal[i] is not None else None,
            "HIST:", round(macd_hist[i], 4) if macd_hist[i] is not None else None
        )
    relative_volume = calculate_relative_volume(candles)

    print("\nSENASTE FEM VOLYMVARDENA:")

    for i in range(max(0, len(candles) - 5), len(candles)):
        rv = relative_volume[i]

        if rv is None:
            print(
                candles[i]["time"].strftime("%H:%M"),
                "Volym:", candles[i]["volume"],
                "Relativ volym: EJ BERAKNAD"
            )
        else:
            print(
                candles[i]["time"].strftime("%H:%M"),
                "Volym:", candles[i]["volume"],
                "Relativ volym:", round(rv, 2),
                "STARK VOLYM:", rv > 1.5
            )    
    patterns = detect_candlestick_patterns(candles)

    print("\nCANDLESTICK-MONSTER:")

    found = 0

    for pattern in patterns:
        if pattern["engulfing"] or pattern["hammer"]:
            print(
                pattern["time"].strftime("%H:%M"),
                "ENGULFING:", pattern["engulfing"],
                "HAMMER:", pattern["hammer"]
            )
            found += 1

    print("ANTAL MONSTER:", found)   
    scores = calculate_signal_scores(
        candles,
        ema9,
        ema21,
        rsi14,
        macd_hist,
        relative_volume,
        patterns
    )

    print("\nAKTIERADAR AI - SIGNALPOANG:")

    valid_scores = [
        item for item in scores
        if item is not None
    ]

    print("ANTAL BERAKNADE:", len(valid_scores))

    for item in valid_scores:
        if item["score"] >= 50:
            print(
                item["time"].strftime("%H:%M"),
                "POANG:", item["score"],
                "ORSAKER:", ", ".join(item["reasons"])
            )

    print("\nHOGSTA POANG:")
    if valid_scores:
        best = max(
            valid_scores,
            key=lambda item: item["score"]
        )
        print(
            best["time"].strftime("%H:%M"),
            "POANG:", best["score"],
            "ORSAKER:", ", ".join(best["reasons"])
        )
    else:
        print("Inga tillforlitliga poang kunde beraknas")
    print("KOMPLETTA LJUS:", len(candles))
    print("OVERHOPPADE PERIODER:", len(skipped))
    print("OVERHOPPADE TIDER:", skipped)

    print("\nSENASTE FEM EMA-VARDENA:")

    for i in range(max(0, len(candles) - 5), len(candles)):
        print(
            candles[i]["time"].strftime("%H:%M"),
            "KURS:", closes[i],
            "EMA9:", round(ema9[i], 2) if ema9[i] is not None else None,
            "EMA21:", round(ema21[i], 2) if ema21[i] is not None else None
        )

    print("\nEMA-KORSNINGAR:")

    crossings = 0

    for i in range(1, len(candles)):
        if None in (
            ema9[i], ema21[i],
            ema9[i - 1], ema21[i - 1]
        ):
            continue

        # Kontrollera att ljusen ligger direkt efter varandra.
        if (
            candles[i]["time"] - candles[i - 1]["time"]
        ).total_seconds() != 300:
            continue

        if (
            ema9[i - 1] <= ema21[i - 1]
            and ema9[i] > ema21[i]
        ):
            print(
                "POSITIV KORSNING:",
                candles[i]["time"].strftime("%H:%M")
            )
            crossings += 1

        elif (
            ema9[i - 1] >= ema21[i - 1]
            and ema9[i] < ema21[i]
        ):
            print(
                "NEGATIV KORSNING:",
                candles[i]["time"].strftime("%H:%M")
            )
            crossings += 1

    print("ANTAL KORSNINGAR:", crossings)


asyncio.run(main())
