import argparse
import asyncio
import sys
import os
from fastmcp import Client


async def main():
    args = parse_cmd(sys.argv)
    config = {}
    config["mcpServers"] = {}
    if args.transport in ["stdio", "all"] and not args.mcp_server:
        print("specify mcp stdio server program")
        sys.exit()
    stdio_server = {
        "test_server": {
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "bluepython", "--oss", "--cfg-dir", os.path.expanduser("~/.bluerock"), args.mcp_server],
        }
    }
    http_server_remote = {"deep_wiki": {"transport": "http", "url": "https://mcp.deepwiki.com/mcp"}}
    http_server = {
        "file_server": {
            "transport": "http",
            "url": "http://127.0.0.1:8001/mcp",
            "headers": {"Authorization": "Bearer token"},
            "auth": "dev-test-token",
        }
    }
    sse_server = {"linux_admin": {"transport": "sse", "url": "http://127.0.0.1:8002/sse"}}
    if args.transport == "stdio":
        config["mcpServers"].update(stdio_server)
    elif args.transport == "http":
        config["mcpServers"].update(http_server)
    elif args.transport == "remote_http":
        config["mcpServers"].update(http_server_remote)
    elif args.transport == "sse":
        config["mcpServers"].update(sse_server)
    elif args.transport == "all":
        config["mcpServers"].update(stdio_server)
        config["mcpServers"].update(http_server)
        config["mcpServers"].update(http_server_remote)
        config["mcpServers"].update(sse_server)
    print(config)

    client = Client(config)
    async with client:
        # Basic server interaction
        await client.ping()
        # list tools
        tools = await client.list_tools()
        print("*******************************")
        print(f"Available tools: {tools}")
        if args.transport == "stdio":
            # list resources
            resources = await client.list_resources()
            print("*******************************")
            print(f"Available resources: {resources}")
            # list prompts
            prompts = await client.list_prompts()
            print("*******************************")
            print(f"Available prompts: {prompts}")
            # Local MCP server Tool call
            result = await client.call_tool("multiply", {"a": 5, "b": 3})
            print("*******************************")
            print(f"Result: {result.content[0].text}")
            # Local MCP server static Resource call
            content = await client.read_resource("config://version")
            print("*******************************")
            print(f"Resource Result: {content[0].text}")
            # Local MCP server Dynamic Resource call
            content = await client.read_resource("users://5432/profile")
            print("*******************************")
            print(f"Resource Result: {content[0].text}")
            # Local MCP server prompt call
            text_data = "very long paragraph from curl output"
            messages = await client.get_prompt("summarize_request", {"text": text_data})
            print("*******************************")
            print(messages.messages[0].content.text)
        elif args.transport == "remote_http":
            # Remote MCP server tool call
            wiki_data = await client.call_tool("read_wiki_contents", {"repoName": "wonderwhy-er/DesktopCommanderMCP"})
            print("*******************************")
            print(wiki_data)
        elif args.transport == "http":
            # list resources
            resources = await client.list_resources()
            print("*******************************")
            print(f"Available resources: {resources}")
            # list prompts
            prompts = await client.list_prompts()
            print("*******************************")
            print(f"Available prompts: {prompts}")
            file_list = await client.call_tool("list_files", {"directory": ".", "pattern": "*"})
            print("*******************************")
            print(file_list)
        elif args.transport == "sse":
            # list resources
            resources = await client.list_resources()
            print("*******************************")
            print(f"Available resources: {resources}")
            # list prompts
            prompts = await client.list_prompts()
            print("*******************************")
            print(f"Available prompts: {prompts}")
            # MCP sse server tool call
            data = await client.call_tool("run_command", {"command": "env"})
            print("*******************************")
            print(data.content[0].text)
            # data = await client.call_tool("curl_tool", {"url": "https://github.com/datacline/secure-mcp-gateway/blob/main/requirements.txt"})
            # data = await client.call_tool("curl_tool", {"url": "https://linuxcommand.org/lc3_wss0030.php"})
            data = await client.call_tool("curl_tool", {"url": "https://text.npr.org"})
            print("*******************************")
            print(data.content[0].text)
            # Local MCP server static Resource call
            content = await client.read_resource("file://read/sample.txt")
            print("*******************************")
            print(f"Resource Result: {content[0].text}")
            # Local MCP server prompt call
            messages = await client.get_prompt("useful_helper_prompt", {"lang": "java"})
            print("*******************************")
            print(messages.messages[0].content.text)
        elif args.transport == "all":
            # Local MCP server Tool call
            result = await client.call_tool("test_server_multiply", {"a": 5, "b": 3})
            print("*******************************")
            print(f"Result: {result.content[0].text}")
            # Local MCP server static Resource call
            content = await client.read_resource("config://test_server/version")
            print("*******************************")
            print(f"Resource Result: {content[0].text}")
            # Local MCP server Dynamic Resource call
            content = await client.read_resource("users://test_server/5432/profile")
            print("*******************************")
            print(f"Resource Result: {content[0].text}")
            # Local MCP server prompt call
            text_data = "very long paragraph from curl output"
            messages = await client.get_prompt("test_server_summarize_request", {"text": text_data})
            print("*******************************")
            print(messages.messages[0].content.text)
            # Remote HTTP MCP server tool call
            wiki_data = await client.call_tool(
                "deep_wiki_read_wiki_contents", {"repoName": "wonderwhy-er/DesktopCommanderMCP"}
            )
            print("*******************************")
            print(wiki_data)
            # MCP SSE server tool call
            data = await client.call_tool("linux_admin_run_command", {"command": "df -h"})
            print("*******************************")
            print(data.content[0].text)
            # Local HTTP MCP server - file_server tool call
            data = await client.call_tool("file_server_list_files", {"directory": ".", "pattern": "*"})
            print("*******************************")
            print(data.content[0].text)


def parse_cmd(argv):
    cp = argparse.ArgumentParser()
    # cp.add_argument("--mcp_server", help="mcp stdio server program",required=True)
    cp.add_argument("--mcp_server", help="mcp stdio server program", default="mcp_test_server.py")
    cp.add_argument(
        "--transport",
        default="stdio",
        help="mcp transport type",
        choices=["stdio", "http", "sse", "remote_http", "all"],
    )
    # cp.add_argument("--llmhost", required=True)
    # cp.add_argument("--model", default="llama3.1:latest")
    return cp.parse_args(argv[1:])


if __name__ == "__main__":
    asyncio.run(main())
