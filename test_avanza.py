import asyncio
from fastmcp import Client
from avanza_mcp import mcp

async def main():
    print("AktieRadar AI - Avanza test 2")
    print("Soker efter Saab B...")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_instruments",
            {
                "query": "Saab",
                "instrument_type": "stock"
            }
        )

        print("Sokresultat:")
        print(result.structured_content)

asyncio.run(main())
