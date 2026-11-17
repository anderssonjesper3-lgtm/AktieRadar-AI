import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

from fastmcp import Client
from avanza_mcp import mcp

SWEDEN = ZoneInfo("Europe/Stockholm")


async def main():
    print("AktieRadar AI - Avanza test 7")
    print("Bygger riktiga 5-minutersljus...")

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
            batch = data.get("data", {}).get("ohlc", [])
            points.extend(batch)

            if not data.get("pagination", {}).get(
                "has_more", False
            ):
                break

    # Sortera och ta bort eventuella dubbletter
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

        # Avrunda nedåt till närmaste 5 minuter
        minute = (dt.minute // 5) * 5
        start = dt.replace(
            minute=minute,
            second=0,
            microsecond=0
        )

        groups[start].append(point)

    candles = []

    for start, group in sorted(groups.items()):
        group.sort(key=lambda p: p["timestamp"])

        candle = {
            "time": start.strftime("%H:%M"),
            "open": group[0]["open"],
            "high": max(p["high"] for p in group),
            "low": min(p["low"] for p in group),
            "close": group[-1]["close"],
            "volume": sum(
                p.get("totalVolumeTraded", 0)
                for p in group
            ),
            "minutes": len(group)
        }

        candles.append(candle)

    complete = [
        c for c in candles if c["minutes"] == 5
    ]

    incomplete = [
        c for c in candles if c["minutes"] != 5
    ]

    print("MINUTPUNKTER:", len(points))
    print("5-MINUTERSLJUS:", len(candles))
    print("KOMPLETTA LJUS:", len(complete))
    print("OFULLSTANDIGA LJUS:", len(incomplete))

    print("\nFORSTA FEM LJUSEN:")
    for candle in candles[:5]:
        print(candle)

    print("\nOFULLSTANDIGA PERIODER:")
    for candle in incomplete[:15]:
        print(candle["time"], candle["minutes"])

asyncio.run(main())
