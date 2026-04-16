# MCP Examples

BlueRock MCP monitoring examples demonstrating runtime protection across all three MCP transports.

## Scripts

| Script | Transport | Description |
|--------|-----------|-------------|
| `mcp_test_server.py` | stdio | Basic server with tools, resources, and prompts |
| `mcp_client.py` | stdio/http/sse | Generic multi-transport client |
| `mcp_file_server.py` | http | File operations server with JWT auth |
| `mcp_linux_admin.py` | sse | Shell command execution server |
| `weatherMCP-server.py` | stdio | Real-world async server (NWS weather API) |
| `weatherMCP-client.py` | stdio | LLM-powered weather client (requires ollama) |

## Quick Start

### Stdio (simplest)

```bash
# Run the test server under BlueRock monitoring
python mcp_client.py --mcp_server mcp_test_server.py --transport stdio

# Events written to ~/.bluerock/event-spool/*.ndjson
```

### HTTP with auth

```bash
# Start the file server (separate terminal)
python mcp_file_server.py

# Connect with the generic client
python mcp_client.py --transport http --mcp_auth_token dev-test-token
```

### SSE

```bash
# Start the linux admin server (separate terminal)
python mcp_linux_admin.py

# Connect with the generic client
python mcp_client.py --transport sse
```

## Requirements

```
mcp>=1.0
fastmcp>=0.1
httpx  # for weatherMCP-server
```

## Events

BlueRock captures 6 MCP event types:

- `python_mcp_server_init` -- server startup
- `python_mcp_server_add` -- tool/resource/prompt registration
- `python_mcp_event` -- request/response/notification traffic
- `python_mcp_session_created` -- session lifecycle start
- `python_mcp_session_terminated` -- session lifecycle end
- `python_mcp_client_connect` -- transport connection (stdio/http/sse/websocket)
