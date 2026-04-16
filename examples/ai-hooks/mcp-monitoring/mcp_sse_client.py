# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

"""MCP SSE client test. Connects to mcp_linux_admin.py on port 8002."""

import asyncio
from fastmcp import Client


async def main():
    config = {
        "mcpServers": {
            "linux_admin": {
                "transport": "sse",
                "url": "http://127.0.0.1:8002/sse",
            }
        }
    }
    client = Client(config)
    async with client:
        tools = await client.list_tools()
        print(f"Tools: {[t.name for t in tools]}")

        resources = await client.list_resources()
        print(f"Resources: {[r.name for r in resources]}")

        prompts = await client.list_prompts()
        print(f"Prompts: {[p.name for p in prompts]}")

        result = await client.call_tool("run_command", {"command": "echo hello"})
        print(f"Result: {result.content[0].text[:100]}")


asyncio.run(main())
