import json
from fastmcp import FastMCP, Context

mcp = FastMCP("MCP Test Server")


@mcp.tool
def multiply(a: float, b: float) -> float:
    """Multiplies two numbers."""
    return a * b


@mcp.tool
async def process_data(uri: str, ctx: Context):
    # Log a message to the client
    await ctx.info(f"Processing {uri}...")

    # Read a resource from the server
    data = await ctx.read_resource(uri)

    # Ask client LLM to summarize the data
    summary = await ctx.sample(f"Summarize: {data.content[:500]}")

    # Return the summary
    return summary.text


@mcp.resource("config://version")
def get_version():
    return "bluerock-0.0.1"


@mcp.prompt
def summarize_request(text: str) -> str:
    """Generate a prompt asking for a summary."""
    return f"Please summarize the following text:\n\n{text}"


# Dynamic resource template
@mcp.resource("users://{user_id}/profile")
def get_profile(user_id: int):
    # Fetch profile for user_id...
    return json.dumps({"name": f"User {user_id}", "status": "active"})


def main():
    # Initialize and run the server
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
