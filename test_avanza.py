import asyncio
from datetime import datetime, timezone
from fastmcp import Client
from avanza_mcp import mcp

async def main():
    print("AktieRadar AI - Avanza test 6")

    all_points = []

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
            points = data.get("data", {}).get("ohlc", [])
            all_points.extend(points)

            print(f"Hamtade {len(points)} punkter")

            if not data.get("pagination", {}).get("has_more", False):
                break

    all_points.sort(key=lambda p: p["timestamp"])

    print("TOTALT:", len(all_points))

    if all_points:
        first = datetime.fromtimestamp(
            all_points[0]["timestamp"] / 1000,
            tz=timezone.utc
        )
        last = datetime.fromtimestamp(
            all_points[-1]["timestamp"] / 1000,
            tz=timezone.utc
        )

        print("FORSTA TID:", first)
        print("SISTA TID:", last)
        print("FORSTA KURS:", all_points[0]["open"])
        print("SISTA KURS:", all_points[-1]["close"])

        gaps = 0
        for a, b in zip(all_points, all_points[1:]):
            minutes = (
                b["timestamp"] - a["timestamp"]
            ) / 60000

            if minutes > 1:
                gaps += 1

        print("LUCKOR OVER 1 MINUT:", gaps)

asyncio.run(main())
