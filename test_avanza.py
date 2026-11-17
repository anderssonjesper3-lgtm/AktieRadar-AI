import asyncio
from fastmcp import Client
from avanza_mcp import mcp

async def main():
    print("AktieRadar AI - Avanza test 5")
    print("Hamtar dagens kurshistorik for Saab B...")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_stock_chart",
            {
                "order_book_id": "5401",
                "time_period": "today",
                "offset": 0,
                "limit": 5
            }
        )

        print("RESULTAT:")
        print(result.structured_content)

asyncio.run(main())
