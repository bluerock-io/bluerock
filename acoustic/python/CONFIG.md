# Python Sensor Configuration Reference

The `SensorConfig` class (in `cfg.py`) controls which instrumentation hooks are active. All options are disabled by default. The top-level `enable` key must be `true` for any sensor to activate.

Options can be set as a boolean (`true`/`false`) or as an object with an `enable` key plus option-specific sub-fields (e.g., `{"enable": true, "log_prompts": false}`).

## MCP Quick Start (v0.1.0)

For MCP-only monitoring, use this minimal config:

```json
{
  "enable": true,
  "mcp": true
}
```

Save as `~/.bluerock/bluerock-oss.json`. The sensor auto-discovers this path in `--oss` mode.

The `mcp` option instruments the `mcp` and `fastmcp` Python packages, capturing tool calls, resource access, prompt requests, session lifecycle, and transport connections. See [EVENTS.md](EVENTS.md) for the 6 MCP event types.

> **Note:** This release is monitoring-only. Policy enforcement and remediation are available in the [full version](https://www.bluerock.io/try-bluerock).

## OSS Config Options (v0.1.0)

These options are available in the open-source release:

| Option | Category | What it instruments |
| --- | --- | --- |
| `enable` | Global | Master switch — if `false`, all sensors are disabled regardless of individual settings |
| `cfg_dir` | Global | Directory containing the config file named `bluerock-oss.json` |
| `mcp` | AI agents | Model Context Protocol: tracks tool, resource, and messages |
| `imports` | Supply chain | Custom `MetaPathFinder` in the import system; computes SHA-256 of every imported file and maps it to its package; detects hash changes between runs |
| `debug` | Diagnostics | Enables verbose diagnostic output from the sensor itself to stderr |
| `log_file` | Diagnostics | Routes low-level sensor traces to a file path (set value to the desired path) |
| `log_stderr` | Diagnostics | Routes low-level sensor traces to stderr |

## Full Version Config Options

The following options require the [full version](https://www.bluerock.io/try-bluerock). They are recognized by the sensor config parser but are not active in the OSS release.

| Option | Category | What it instruments |
| --- | --- | --- |
| `a2a` | AI agents | Agent-to-Agent (A2A) protocol: hooks JSON-RPC transport methods (`send_message`, `send_message_streaming`, `get_task`, `cancel_task`, callback management) and HTTP card exchange |
| `aiohttp` | HTTP | `aiohttp.ClientSession` HTTP methods and `FileResponse`/`BaseRequest` init; checks URLs for path traversal patterns |
| `anthropic` | LLM | `anthropic.BaseClient._build_request` and response processing |
| `crewai` | AI agents | CrewAI framework lifecycle: `Task.execute_*`, `Agent.execute_task`, `Crew.kickoff/train/test`, `LLM.call`, `BaseTool.run`, memory operations |
| `django` | HTTP | `django.core.handlers.base.BaseHandler.get_response`; checks URL path and query string for suspicious patterns |
| `execs` | Process | Audit-hook monitoring of `os.system`, `os.posix_spawn`, `os.spawn`, `subprocess.Popen`, `pty.spawn`; warns when Python subprocesses run without the sensor |
| `flask` | HTTP | `Flask.__call__` (WSGI entry point); extracts path and query string from the WSGI environment and checks for suspicious patterns |
| `gemini` | LLM | Google Generative AI client request/response cycle |
| `http_requests_monitor` | HTTP | General HTTP request monitoring (reserved / not yet active) |
| `httpx` | HTTP | `httpx.AsyncClient.send` and `httpx.Client.send`; captures method and URL for every request |
| `langchain` | AI agents | LangChain callback system: chain start/end/error, LLM calls, tool/agent execution, token usage, memory operations |
| `litellm` | LLM | provider-agnostic extraction of request and response data |
| `loads` | Code execution | Dynamic code loading: `marshal.loads/load` (bytecode deserialization), `ctypes.dlopen/dlsym` (native library loading) |
| `openai` | LLM | `openai.BaseClient._build_request` and response processing |
| `opentelemetry` | Observability | Registers a `_BluerockSpanProcessor` with `TracerProvider.__init__`; converts OpenTelemetry spans into custom events |
| `pathjoin` | Security | `os.path.join`, `pathlib.Path.joinpath`, `os.path.abspath/normpath/realpath`, `pathlib.Path.resolve`; flags absolute-path components that could escape the intended root |
| `pathtraversal` | Security | `open()`, `os.open`, `pathlib.Path.open`; checks paths for traversal patterns; correlates file opens with recent HTTP request URLs |
| `pickle` | Security | Opcode analysis; builds an object construction graph to identify dangerous deserialization patterns |
| `profiling` | Diagnostics | Wraps instrumented functions with timing; tracks min/max/count; dumps aggregate statistics at process exit |
| `symlink` | Security | Audit-hook on `os.symlink`; checks the link source for path traversal patterns |
| `tracing` | Code execution | Bytecode-level tracing, logs each function call |
| `urllib` | HTTP | parses URL for policy evaluation |
| `uvicorn` | HTTP | captures HTTP method and URL at the ASGI server level |
| `web_server` | HTTP | General web-server monitoring (reserved / not yet active) |
| `zip_slip` | Security | Archive extraction: checks member names for path traversal before extraction |

## Configuration format

The sensor configuration is loaded from the JSON object stored in the sensor config file (`bluerock-oss.json` from the config directory). Example:

**OSS example** (only uses active options):

```json
{
  "enable": true,
  "mcp": true,
  "imports": true,
  "debug": false
}
```

**Full version example** (all options available):

```json
{
  "enable": true,
  "imports": true,
  "execs": true,
  "pathtraversal": true,
  "zip_slip": true,
  "openai": true,
  "langchain": { "enable": true, "log_prompts": false },
  "debug": false
}
```

Unknown keys cause an immediate `sys.exit(1)` to prevent silent misconfiguration.
