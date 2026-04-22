# BlueRock

Runtime security sensor for Python applications. Monitors MCP protocol interactions and module imports — emitting structured NDJSON events for every operation, with zero code changes.

## Install

```bash
python3 -m venv venv && source venv/bin/activate
pip install bluerock[oss]
```

This installs:
- **bluerock** — Python sensor (hooks, instrumentation, CLI)
- **bluerock-oss** — Rust DSO backend that handles event writing

## Quick Start

Create a sensor config and run any Python script under BlueRock:

```bash
mkdir -p ~/.bluerock
echo '{"enable": true, "mcp": true, "imports": true}' > ~/.bluerock/bluerock-oss.json
python -m bluepython --oss --cfg-dir ~/.bluerock your_script.py
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

### Framework hooks (zero overhead if not imported)

| Framework | Events |
|-----------|--------|
| **MCP** | `python_mcp_event`, `python_mcp_server_init`, `python_mcp_server_add`, `python_mcp_session_created`, `python_mcp_session_terminated`, `python_mcp_client_connect` |

MCP hooks use `@wrapt.when_imported()` — loaded only when your application imports `mcp` or `fastmcp`.

> **Want more?** The [full version](https://www.bluerock.io/try-bluerock) supports 30+ hook categories covering process spawns, dynamic code execution, serialization, HTTP frameworks, LLM APIs, and more.

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
    }
  }
}
```

## CLI Reference

```
python3 -m bluepython --oss [OPTIONS] [script.py | -m module] [args...]

Options:
  --oss                Use OSS backend (also auto-detected when bluerock-oss is installed)
  --cfg-dir DIR        Load sensor config from DIR/bluerock-oss.json (see CONFIG.md)
  -m MODULE            Run a Python module instead of a script
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
