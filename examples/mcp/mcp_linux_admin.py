#!/usr/bin/env python
# from mcp.server.fastmcp import FastMCP
from fastmcp import FastMCP
import subprocess
import asyncio
import os
import json
import base64
from typing import Optional, Dict, Any, List
from pathlib import Path

# Create an MCP server
mcp = FastMCP(name="Linux admin Server")


@mcp.tool()
async def run_command(command: str) -> Dict[str, Any]:
    """
    Run a terminal command and return the output.

    Args:
        command: The command to execute in the terminal

    Returns:
        A dictionary containing stdout, stderr, and return code
    """
    try:
        # Execute the command
        process = await asyncio.create_subprocess_shell(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Get output
        stdout, stderr = await process.communicate()

        # Return results
        return {
            "stdout": stdout.decode() if stdout else "",
            "stderr": stderr.decode() if stderr else "",
            "return_code": process.returncode,
        }
    except Exception as e:
        return {"stdout": "", "stderr": f"Error executing command: {str(e)}", "return_code": -1}


@mcp.tool()
async def curl_tool(url: str) -> Dict[str, Any]:
    """
    Download content from a specified URL

    Args:
        url: url to fetch content

    Returns:
        A dictionary containing the downloaded content and status
    """
    try:
        # Use curl to download the content
        process = await asyncio.create_subprocess_exec(
            "curl", "-s", url, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # Get output
        stdout, stderr = await process.communicate()

        # Return results
        return {
            "content": stdout.decode() if stdout else "",
            "error": stderr.decode() if stderr else "",
            "success": process.returncode == 0,
        }
    except Exception as e:
        return {"content": "", "error": f"Error downloading content: {str(e)}", "success": False}


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
    except Exception as e:
        return f"Error reading {file_path}: {str(e)}"


@mcp.prompt()
def useful_helper_prompt(lang: str) -> List[Dict[str, Any]]:
    """
    Very useful prompt for people learning linux and perl
    """
    return [{"role": "user", "content": f"You are an expert in {lang}.  write {lang} code that uses nc."}]


if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8002, log_level="DEBUG")
