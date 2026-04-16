# Testing

BlueRock integration test suites, how to run them, and the CI pipeline.

## Test Suites

BlueRock has three test runners, each validating a different layer:

| Runner | What It Tests | Location |
|--------|--------------|----------|
| `pytest` | DSO smoke tests — ctypes FFI, import resolution | `acoustic/python/tests/test_smoke.py`, `test_bluepython_import.py` |
| `run-tests-oss.py` | Integration tests — runs scripts under `python -m bluepython --oss`, validates NDJSON events | `acoustic/run-tests-oss.py` |
| `run-examples.py` | Cookbook examples — validates example scripts produce expected events | `examples/run-examples.py` |

## Running the Full Suite

All tests should be run inside a virtualenv with BlueRock installed:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e "acoustic/python/[test]"
pip install acoustic/python-oss/
```

```bash
# 1. Smoke tests (fast, ~5s)
pytest acoustic/python/tests/test_bluepython_import.py acoustic/python/tests/test_smoke.py -v --no-header

# 2. Integration tests (~30s)
cd acoustic/python && PYTHONPATH=.. python ../run-tests-oss.py --skip-missing-deps && cd ../..

# 3. Cookbook examples (~20s)
python examples/run-examples.py
```

All three must pass before submitting a PR.

## Running Individual Tests

### run-tests-oss.py

The integration runner lives at `acoustic/run-tests-oss.py` and imports test definitions from `acoustic/sensor_tests/python.py`. It must be run from `acoustic/python/` so that `cwd="tests/"` resolves to the test scripts:

```bash
cd acoustic/python && PYTHONPATH=.. python ../run-tests-oss.py --skip-missing-deps
```

Run a subset by regex:

```bash
cd acoustic/python && PYTHONPATH=.. python ../run-tests-oss.py --select test_import
```

Suppress subprocess output:

```bash
cd acoustic/python && PYTHONPATH=.. python ../run-tests-oss.py --skip-missing-deps --quiet
```

> **Note:** `run-tests-oss.py` uses an `OSS_ALLOWLIST` to select which tests from `sensor_tests/python.py` are safe to run against the OSS backend. Tests not in the allowlist are automatically skipped.

### run-examples.py

Run all examples:

```bash
python examples/run-examples.py
```

Run by name:

```bash
python examples/run-examples.py --select ai-mcp
```

## How Tests Work

### run-tests-oss.py

1. Import test case definitions from `acoustic/sensor_tests/python.py`
2. Filter by `OSS_ALLOWLIST` (tests requiring the full sensor backend are excluded)
3. Create a temporary directory with `bluerock-oss.json` containing the sensor config
4. For each test: clean `~/.bluerock/event-spool/`, run via `python -m bluepython --oss --cfg-dir <tmpdir> -- <script>.py`
5. Collect NDJSON events from `~/.bluerock/event-spool/`
6. Validate events using the test case's `event_parser` callback
7. Check for unexpected internal exception events

### run-examples.py

1. Create a shared temporary directory with `bluerock-oss.json` enabling all hooks used by examples
2. For each example: clean `~/.bluerock/event-spool/`, run via `python -m bluepython --oss --cfg-dir <tmpdir> <script>`
3. Collect NDJSON events from `~/.bluerock/event-spool/`
4. Validate events using `EventChecker` (all listed events must be present)
5. Validate event meta-fields (`name`, `type`, `origin`, `sensor_id`, `source_event_id`)
6. Check for internal exception events (should be absent)

### EventChecker (examples runner)

```python
EventChecker(
    ("python_mcp_server_init", None),
    ("python_mcp_event", None),
    ("python_mcp_client_connect", None),
)
```

Each tuple is `(event_name, attributes_dict_or_None)`. All listed events must be present with matching attributes for the test to pass.

### check_for_event (integration runner)

```python
from sensor_tests.common import check_for_event
check_for_event(events, "python_mcp_event", {"event": "server_received_request"})
```

Returns `True` if any event matches the name and all specified attributes.

### Optional Dependencies

Tests that require external packages use `extra_deps` (integration) or `requires` (examples):

```python
# Integration (sensor_tests/python.py)
PythonTestCase("test_import", extra_deps=["numpy", "requests", "PyYAML"], event_parser=check_import_events)

# Examples (run-examples.py)
TestCase("ai-mcp-monitoring", script_path="...", requires="mcp")
```

If the package is not installed, the test is **skipped** (not failed). In CI, `mcp` and `fastmcp` are installed via `.github/requirements/test.txt`.

## Test Categories

### Smoke Tests (pytest)

| Test | What It Verifies |
|------|-----------------|
| `test_bluepython_import.py` | `import bluepython` succeeds, `import bluerock_oss` resolves DSO path |
| `test_smoke.py` | DSO loads via ctypes, `acoustic_event` C function callable, sensor config returns valid JSON |

### Integration Tests (run-tests-oss.py, OSS_ALLOWLIST)

| Test | Events Verified | Notes |
|------|----------------|-------|
| `test_import` | `python_import` with pkg, version, SHA256 | Module import monitoring |
| `test_reload_import` | `python_import` after module reload | Import re-detection |

### MCP Examples (run-examples.py)

| Example | Transport | Events Verified | Dependencies |
|---------|-----------|----------------|--------------|
| MCP monitoring (stdio) | stdio | `mcp_server_init`, `mcp_server_add`, `mcp_event`, `mcp_session_created`, `mcp_session_terminated`, `mcp_client_connect` | `mcp`, `fastmcp` |
| MCP HTTP | http | `mcp_client_connect`, `mcp_event` | `mcp`, `fastmcp` |
| MCP SSE | sse | `mcp_client_connect`, `mcp_event` | `mcp`, `fastmcp` |

## Event Output

All tests read events from NDJSON files at `~/.bluerock/event-spool/python-{pid}-{tid}.{generation}.ndjson`.

To inspect events manually after a test run:

```bash
# All events (each line is {"ts": "...", "event": {...}})
cat ~/.bluerock/event-spool/python-*.ndjson | jq .event

# Filter by event type
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name == "python_import")'

# Count events by type
cat ~/.bluerock/event-spool/python-*.ndjson | jq -r '.event.meta.name' | sort | uniq -c | sort -rn
```

> **macOS:** Events are written to `~/.bluerock/event-spool/` (same as Linux). No `/tmp` symlink issues.

## CI Pipeline

### On Every Push and PR

`ci.yml` runs:

1. **lint-rust** — `cargo fmt --check` + `cargo clippy -D warnings`
2. **lint-python** — `black --check` + `ruff check`
3. **build-test-unified** — Rust unit tests, Python install, DSO build, pytest, run-tests-oss.py, run-examples.py
4. **test-wheel-install** — Build wheels via cibuildwheel (manylinux_2_28), install, verify DSO resolution

### Scheduled (Weekly)

- `ci.yml` (mcp-compat job) — Tests MCP hooks against the latest upstream mcp + fastmcp. Auto-creates a GitHub Issue if hooks break.
- `staging-tests.yml` — Full integration suite plus wheel builds. Auto-creates a GitHub Issue on failure.
- `security-audit.yml` — `cargo deny check` (Rust advisories + licenses), `pip-audit` (Python CVEs), `pip-licenses` (Python license compliance), `govulncheck` (Go vulnerabilities), `go-licenses` (Go license compliance), `zizmor` (GitHub Actions audit)

### On PR

`dependency-review.yml` scans the PR diff for new vulnerabilities and license violations (requires GitHub Advanced Security on public repos).

## Platform-Specific Behaviour

### Linux

- Event output path: `~/.bluerock/event-spool/`
- DSO file: `libacoustic_oss.so`
- Wheels: manylinux_2_28 (glibc >= 2.28 — RHEL 8, Debian 10, Amazon Linux 2023+)

### macOS

- Event output path: `~/.bluerock/event-spool/` (same as Linux)
- DSO file: `libacoustic_oss.dylib`
- Wheels: macOS 11+ (universal2: Intel + Apple Silicon)
- SHA-256 hashes for packages with compiled extensions differ between platforms

## Adding a New Test

### To run-tests-oss.py

1. Create the test script in `acoustic/python/tests/`:

   ```python
   # test_my_feature.py
   import my_module
   my_module.do_something()
   ```

2. Add a `PythonTestCase` entry in `acoustic/sensor_tests/python.py`:

   ```python
   PythonTestCase(
       "test_my_feature",
       event_parser=lambda events: check_for_event(events, "my_event_name", {"key": "value"}),
       extra_deps=["my_module"],  # omit for stdlib-only
   ),
   ```

3. Add the test name to `OSS_ALLOWLIST` in `acoustic/run-tests-oss.py`:

   ```python
   OSS_ALLOWLIST = {
       ...
       "test_my_feature",
   }
   ```

4. Run it:

   ```bash
   cd acoustic/python && PYTHONPATH=.. python ../run-tests-oss.py --select test_my_feature
   ```

### To run-examples.py

1. Create the example directory and script in `examples/`:

   ```
   examples/category/my-example/
     my_example.py
     requirements.txt   # if external deps needed
     README.md           # howto guide
   ```

2. Add a `TestCase` entry in `examples/run-examples.py`:

   ```python
   TestCase(
       "category/my-example",
       script_path="category/my-example/my_example.py",
       event_checker=EventChecker(
           ("my_event_name", None),
       ),
       requires="my_package",  # or None
   ),
   ```

3. Run it: `python examples/run-examples.py --select my-example`
