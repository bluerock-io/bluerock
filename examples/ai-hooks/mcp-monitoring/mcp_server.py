# Copyright (C) 2026 BlueRock Security, Inc.
# All rights reserved.

"""MCP server example with tools, resources, and prompts.

Launched as a subprocess by mcp_client.py under BlueRock instrumentation.
Exercises all mcp_server_add subtypes (tool, resource, prompt).
"""

from fastmcp import FastMCP

mcp = FastMCP("example-server")


@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@mcp.tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"


@mcp.resource("config://version")
def get_version():
    return "bluerock-0.0.1"


@mcp.resource("users://{user_id}/profile")
def get_profile(user_id: int):
    """Dynamic resource template."""
    import json

    return json.dumps({"name": f"User {user_id}", "status": "active"})


@mcp.prompt
def summarize(text: str) -> str:
    """Generate a prompt asking for a summary."""
    return f"Please summarize: {text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
