# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

"""MCP client example.

Launches mcp_server.py as a subprocess under BlueRock instrumentation
and exercises tools, resources, and prompts via stdio.

Run:
    python -m bluepython --oss mcp_client.py

Events written to ~/.bluerock/event-spool/*.ndjson
"""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_script = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    cfg_dir = os.path.join(os.path.expanduser("~"), ".bluerock")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "bluepython", "--oss", "--cfg-dir", cfg_dir, server_script],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"Available tools: {[t.name for t in tools.tools]}")

            result = await session.call_tool("add", arguments={"a": 2, "b": 3})
            print(f"add(2, 3) = {result.content[0].text}")

            result = await session.call_tool("greet", arguments={"name": "BlueRock"})
            print(f"greet = {result.content[0].text}")

            prompts = await session.list_prompts()
            print(f"Prompts: {[p.name for p in prompts.prompts]}")

            resources = await session.list_resources()
            print(f"Resources: {[r.name for r in resources.resources]}")

            content = await session.read_resource("config://version")
            print(f"Version: {content.contents[0].text}")

            content = await session.read_resource("users://42/profile")
            print(f"Profile: {content.contents[0].text}")

            prompt_result = await session.get_prompt("summarize", arguments={"text": "hello world"})
            print(f"Prompt: {prompt_result.messages[0].content.text}")


asyncio.run(main())
