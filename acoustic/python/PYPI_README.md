# BlueRock

Runtime security sensor for Python applications. Monitors imports, process execution, dynamic code loading, deserialization, network calls, and AI framework interactions — emitting structured NDJSON events for every operation.

## Install

```bash
python3 -m venv venv && source venv/bin/activate
pip install bluerock[oss]
```

This installs:
- **bluerock** — Python sensor (hooks, instrumentation, CLI)
- **bluerock-oss** — Rust DSO backend that handles event writing

## Quick Start

Run any Python script under BlueRock:

```bash
python -m bluepython --oss your_script.py
```

Events are written to `~/.bluerock/event-spool/python-{pid}-{tid}.{generation}.ndjson`:

```bash
cat ~/.bluerock/event-spool/python-*.ndjson | jq .event
```

## What Gets Monitored

### Core hooks (always active)

| Category | Events |
|----------|--------|
| **Imports** | `python_import` — name, path, version, SHA256 |
| **Dynamic code** | `python_builtins_exec` — eval/exec calls |
| **Process spawn** | `python_os_system`, `python_subprocess_Popen` |
| **ctypes** | `python_ctypes_dlopen`, `python_ctypes_dlsym` |
| **Deserialization** | `python_pickle_find_class`, `python_pickle_reduce` |
| **Archives** | `python_zip_slip` — zip/tar path traversal |

### Framework hooks (zero overhead if not imported)

| Framework | Events |
|-----------|--------|
| **Flask** | `python_flask_call` |
| **httpx** | `python_http_request` |
| **Django** | `python_django_call` |
| **MCP** | `python_mcp_event` |
| **LangChain** | `python_langchain_event`, `python_langgraph_event` |
| **CrewAI** | `python_crewai_event` |
| **OpenAI/Anthropic/Gemini** | `python_llm_call`, `python_llm_reply` |
| **OpenTelemetry** | `python_otel_span` |

Framework hooks use `@wrapt.when_imported()` — loaded only when your application imports the framework.

## Event Format

Every line in the NDJSON log is a timestamped envelope wrapping an event. Use `jq .event` to unwrap:

```json
{
  "ts": "2026-04-02T10:00:00.123456Z",
  "event": {
    "meta": {
      "name": "python_mcp_server_add",
      "type": "event",
      "origin": "bluepython",
      "sensor_id": 1,
      "source_event_id": 5,
      "uuid": "component-uuid-v4"
    },
    "context": {
      "process": { "pid": 12345 }
    },
    "element": {
      "type": "tool",
      "name": "add",
      "description": "Add two numbers."
    },
    "entity_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

## CLI Reference

```
python3 -m bluepython --oss [OPTIONS] [script.py | -m module] [args...]

Options:
  --oss                Use OSS (bluerock_oss) DSO — required for pip-installed bluerock
  --cfg-dir DIR        Load sensor config from DIR/bluerock-oss.json (see CONFIG.md)
  -m MODULE            Run a Python module instead of a script
  -p, --path-traversal Enable path traversal event detection
  --debug              Print debug logs to stderr
  --install            Install bluerock autostart (sitecustomize)
  --uninstall          Remove bluerock autostart
```

## Links

- [Full Documentation](https://github.com/bluerock-io/bluerock#readme)
- [Cookbook Examples](https://github.com/bluerock-io/bluerock/tree/main/examples)
- [Event Schema Reference](https://github.com/bluerock-io/bluerock/blob/main/acoustic/python/EVENTS.md)
- [Contributing Guide](https://github.com/bluerock-io/bluerock/blob/main/CONTRIBUTING.md)

## Requirements

- Python >= 3.10 (tested up to 3.13)
- Linux (x86_64, aarch64) or macOS (Intel, Apple Silicon)

## License

[Apache 2.0](https://github.com/bluerock-io/bluerock/blob/main/LICENSE)
