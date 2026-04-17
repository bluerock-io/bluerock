# BlueRock MCP Event Reference

All events are written as NDJSON to `~/.bluerock/event-spool/python-{pid}-{tid}.{generation}.ndjson`. Each line is a timestamped envelope:

```json
{"ts": "2026-03-22T10:00:00Z", "event": { "meta": {...}, "context": {...}, ...attributes... }}
```

## Universal Meta Fields

Every event includes these fields in `event.meta`:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Event type (e.g., `python_mcp_event`, `python_mcp_server_init`) |
| `type` | string | `"event"` (actionable) or `"nonactionable"` or `"sensor_lifecycle"` |
| `origin` | string | Always `"bluepython"` |
| `sensor_id` | integer | Sensor instance identifier |
| `source_event_id` | integer | Monotonically increasing per-process counter |
| `uuid` | string | Entity UUID for cross-sensor correlation |

Context fields in `event.context`:

| Field | Type | Description |
|-------|------|-------------|
| `context.process.pid` | integer | Process ID |

---

## MCP Events

### Event `python_mcp_server_init`

Emitted when a FastMCP/MCPServer instance is created.

| Attribute | Type | Description |
|-----------|------|-------------|
| `server.name` | string | Server name (from `FastMCP("name")`) |
| `server.title` | string | Server title, if provided |
| `server.description` | string | Server description, if provided |
| `server.version` | string | Server version |
| `server.instructions` | string | Server instructions, if provided |
| `entity_id` | string | Component UUID for cross-process correlation |

### Event `python_mcp_server_add`

Emitted when a tool, resource, or prompt is registered on the server.

| Attribute | Type | Description |
|-----------|------|-------------|
| `element.type` | string | `"tool"`, `"resource"`, or `"prompt"` |
| `element.name` | string | Registered element name |
| `element.title` | string | Element title, if provided |
| `element.description` | string | Element description |
| `element.parameters` | object | Parameter schema (tools only) |
| `element.uri` | string | Resource URI (resources only) |
| `element.arguments` | array | Prompt arguments (prompts only) |
| `entity_id` | string | Component UUID |

### Event `python_mcp_event`

Emitted on every MCP protocol request, response, and notification. The `event` field distinguishes 10 sub-types.

| Attribute | Type | Description |
|-----------|------|-------------|
| `event` | string | Sub-type (see table below) |
| `id` | integer | MCP request ID |
| `message` | object | Full JSON-RPC message body |
| `entity_id` | string | Component UUID of the emitting process |
| `client_id` | string | Client component UUID (server-side events) |
| `session_id` | string | MCP session UUID |
| `source` | integer | `0` = server, `1` = client |
| `server_name` | string | Server name (for tagging) |

**Sub-types:**

| `event` value | Direction | Description |
|---------------|-----------|-------------|
| `server_received_request` | client -> server | Incoming tool call, resource read, prompt request |
| `server_send_response` | server -> client | Tool result, resource content, prompt messages |
| `server_received_notification` | client -> server | Client notifications |
| `server_send_notification` | server -> client | Server notifications |
| `client_send_request` | client -> server | Outgoing tool call, resource read |
| `client_received_response` | server -> client | Received tool result, resource content |
| `client_send_notification` | client -> server | Client-side notifications |
| `client_received_notification` | server -> client | Server notifications received by client |
| `client_received_request` | server -> client | Server-initiated requests (sampling, roots) |
| `client_send_response` | client -> server | Client responses to server requests |

### Event `python_mcp_session_created`

Emitted when a client or server MCP session is initialized.

| Attribute | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Component UUID |
| `session_id` | string | MCP session UUID |
| `source` | integer | `0` = server session, `1` = client session |

### Event `python_mcp_session_terminated`

Emitted when a client or server MCP session ends.

| Attribute | Type | Description |
|-----------|------|-------------|
| `entity_id` | string | Component UUID |
| `client_id` | string | Client component UUID (server-side only) |
| `session_id` | string | MCP session UUID |
| `source` | integer | `0` = server session, `1` = client session |

### Event `python_mcp_client_connect`

Emitted when a client initiates a transport connection.

| Attribute | Type | Description |
|-----------|------|-------------|
| `server.type` | string | Transport: `"stdio"`, `"http"`, `"sse"`, `"websocket"` |
| `server.command` | string | Command (stdio only) |
| `server.args` | array | Command arguments (stdio only) |
| `server.url` | string | Server URL (http/sse/websocket only) |
| `server.auth` | boolean | Whether authentication is configured (http/sse only) |
| `entity_id` | string | Component UUID |

---

## Lifecycle Events

### Event `sensor_startup`

Emitted once when bluepython initializes.

| Attribute | Type | Description |
|-----------|------|-------------|
| `pid` | integer | Process ID |

### Event `python_internal_exception`

Emitted when an unexpected error occurs inside the sensor.

| Attribute | Type | Description |
|-----------|------|-------------|
| `type` | string | Exception description |
| `traceback` | string | Full Python traceback |

---

> **Remediation:** This release is monitoring-only. Policy enforcement and remediation (e.g., blocking a tool call, filtering resources based on server policy) are available in the [full version](https://www.bluerock.io/try-bluerock).

> **Coming soon:** events for subprocesses, serialization, web frameworks, LLM APIs, and more. See [CONFIG.md](acoustic/python/CONFIG.md) for the full roadmap.
