"""Interactive MCP REPL — type tool calls, see events flow live.

Run:
    python -m bluepython --oss repl_mcp.py

Commands:
    tools                  list available tools
    add <a> <b>            call add(a, b)
    greet <name>           call greet(name)
    resource <uri>         read a resource (e.g. config://version)
    list-resources         list all resources
    prompts                list available prompts
    help                   show this help
    quit                   exit
"""
import asyncio
import os
import shlex
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HELP = """\
commands:
  tools                  list available tools
  add <a> <b>            call add tool
  greet <name>           call greet tool
  resource <uri>         read a resource (e.g. config://version)
  list-resources         list resources
  prompts                list prompts
  quit                   exit
"""


async def repl():
    server_script = os.path.join(os.path.dirname(__file__), "mcp_server.py")
    cfg_dir = os.path.join(os.path.expanduser("~"), ".bluerock")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "bluepython", "--oss", "--cfg-dir", cfg_dir, server_script],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP session ready. Type 'help' or 'quit'.\n")
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
                    elif cmd == "add":
                        a, b = int(args[0]), int(args[1])
                        r = await session.call_tool("add", {"a": a, "b": b})
                        print(r.content[0].text)
                    elif cmd == "greet":
                        r = await session.call_tool("greet", {"name": args[0]})
                        print(r.content[0].text)
                    elif cmd == "resource":
                        r = await session.read_resource(args[0])
                        print(r.contents[0].text)
                    elif cmd == "list-resources":
                        r = await session.list_resources()
                        print([str(x.uri) for x in r.resources])
                    elif cmd == "prompts":
                        r = await session.list_prompts()
                        print([p.name for p in r.prompts])
                    else:
                        print(f"unknown command '{cmd}' — type 'help'")
                except IndexError:
                    print(f"missing args — type 'help'")
                except Exception as e:
                    print(f"error: {e}")


if __name__ == "__main__":
    asyncio.run(repl())
