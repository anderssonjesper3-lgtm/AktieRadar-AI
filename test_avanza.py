import asyncio
from fastmcp import Client
from avanza_mcp import mcp

async def main():
    print("AktieRadar AI - Avanza test 4")
    print("Undersoker historiska kursdata...")

    async with Client(mcp) as client:
        tools = await client.list_tools()

        for tool in tools:
            if tool.name == "get_stock_chart":
                print("FUNKTION:", tool.name)
                print("BESKRIVNING:", tool.description)
                print("INSTÄLLNINGAR:", tool.inputSchema)
                return

        print("Funktionen hittades inte.")

asyncio.run(main())
