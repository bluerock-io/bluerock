# BlueRock

[![PyPI](https://img.shields.io/pypi/v/bluerock)](https://pypi.org/project/bluerock/)
[![Python](https://img.shields.io/pypi/pyversions/bluerock)](https://pypi.org/project/bluerock/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

**Lightweight runtime security sensor for Python.** Monitor MCP tool calls, resource access, session lifecycle, and module imports your application makes, with zero code changes, emitting structured events for every operation.

```bash
pip install bluerock[oss]
python -m bluepython --oss --cfg-dir ~/.bluerock your_script.py
cat ~/.bluerock/event-spool/python-*.ndjson | jq .event
```

BlueRock wraps your Python process and emits structured NDJSON events for security-sensitive operations. It hooks into Python at startup, before your code runs, so nothing slips through. Your code, your dependencies, and their transitive dependencies are all in scope.

Built for security teams, AppSec engineers, and anyone who wants to know what their Python applications are actually doing at runtime.

| | BlueRock | Manual logging | OpenTelemetry |
|---|---|---|---|
| Code changes | None | Instrument every call | Add spans/traces |
| Covers dependencies | Yes (transitive) | Only what you wrap | Only what you wrap |
| AI/MCP monitoring | Built-in (6 event types) | DIY | No |
| Import verification | SHA256 per module | No | No |
| Output format | NDJSON (structured) | Ad-hoc | OTLP |

## Requirements

| Dependency | Version |
|---|---|
| Python | >= 3.10 (MCP hooks require 3.10+) |
| Rust | stable toolchain (build from source only) |
| OS | Linux (x86_64, aarch64), macOS (arm64, x86_64) |
| Docker | optional, for the Grafana dashboard |

## Try It

```bash
# 1. Clone and set up
git clone https://github.com/bluerock-io/bluerock.git
cd bluerock
python3 -m venv venv && source venv/bin/activate

# 2. Install the sensor + MCP deps
pip install -e "acoustic/python/"
pip install setuptools-rust && pip install acoustic/python-oss/
pip install mcp fastmcp

# 3. Create a sensor config
mkdir -p ~/.bluerock
echo '{"enable": true, "mcp": true}' > ~/.bluerock/bluerock-oss.json

# 4. Run the MCP example (client launches a server, both are monitored)
cd examples/mcp/
python -m bluepython --oss mcp_client.py --transport stdio

# 5. See what happened
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event.meta.name' | sort | uniq -c | sort -rn
```

You should see events like `python_mcp_event`, `python_mcp_server_add`, `python_mcp_session_created`, `python_mcp_server_init`, and `python_mcp_client_connect` -- every MCP protocol interaction captured automatically.

**Try import monitoring too:**

```bash
# Enable imports in your config
echo '{"enable": true, "mcp": true, "imports": true}' > ~/.bluerock/bluerock-oss.json

# Run the import monitoring example
pip install requests
python -m bluepython --oss examples/core-hooks/import-monitoring/import_monitoring.py

# See every module loaded, with SHA-256 hashes
cat ~/.bluerock/event-spool/python-*.ndjson \
  | jq -r '.event | select(.meta.name == "python_import") | "\(.fullname) \(.version // "n/a") \(.sha256[0:16])..."'
```

## Why BlueRock

Most runtime instrumentation focuses on observability (tracing API calls, measuring latency, collecting metrics). BlueRock focuses on **security**: the operations that matter from a threat-detection perspective.

- **Zero code changes.** Wrap any script with `python -m bluepython --oss your_script.py`. No imports, no SDK integration required. A one-time [sensor config](#quick-start) enables the hooks you need.
- **Three-layer hooking.** `sys.addaudithook` for process spawns and ctypes, `sys.meta_path` for every module import (with SHA256 verification), `wrapt` for framework-specific operations. Each layer catches what the others can't.
- **Full MCP coverage.** Tool calls, resource access, prompt requests, session lifecycle, and transport connections across stdio, HTTP, and SSE.
- **Hooks before your code runs.** Instrumentation activates at Python startup. Operations from your code, your dependencies, and their transitive dependencies all emit events.
- **Open source.** Apache 2.0. Inspect the hooks, contribute new ones, integrate with your own tooling.

## What It Does

BlueRock instruments your Python application at runtime using two mechanisms:

- **`wrapt` monkey-patching** for imported libraries and frameworks. Hooks are applied lazily via `@wrapt.when_imported()`, so packages you don't use cost nothing.
- **`sys.addaudithook`** for built-in security-sensitive operations (process spawning, ctypes loading, symlink creation).

Every hooked operation emits a structured JSON event to an NDJSON log file at `~/.bluerock/event-spool/`. Events include full context: what was called, with what arguments, from which module, and the process ID.

```
┌──────────────────────────────────────────────────────────────┐
│  python -m bluepython --oss your_app.py                      │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│  │ audit hooks  │    │ import hooks │    │ framework hooks │  │
│  │ (subprocess, │    │ (SHA256,     │    │ (MCP, LLMs,    │  │
│  │  ctypes)     │    │  versions)   │    │  and more)     │  │
│  └──────┬───────┘    └──────┬───────┘    └───────┬─────────┘  │
│         └──────────────┬────┘────────────────────┘           │
│                        ▼                                     │
│              ┌─────────────────┐                             │
│              │ bluerock-oss    │  Rust DSO (libacoustic_oss) │
│              │ NDJSON writer   │                             │
│              └────────┬────────┘                             │
│                       ▼                                      │
│         ~/.bluerock/event-spool/*.ndjson                      │
└──────────────────────────────────────────────────────────────┘
                        │
          ┌─────────────┼──────────────────┐
          ▼             ▼                  ▼
     jq / grep    Grafana + Loki    Datadog / Splunk / SIEM
                  (included)        (via OTLP forwarding)
```

## Install

### Option A: Install from PyPI

```bash
python3 -m venv venv && source venv/bin/activate
pip install bluerock[oss]

python -m bluepython --help
python -c "import bluerock_oss; print('DSO:', bluerock_oss.get_dso_path())"
```

This installs two packages:
- `bluerock` — the Python sensor (hooks, instrumentation, CLI)
- `bluerock-oss` — the Rust DSO backend (`libacoustic_oss.so`) that handles event writing

### Option B: Install from GitHub release wheels

For air-gapped installs, or when a PyPI wheel for your platform isn't available, download both `.whl` files from the [latest release](../../releases/latest) — pick the `bluerock_oss` wheel matching your Python version and platform:

```bash
python3 -m venv venv && source venv/bin/activate

# install bluerock (pure Python sensor) + bluerock-oss (Rust DSO) from release wheels
pip install bluerock-<version>-py3-none-any.whl
pip install bluerock_oss-<version>-<cpXY>-<platform>.whl

python -m bluepython --help
python -c "import bluerock_oss; print('DSO:', bluerock_oss.get_dso_path())"
```

### Option C: Build from source

For development, contributing, or when a prebuilt wheel isn't available for your platform.

**Prerequisites:** Python >= 3.10, Rust toolchain, git, platform development tools (see step 2 below).

```bash
# 1. Clone the repository
git clone https://github.com/bluerock-io/bluerock.git
cd bluerock

# 2. Install platform development tools
#    Amazon Linux 2023:
sudo dnf groupinstall "Development Tools"
#    Ubuntu / Debian:
sudo apt install build-essential
#    openSUSE:
sudo zypper install -t pattern devel_basis

# 3. Install the Rust toolchain (skip if already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
export PATH="$HOME/.cargo/bin:$PATH"
rustup toolchain install stable --profile minimal

# 4. Create a virtualenv and install the Python sensor
python3 -m venv venv && source venv/bin/activate
pip install -e "acoustic/python/[test]"

# 5. Build and install bluerock-oss (compiles the Rust DSO from source)
pip install setuptools-rust
pip install acoustic/python-oss/

# 6. Install MCP + framework deps to run examples and tests
pip install mcp fastmcp

# 7. Verify
python -m bluepython --help
```

Both install methods produce the same result: a working `bluerock` + `bluerock-oss` installation. The sensor discovers the DSO automatically via the installed `bluerock_oss` Python package.

## Quick Start

Create a sensor config to enable the hooks you need:

```bash
mkdir -p ~/.bluerock
cat > ~/.bluerock/bluerock-oss.json << 'EOF'
{
  "enable": true,
  "imports": {"enable": true, "fileslist": true},
  "mcp": true
}
EOF
```

Run any Python script under BlueRock:

```bash
python -m bluepython --oss --cfg-dir ~/.bluerock your_script.py
```

Or run an MCP server module:

```bash
python -m bluepython --oss --cfg-dir ~/.bluerock your_mcp_server.py
```

See [CONFIG.md](acoustic/python/CONFIG.md) for all sensor options. In this release, only **MCP** and **Imports** are active. The remaining options listed in CONFIG.md require the [full version](https://try.bluerock.io).

Events are written to `~/.bluerock/event-spool/python-{pid}-{tid}.{generation}.ndjson`. Read them with `jq`:

```bash
# All events (each line is {"ts": "...", "event": {...}})
cat ~/.bluerock/event-spool/python-*.ndjson | jq .event

# Just imports
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name == "python_import")'

# Just process spawns
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name | startswith("python_os_"))'
```

### Example: NDJSON event trace

Running an MCP server produces events like these (one JSON object per line, wrapped in `{"ts", "event"}`):

```jsonc
// sensor startup (lifecycle event)
{"ts":"2026-04-02T10:00:00Z","event":{"meta":{"name":"sensor_startup","origin":"bluepython","sensor_id":1,"type":"sensor_lifecycle"},"pid":24241}}

// MCP server initialized
{"ts":"2026-04-02T10:00:00Z","event":{"context":{"process":{"pid":24241}},
 "meta":{"name":"python_mcp_server_init","origin":"bluepython","sensor_id":1,"type":"event"},
 "server":{"name":"test-mcp-server","version":"0.0.1"},"entity_id":"..."}}

// tool registered on the server
{"ts":"2026-04-02T10:00:00Z","event":{"context":{"process":{"pid":24241}},
 "meta":{"name":"python_mcp_server_add","origin":"bluepython","sensor_id":1,"type":"event"},
 "element":{"type":"tool","name":"add","description":"Add two numbers."},"entity_id":"..."}}
```

## CLI Reference

```
python3 -m bluepython --oss [OPTIONS] [script.py | -m module] [args...]

Options:
  --oss                Use the OSS backend (required for pip-installed bluerock)
  --cfg-dir DIR        Load sensor config from DIR/bluerock-oss.json (see CONFIG.md)
  -m MODULE            Run a Python module instead of a script
  -p, --path-traversal Enable path traversal event detection
  --debug              Print debug logs to stderr
  --install            Install bluerock autostart (sitecustomize)
  --uninstall          Remove bluerock autostart
```

### Programmatic usage

You can also import bluepython directly in your Python code. This is useful when you want to instrument a specific entry point without wrapping the entire process from the command line:

```python
import bluepython

# your MCP server code
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("my-server")

@mcp.tool()
def add(a: int, b: int) -> int:
    return a + b

mcp.run(transport="stdio")
```

When imported, bluepython activates its hooks in the current process. Events are written to `~/.bluerock/event-spool/` as usual.

### Persistent install (sitecustomize)

> **Note:** Persistent install is designed for the [full version](https://try.bluerock.io). For OSS users, use the `python -m bluepython --oss` prefix or `import bluepython` in your code.

## What Gets Monitored

### Active in this release

| Category | Events | What It Catches |
|----------|--------|-----------------|
| **MCP** | `python_mcp_server_init`, `python_mcp_server_add`, `python_mcp_event`, `python_mcp_session_created`, `python_mcp_session_terminated`, `python_mcp_client_connect` | Tool calls, resource access, prompt requests, session lifecycle, transport connections |
| **Imports** | `python_import` | Every module import with name, path, version, SHA256 |

Framework hooks use `@wrapt.when_imported()`. The hook module only loads when your application actually imports the framework. Combined with a per-feature config gate (`cfg.sensor_config.enabled("mcp")`), this means:

- Uninstalled framework = zero overhead (wrapt gate)
- Disabled feature = near-zero overhead (config gate)
- Enabled + installed = full monitoring

> **Want more?** BlueRock's sensor engine supports 30+ hook categories covering process spawns, dynamic code execution, serialization, HTTP frameworks, LLM APIs, and more. [Get in touch](https://try.bluerock.io) to enable the full suite.

### MCP events in detail

BlueRock captures 6 MCP event types covering the full protocol lifecycle:

| Event | When it fires | What you see |
|-------|---------------|-------------|
| `python_mcp_server_init` | Server starts up | Server name, version |
| `python_mcp_server_add` | Tool/resource/prompt registered | Element name, type, parameters |
| `python_mcp_event` | Any request, response, or notification | Full protocol message with session + direction |
| `python_mcp_session_created` | Client or server session opens | Session ID |
| `python_mcp_session_terminated` | Session closes | Session ID |
| `python_mcp_client_connect` | Client connects to a server | Transport type (stdio/http/sse), URL or command |

The `python_mcp_event` has 10 sub-types covering both directions -- see [EVENTS.md](acoustic/python/EVENTS.md) for the complete attribute schemas.

### Import events in detail

Every `import` statement produces a `python_import` event:

| Field | What you see |
|-------|-------------|
| `fullname` | Fully-qualified module name (e.g., `urllib3.util.retry`) |
| `sha256` | SHA-256 hash of the module file on disk — detects tampering between runs |
| `version` | Installed package version from metadata (when available) |
| `path` | Absolute filesystem path to the module |

This covers your code, your dependencies, AND their transitive dependencies. A single `import requests` generates events for `requests`, `urllib3`, `charset_normalizer`, `certifi`, and more — each with its own SHA-256 fingerprint.

See the [import monitoring example](examples/core-hooks/import-monitoring/) for a runnable demo with `jq` queries.

> **Note:** This release is monitoring-only. Policy enforcement and remediation (blocking tool calls, filtering resources) are available in the [full version](https://try.bluerock.io).

## Dashboard (Grafana + Loki)

BlueRock ships with a Grafana dashboard that visualizes events in real time. It runs locally via Docker Compose.

**You need:** Docker, Docker Compose, Docker buildx plugin >= 0.17.0, and [`just`](https://github.com/casey/just) (a command runner).

```bash
# Install just (if not already installed)
# macOS
brew install just

# Linux
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin
```

### Quick demo (no sensor needed)

Replays sample events so you can see the dashboard without running any MCP servers:

```bash
cd observe/spoolfile2loki
just build                                # or: docker build -t spoolfile2loki:latest .
cd ../deploy
./deploy.sh mock                          # start Grafana + Loki + sample data
```

Open [http://localhost:3000](http://localhost:3000) (login: `admin` / `admin`). The "BlueRock Acoustic" dashboard shows event timelines, tool call breakdowns, and session lifecycle panels.

### Live mode (real events from the sensor)

Point the dashboard at your actual event spool:

```bash
cd observe/deploy
./deploy.sh dir ~/.bluerock/event-spool
```

Now run any script under BlueRock in another terminal -- events appear in Grafana within seconds.

### Tear down

```bash
cd observe/deploy
./deploy.sh down        # removes containers and volumes
```

## Event Format

Every line in the NDJSON log is a timestamped envelope wrapping an event:

```json
{
  "ts": "2026-04-02T10:00:00.123456Z",
  "event": {
    "meta": {
      "name": "python_mcp_server_add",
      "type": "event",
      "origin": "bluepython",
      "sensor_id": 1,
      "source_event_id": 5
    },
    "context": {
      "process": { "pid": 12345 }
    },
    "element": {
      "type": "tool",
      "name": "add",
      "description": "Add two numbers.",
      "parameters": { "a": "integer", "b": "integer" }
    },
    "entity_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

Use `jq .event` to unwrap the envelope when reading events.

- `event.meta.name` — event type (see tables above)
- `event.meta.type` — `"event"` (actionable) or `"sensor_lifecycle"` (informational)
- `event.meta.source_event_id` — monotonically increasing per-process counter
- `event.context.process.pid` — process ID
- Remaining fields are event-specific (see [EVENTS.md](acoustic/python/EVENTS.md))

## Cookbook

See the [`examples/`](examples/) directory for runnable demos:

- **[Import monitoring](examples/core-hooks/import-monitoring/)** — track every module import with SHA-256 hash and version
- **[MCP examples](examples/mcp/)** — multi-transport examples (stdio, HTTP with auth, SSE), generic client, weather server
- **[MCP monitoring](examples/ai-hooks/mcp-monitoring/)** — simple client/server pair for quick testing

Each example is a self-contained script you run with `python -m bluepython --oss <script>.py`.

## Project Structure

```
acoustic/
  python-oss/          # Rust DSO (bluerock-oss on PyPI)
    src/lib.rs         # C ABI: acoustic_event, acoustic_get_sensor_config, ...
    bluerock_oss/      # Python wrapper: get_dso_path()
    Cargo.toml
    pyproject.toml
  python/
    bluepython/        # Python sensor (bluerock on PyPI)
      backend.py       # DSO discovery, event composition, ctypes FFI
      common.py        # CLI entry point (python -m bluepython)
      import_hooks.py  # sys.meta_path import monitor
      cfg.py           # Sensor config loading
      *_hooks.py       # Per-framework hook modules
    tests/             # Integration test scripts
      test_smoke.py    # DSO smoke tests via ctypes
    pyproject.toml
    EVENTS.md          # Event schema reference
  sensor_tests/        # Shared test definitions
  run-tests-oss.py     # OSS integration test runner
examples/              # Cookbook examples
  mcp/                 # MCP examples (stdio, HTTP, SSE)
  run-examples.py      # Example test runner
observe/
  deploy/              # Docker Compose stack (Grafana + Loki)
  spoolfile2loki/      # Spool file forwarder (Go)
.github/workflows/
  ci.yml               # Lint + build + test + wheel install
  release.yml          # Tag-driven: build -> test -> PyPI (OIDC)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code standards, and how to submit changes.

See [TESTING.md](TESTING.md) for the full testing guide — test suites, how to run them, platform-specific behaviour, and how to add new tests.

See [CHANGELOG.md](CHANGELOG.md) for version history and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Supported Platforms

Pre-built wheels are available for:

| OS | Architecture | Python | Wheel tag |
|----|-------------|--------|-----------|
| Linux | x86_64 | 3.10 — 3.13 | `manylinux_2_28_x86_64` |
| Linux | aarch64 | 3.10 — 3.13 | `manylinux_2_28_aarch64` |
| macOS | Apple Silicon (arm64) | 3.10 — 3.13 | `macosx_11_0_arm64` |
| macOS | Intel (x86_64) | 3.10 — 3.13 | `macosx_10_12_x86_64` |

### Tested distributions

Verified end-to-end (sensor + DSO + examples) on:

| Distribution | Version |
|---|---|
| Amazon Linux 2023 | `2023.11.20260413` |
| Ubuntu 22.04 LTS (Jammy Jellyfish) | `22.04.5` |
| Ubuntu 24.04 LTS (Noble Numbat) | `24.04.4` |
| SUSE Linux Enterprise Server | `16.0` |

### Tested Python versions

`3.10.12`, `3.11.14`, `3.12.3`, `3.13.11`. Any 3.10+ patch release should work.

**Building from source** supports Python >= 3.10 and requires a Rust toolchain plus your platform's development tools (see [Option C](#option-c-build-from-source)).

## License

[Apache 2.0](LICENSE)
