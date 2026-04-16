# How to Monitor Python Imports

This example shows how BlueRock tracks every `import` statement at runtime, emitting a `python_import` event with the module name, file path, SHA-256 hash, and installed version.

## Prerequisites

```bash
pip install requests
```

## Run

```bash
python -m bluepython --oss import_monitoring.py
```

The script imports `requests` and prints its version. BlueRock captures `python_import` events for `requests` and all of its transitive dependencies (`urllib3`, `charset_normalizer`, `certifi`, etc.).

## Read the Events

Filter for import events:

```bash
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name == "python_import")'
```

Show just module names and versions:

```bash
cat ~/.bluerock/event-spool/python-*.ndjson \
  | jq -r '.event | select(.meta.name == "python_import") | "\(.fullname) \(.version // "n/a")"'
```

## What to Expect

Each imported module produces an event like:

```jsonc
{
  "meta": {
    "name": "python_import",
    "type": "event",
    "origin": "bluepython",
    "sensor_id": "...",
    "source_event_id": "..."
  },
  "fullname": "requests",
  "sha256": "abc123...",
  "version": "2.32.3",
  "path": "/path/to/requests/__init__.py",
  "context": {
    "process": { ... }
  }
}
```

Each transitive dependency (`urllib3`, `charset_normalizer`, `certifi`) produces its own event.

| Field | Description |
|-------|-------------|
| `fullname` | Fully-qualified module name (e.g., `urllib3.util.retry`) |
| `sha256` | SHA-256 hash of the module file on disk — detects tampering |
| `version` | Package version from installed metadata, or absent if unavailable |
| `path` | Absolute filesystem path to the module |

## How It Works

BlueRock installs a custom finder on `sys.meta_path` before your code runs. Every call to `import` passes through this finder, which hashes the module file and records its metadata before allowing the import to proceed.

Enable import monitoring in your sensor config:

```json
{
  "enable": true,
  "imports": {"enable": true, "fileslist": true}
}
```
