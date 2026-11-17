import asyncio
from fastmcp import Client
from avanza_mcp import mcp

async def main():
    print("AktieRadar AI - Avanza test 3")
    print("Hamtar riktig kurs for Saab B...")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_stock_quote",
            {"order_book_id": "5401"}
        )

        print("RESULTAT:")
        print(result.structured_content)

asyncio.run(main())
