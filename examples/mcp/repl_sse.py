"""Interactive MCP REPL for the linux-admin SSE server.

Connects to a running mcp_linux_admin.py instance and lets you drive
its tools, resources, and prompts interactively. Each command typed at
the prompt produces a fresh python_mcp_event in the event spool.

Usage:
    1. Start the server in a separate pane (long-running):
         python -m bluerock --oss mcp_linux_admin.py
    2. Connect with this REPL:
         python -m bluerock --oss repl_sse.py
       (or pass --url to point at a different host/port)

Commands:
    tools                  list available tools
    run <command>          call run_command tool (shell exec)
    curl <url>             call curl_tool tool (HTTP fetch)
    resource <file>        read file resource (e.g. resource sample.txt)
    list-resources         list resources
    prompts                list prompts
    prompt <lang>          get useful_helper_prompt for a language
    help
    quit
"""
import argparse
import asyncio
import shlex

from mcp import ClientSession
from mcp.client.sse import sse_client


HELP = """\
commands:
  tools                  list available tools
  run <command>          call run_command (shell exec)
  curl <url>             call curl_tool (HTTP fetch)
  resource <file>        read text resource (e.g. resource sample.txt)
  list-resources         list resources
  prompts                list prompts
  prompt <lang>          get useful_helper_prompt for a language
  quit
"""


async def repl(url: str):
    async with sse_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"Connected to MCP server at {url}.")
            print("Type 'help' or 'quit'.\n")
            loop = asyncio.get_running_loop()
            while True:
                try:
                    line = await loop.run_in_executor(None, lambda: input("mcp> "))
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    parts = shlex.split(line)
                except ValueError as e:
                    print(f"parse error: {e}")
                    continue
                cmd, args = parts[0], parts[1:]
                try:
                    if cmd in ("quit", "exit", "q"):
                        break
                    elif cmd == "help":
                        print(HELP)
                    elif cmd == "tools":
                        r = await session.list_tools()
                        print([t.name for t in r.tools])
                    elif cmd == "run":
                        command = " ".join(args)
                        if not command:
                            print("usage: run <command>")
                            continue
                        r = await session.call_tool("run_command", {"command": command})
                        print(r.content[0].text)
                    elif cmd == "curl":
                        if not args:
                            print("usage: curl <url>")
                            continue
                        r = await session.call_tool("curl_tool", {"url": args[0]})
                        text = r.content[0].text
                        # truncate big responses for terminal legibility
                        if len(text) > 600:
                            print(text[:600] + "\n... (truncated)")
                        else:
                            print(text)
                    elif cmd == "resource":
                        if not args:
                            print("usage: resource <file>")
                            continue
                        uri = f"file://read/{args[0]}"
                        r = await session.read_resource(uri)
                        print(r.contents[0].text)
                    elif cmd == "list-resources":
                        r = await session.list_resources()
                        print([str(x.uri) for x in r.resources])
                    elif cmd == "prompts":
                        r = await session.list_prompts()
                        print([p.name for p in r.prompts])
                    elif cmd == "prompt":
                        if not args:
                            print("usage: prompt <lang>")
                            continue
                        r = await session.get_prompt("useful_helper_prompt", {"lang": args[0]})
                        print(r.messages[0].content.text)
                    else:
                        print(f"unknown command '{cmd}' — type 'help'")
                except IndexError:
                    print("missing args — type 'help'")
                except Exception as e:
                    print(f"error: {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--url",
        default="http://127.0.0.1:8002/sse",
        help="SSE server URL (default: %(default)s)",
    )
    args = p.parse_args()
    asyncio.run(repl(args.url))


if __name__ == "__main__":
    main()
