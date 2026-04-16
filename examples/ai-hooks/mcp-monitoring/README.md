# How to Monitor MCP Protocol Activity

This example shows how BlueRock instruments the Model Context Protocol (MCP), capturing server initialization, tool registration, and tool invocations as structured events.

The example consists of two files:
- `mcp_server.py` — a minimal FastMCP server with two tools (`add` and `greet`)
- `mcp_client.py` — connects to the server over stdio transport and calls both tools

## Prerequisites

```bash
pip install bluerock[oss] mcp
```

## Run

Run the client, which launches the server as a BlueRock-instrumented subprocess:

```bash
python -m bluepython --oss --cfg-dir ~/.bluerock mcp_client.py
```

You should see output like:

```
Available tools: ['add', 'greet']
add(2, 3) = 5
greet = Hello, BlueRock!
```

## Read the Events

The client and server run in separate processes, so events are written to separate NDJSON files (one per PID). To see all events:

```bash
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name | startswith("python_mcp"))'
```

To see only server-side events:

```bash
cat ~/.bluerock/event-spool/python-*.ndjson \
  | jq '.event | select(.meta.name == "python_mcp_server_init" or .meta.name == "python_mcp_server_add")'
```

## What to Expect

Three categories of MCP events are emitted:

**Server initialization** — when FastMCP starts:

```jsonc
{
  "meta": {
    "name": "python_mcp_server_init",    // server started
    "type": "event",
    "origin": "bluepython",
    "sensor_id": "...",
    "source_event_id": "..."
  },
  "context": { "process": { ... } }
}
```

**Tool registration** — for each `@mcp.tool()` decorator:

```jsonc
{
  "meta": {
    "name": "python_mcp_server_add",     // tool registered
    "type": "event",
    "origin": "bluepython",
    "sensor_id": "...",
    "source_event_id": "..."
  },
  "context": { "process": { ... } }
}
```

**Protocol events** — for client/server message exchange:

```jsonc
{
  "meta": {
    "name": "python_mcp_event",          // tool called
    "type": "event",
    "origin": "bluepython",
    "sensor_id": "...",
    "source_event_id": "..."
  },
  "context": { "process": { ... } }
}
```

| Event | When It Fires |
|-------|---------------|
| `python_mcp_server_init` | Server process starts and FastMCP initializes |
| `python_mcp_server_add` | Each tool is registered with the server |
| `python_mcp_event` | Client sends a request, server receives/responds |

## How It Works

BlueRock uses `@wrapt.when_imported("mcp")` to hook the FastMCP server class. Server lifecycle events (`init`, tool registration) are captured by patching the `FastMCP` constructor and `tool()` decorator. Protocol-level events are captured by instrumenting the JSON-RPC transport layer.

The client script launches the server under `python -m bluepython --oss`, so the server subprocess is also instrumented. Both processes write to `~/.bluerock/event-spool/`, each with its own PID-stamped NDJSON file.

## Platform Notes

> **Subprocess PID handling:** The server runs as a child process with its own PID. On both Linux and macOS, you'll see two sets of NDJSON files — one for the client PID and one for the server PID. Use `jq '.context.process.pid'` to distinguish them.

> **stdio transport:** The MCP client-server communication uses stdin/stdout pipes. This is platform-independent and works identically on Linux and macOS.
