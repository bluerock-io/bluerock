# Contributing to BlueRock

## Development Environment

### Prerequisites

- Python >= 3.10 (tested up to 3.13)
- Rust stable toolchain (`rustup toolchain install stable`)
- Linux (x86_64 or aarch64) or macOS (Intel or Apple Silicon)

### Clone and Build

```bash
git clone https://github.com/bluerock-io/bluerock.git
cd bluerock

# 1. Create a virtualenv
python3 -m venv venv && source venv/bin/activate

# 2. Install the Python sensor (editable mode with test deps)
pip install -e "acoustic/python/[test]"

# 3. Build and install bluerock-oss (Rust DSO)
pip install setuptools-rust
pip install acoustic/python-oss/

# 4. Verify
python -m bluepython --help
python -c "import bluerock_oss; print('DSO:', bluerock_oss.get_dso_path())"
```

### Install Test Dependencies

```bash
pip install mcp fastmcp
```

## Code Standards

### Python

- **Formatter:** `black` with `line-length = 120` (config in `acoustic/python/pyproject.toml`). Always pass `--config acoustic/python/pyproject.toml` — without it, `black` falls back to its 88-char default, wraps lines our CI then re-flattens, and your patch arrives with drift.
- **Linter:** `ruff`

```bash
black --config acoustic/python/pyproject.toml acoustic/python/         # reformat in place
black --check --config acoustic/python/pyproject.toml acoustic/python/ # CI-style gate
ruff check acoustic/python/
```

### Rust

- **Formatter:** `rustfmt`
- **Linter:** `clippy` with `-D warnings`

```bash
cargo fmt --manifest-path acoustic/python-oss/Cargo.toml -- --check
cargo clippy --manifest-path acoustic/python-oss/Cargo.toml --no-deps -- -D warnings
```

### Conventions

- Hook modules follow the `*_hooks.py` naming pattern in `bluepython/`
- Framework hooks use `@wrapt.when_imported()` for lazy loading — zero overhead for uninstalled packages
- Each hook module is gated by `cfg.sensor_config.enabled("feature_name")`
- Events are single-line JSON (NDJSON) written to `~/.bluerock/event-spool/`

## Running Tests

See [TESTING.md](TESTING.md) for the full testing guide — test suites, how to run them, platform-specific behaviour, and how to add new tests.

Quick check before submitting:

```bash
# Lint
black --check --config acoustic/python/pyproject.toml acoustic/python/
ruff check acoustic/python/
cargo fmt --manifest-path acoustic/python-oss/Cargo.toml -- --check
cargo clippy --manifest-path acoustic/python-oss/Cargo.toml --no-deps -- -D warnings

# Test
pytest acoustic/python/tests/test_bluepython_import.py acoustic/python/tests/test_smoke.py -v --no-header
cd acoustic/python && PYTHONPATH=.. python ../run-tests-oss.py --skip-missing-deps
python examples/run-examples.py
```

## Submitting Changes

1. Create a branch from `main`
2. Make your changes, following the code standards above
3. Run the full lint + test suite (see above)
4. Open a pull request — the [PR template](.github/pull_request_template.md) will guide you through the summary, test plan, and checklist

### Commit Messages

Keep them short and descriptive:
- `fix: resolve DSO path lookup on macOS`
- `feat: add OpenAI hook module`
- `ci: update cibuildwheel to v3.5`

## Project Layout

```
acoustic/
  python-oss/           # Rust DSO (bluerock-oss on PyPI)
    src/lib.rs          # C ABI: acoustic_event, acoustic_get_sensor_config
    bluerock_oss/       # Python wrapper: get_dso_path()
    Cargo.toml
    pyproject.toml
  python/
    bluepython/         # Python sensor (bluerock on PyPI)
      backend.py        # DSO discovery, event composition, ctypes FFI
      common.py         # CLI entry point (python -m bluepython)
      import_hooks.py   # sys.meta_path import monitor
      cfg.py            # Sensor config loading
      *_hooks.py        # Per-framework hook modules
    tests/              # Integration test scripts
      test_smoke.py     # DSO smoke tests via ctypes
    pyproject.toml
    EVENTS.md           # Event schema reference
  sensor_tests/         # Shared test definitions (TestCase, check_for_event)
  run-tests-oss.py      # OSS integration test runner (OSS_ALLOWLIST)
examples/               # Cookbook examples
  run-examples.py       # Example test runner
.github/workflows/
  ci.yml                # Lint + build + test + wheel install
  release.yml           # Tag-driven: build → test → PyPI (OIDC)
  staging-tests.yml     # Scheduled integration tests + auto-issue
  security-audit.yml    # cargo-deny + pip-audit
  scorecard.yml         # OSSF Scorecard supply-chain analysis
  dependency-review.yml # PR vulnerability + license gate
```
