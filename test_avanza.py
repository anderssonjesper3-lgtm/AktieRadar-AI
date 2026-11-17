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
