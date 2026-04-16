# BlueRock Cookbook

Runnable examples demonstrating BlueRock's runtime security hooks. Each example is a self-contained script that produces NDJSON events you can inspect with `jq`.

## Prerequisites

Create a virtualenv and install BlueRock (see the [main README](../README.md#install) for full instructions):

```bash
python3 -m venv venv && source venv/bin/activate
# install from release wheels or build from source — see README
pip install mcp fastmcp
```

Verify the installation:

```bash
python -m bluepython --help
```

## Running an Example

1. Create a sensor config file:

   ```bash
   mkdir -p ~/.bluerock
   echo '{"enable": true, "mcp": true, "imports": true}' > ~/.bluerock/bluerock-oss.json
   ```

2. `cd` into the example directory and install its dependencies (if any):

   ```bash
   cd examples/mcp
   ```

3. Run the script under BlueRock:

   ```bash
   python -m bluepython --oss --cfg-dir ~/.bluerock mcp_test_server.py
   ```

4. Read the events:

   ```bash
   cat ~/.bluerock/event-spool/python-*.ndjson | jq .event
   ```

> **Note:** Events are written to `~/.bluerock/event-spool/` on both Linux and macOS.

## Examples

### MCP Events Captured

Running any example under `python -m bluepython --oss` emits these events:

| Event | What It Captures |
|-------|-----------------|
| `python_mcp_server_init` | Server lifecycle — name, version at startup |
| `python_mcp_server_add` | Tool/resource/prompt registration — element name, type, parameters |
| `python_mcp_event` | Protocol messages — requests, responses, notifications with session + direction |
| `python_mcp_session_created` | Session opens — session ID |
| `python_mcp_session_terminated` | Session closes — session ID |
| `python_mcp_client_connect` | Client connects — transport type (stdio/http/sse), URL or command |
| `python_import` | Every module import — name, file path, SHA-256 hash, installed version |

### Import Monitoring

| Example | What It Demonstrates |
|---------|---------------------|
| [Import Monitoring](core-hooks/import-monitoring/) | Tracks every `import` with SHA-256 hash, version, and file path — detects tampered packages |

See [core-hooks/import-monitoring/README.md](core-hooks/import-monitoring/README.md) for the full walkthrough with `jq` queries.

### MCP Examples

| Example | What It Demonstrates | Transport |
|---------|---------------------|-----------|
| [MCP Test Server](mcp/mcp_test_server.py) | Minimal server with tool + resource + prompt | stdio |
| [MCP Client](mcp/mcp_client.py) | Multi-transport generic client | stdio / HTTP / SSE |
| [MCP File Server](mcp/mcp_file_server.py) | File operations server with token auth | HTTP |
| [MCP Linux Admin](mcp/mcp_linux_admin.py) | System administration server | SSE |
| [Weather Server](mcp/weatherMCP-server.py) | External API integration server | stdio |
| [Weather Client](mcp/weatherMCP-client.py) | Weather query client (uses ollama) | stdio |

See [mcp/README.md](mcp/README.md) for detailed per-example instructions.

### Quick MCP Demo (stdio)

| Example | What It Demonstrates |
|---------|---------------------|
| [MCP Server](ai-hooks/mcp-monitoring/mcp_server.py) | Simple server — tools, resources, prompts |
| [MCP Client](ai-hooks/mcp-monitoring/mcp_client.py) | Client that connects, calls tools, reads resources |

See [ai-hooks/mcp-monitoring/README.md](ai-hooks/mcp-monitoring/README.md) for a step-by-step walkthrough.

> **More hook categories** (process spawns, HTTP frameworks, LLM APIs, serialization, and more) are available in the [full version](https://try.bluerock.io).

## Test Runner

Validate all examples with the included test runner:

```bash
python examples/run-examples.py
```

The runner creates a temporary config directory with `bluerock-oss.json`, executes each script under `python -m bluepython --oss --cfg-dir <tmpdir>`, parses the NDJSON output, and verifies the expected events were emitted.

| Flag | Effect |
|------|--------|
| `--quiet` / `-q` | Suppress subprocess stdout/stderr |
| `--select` / `-s` | Run only examples matching a prefix (e.g., `-s mcp`) |

Examples with missing optional dependencies are automatically skipped.

## Platform Notes

| | Linux | macOS |
|--|-------|-------|
| **Supported architectures** | x86_64, aarch64 | x86_64 (Intel), arm64 (Apple Silicon) |
| **Wheel format** | manylinux_2_28 | macOS 11+ universal |
| **Event output path** | `~/.bluerock/event-spool/` | `~/.bluerock/event-spool/` |
| **Python requirement** | >= 3.10 | >= 3.10 |

> **Windows** is not currently supported. The `bluerock-oss` DSO is a native shared library (`.so` on Linux, `.dylib` on macOS).
