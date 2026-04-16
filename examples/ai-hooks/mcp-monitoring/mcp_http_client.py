# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

"""MCP HTTP client test. Connects to mcp_file_server.py on port 8001."""

import asyncio
from fastmcp import Client


async def main():
    config = {
        "mcpServers": {
            "file_server": {
                "transport": "http",
                "url": "http://127.0.0.1:8001/mcp",
                "headers": {"Authorization": "Bearer token"},
                "auth": "dev-test-token",
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

        result = await client.call_tool("list_files", {"directory": ".", "pattern": "*.py"})
        print(f"Files: {result.content[0].text[:100]}")


asyncio.run(main())
