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

First, create a sensor config if you haven't already:

```bash
mkdir -p ~/.bluerock
echo '{"enable": true, "mcp": true, "imports": true}' > ~/.bluerock/bluerock-oss.json
```

### Stdio (simplest)

```bash
cd examples/mcp/
python -m bluepython --oss mcp_client.py --mcp_server mcp_test_server.py --transport stdio

# Events written to ~/.bluerock/event-spool/*.ndjson
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name | startswith("python_mcp_"))'
```

### HTTP with auth

```bash
cd examples/mcp/

# Start the file server (separate terminal)
python -m bluepython --oss mcp_file_server.py

# Connect with the generic client
python -m bluepython --oss mcp_client.py --transport http --mcp_auth_token dev-test-token
```

### SSE

```bash
cd examples/mcp/

# Start the linux admin server (separate terminal)
python -m bluepython --oss mcp_linux_admin.py

# Connect with the generic client
python -m bluepython --oss mcp_client.py --transport sse
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
