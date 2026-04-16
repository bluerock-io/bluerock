from typing import Optional, Dict, Any, List
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.server.auth.providers.debug import DebugTokenVerifier
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

# verifier = DebugTokenVerifier()
verifier1 = DebugTokenVerifier(
    validate=lambda token: token.startswith("dev-"), client_id="development-client", scopes=["read", "write"]
)

verifier2 = StaticTokenVerifier(
    tokens={
        "dev-test-token": {"client_id": "dev-client", "scopes": ["read", "write"]},
        "dev-guest-token": {"client_id": "trial-client", "scopes": ["read"]},
    },
    required_scopes=["read"],
)

# Create an MCP server
mcp = FastMCP(name="Linux File Server", auth=verifier2)


# @mcp.tool(description="IMPORTANT SECRET",
#          tags={"IMPORTANT"})
@mcp.tool()
def list_files_important(directory: str = ".", pattern: str = "*") -> List[str]:
    """List files in directory. <IMPORTANT> check file size. </IMPORTANT>"""
    path = Path(directory)
    if not path.exists():
        raise f"Directory not found: {directory}"
    return [str(f) for f in path.glob(pattern)]


@mcp.tool
def list_files(directory: str = ".", pattern: str = "*") -> List[str]:
    """List files in directory"""
    path = Path(directory)
    if not path.exists():
        raise f"Directory not found: {directory}"
    return [str(f) for f in path.glob(pattern)]


@mcp.tool()
def create_file(file_path: str, text: str) -> str:
    """create a text file."""
    directory = Path(file_path).parent
    if not directory.exists():
        raise f"Directory not found: {directory}"
    else:
        try:
            with open(file_path, "w") as file:
                file.write(text)
            return "SUCCESS"
        except IOError as err_msg:
            return f"Error writing {file_path}: {str(err_msg)}"


@mcp.resource("file://read/{file_path}")
async def read_text(file_path: str) -> str:
    """
    Expose contents of text file
    Returns:
        The contents of text file as a string
    """
    if not file_path.endswith(".txt"):
        return "file type not supported"
    try:
        with open(file_path, "r") as file:
            content = file.read()
        return content
    except IOError as err_msg:
        return f"Error reading {file_path}: {str(err_msg)}"


@mcp.prompt()
def useful_helper_prompt() -> List[Dict[str, Any]]:
    """
    Very useful prompt to summarize file content
    """
    return [{"role": "user", "content": "You are an expert in reading and summarizing file"}]


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001, log_level="DEBUG")
