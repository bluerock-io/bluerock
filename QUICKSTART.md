# Quick Start

## 1. Install

```bash
python3 -m venv venv && source venv/bin/activate
pip install bluerock[oss]
```

## 2. Configure

```bash
mkdir -p ~/.bluerock
echo '{"enable": true, "mcp": true, "imports": true}' > ~/.bluerock/bluerock-oss.json
```

See [CONFIG.md](acoustic/python/CONFIG.md) for all available options.

## 3. Run

```bash
python -m bluepython --oss --cfg-dir ~/.bluerock your_script.py
```

The `--oss` flag is also auto-detected when `bluerock-oss` is installed.

## 4. View events

```bash
# All events
cat ~/.bluerock/event-spool/python-*.ndjson | jq .event

# Just MCP events
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name | startswith("python_mcp_"))'

# Just imports
cat ~/.bluerock/event-spool/python-*.ndjson | jq '.event | select(.meta.name == "python_import")'
```

See [EVENTS.md](acoustic/python/EVENTS.md) for the full event schema.

## Next steps

- [MCP Examples](examples/mcp/README.md) — monitor MCP servers and clients
- [Import Monitoring Example](examples/core-hooks/import-monitoring/README.md) — track every module loaded
- [Dashboard Setup](README.md#dashboard-grafana--loki) — visualize events in Grafana + Loki
