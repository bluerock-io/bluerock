# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

import anyio
import mcp.types as types
from mcp import ClientSession
from mcp.server import Server
from mcp.shared.memory import create_client_server_memory_streams

server = Server("Tool Test Server")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="greet",
            description="Greet a user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "greet":
        return [types.TextContent(type="text", text=f"Hello, {arguments['name']}!")]
    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with create_client_server_memory_streams() as (
        client_streams,
        server_streams,
    ):
        client_read, client_write = client_streams
        server_read, server_write = server_streams

        async with anyio.create_task_group() as tg:
            tg.start_soon(
                lambda: server.run(
                    server_read,
                    server_write,
                    server.create_initialization_options(),
                )
            )

            async with ClientSession(
                read_stream=client_read,
                write_stream=client_write,
            ) as session:
                await session.initialize()
                result = await session.call_tool("greet", {"name": "world"})
                print(result)

            tg.cancel_scope.cancel()


anyio.run(main)
