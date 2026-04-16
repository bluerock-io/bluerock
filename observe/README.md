# Grafana OSS Stack for BlueRock Events

A self-contained Grafana + Loki stack for visualizing BlueRock security events. Reads NDJSON spool files produced by acoustic-lite sensors and forwards them to Loki for querying and dashboarding in Grafana.

## Prerequisites

The `spoolfile2loki` container image must be built before deploying the stack.

```bash
cd spoolfile2loki
just build
```

This builds a multi-arch (x86_64 + arm64) container image tagged as both `spoolfile2loki:<version>` and `spoolfile2loki:latest`.

## Directory Structure

```
grafana-opensource/
├── deploy/                          # Docker Compose stack
│   ├── deploy.sh                    # Deployment script
│   ├── docker-compose.yml           # Grafana + Loki + spoolfile2loki
│   ├── loki-config.yml              # Loki storage configuration
│   ├── spoolfile2loki-mock.yaml     # Config for mock mode (embedded test data)
│   ├── spoolfile2loki-dir.yaml      # Config for directory mode (real spool files)
│   ├── grafana/provisioning/        # Auto-provisioned Loki datasource
│   ├── boards/                      # Pre-built Grafana dashboards
│   └── spool/                       # Sample NDJSON spool file
└── spoolfile2loki/                  # Spool-to-Loki forwarder (Go)
    ├── cmd/spoolfile2loki/main.go   # Entrypoint
    ├── internal/                    # Core logic (forwarder, Loki client, state)
    ├── Dockerfile                   # Multi-arch container build
    ├── justfile                     # Build recipes
    ├── VERSION                      # Semantic version
    └── config.yaml.example          # Annotated config reference
```

## Deployment

### Mock Mode (no sensor required)

Replays embedded acoustic-lite sample events with timestamps shifted to the current time. Useful for testing and demos.

```bash
cd deploy
./deploy.sh mock
```

### Directory Mode (live spool files)

Reads rolling NDJSON spool files from a directory on the host. The default spool directory is `~/.bluerock/oss-events`.

```bash
cd deploy
./deploy.sh dir ~/.bluerock/oss-events
```

The forwarder watches the directory for new and growing files, tracks byte offsets to avoid re-reading, and marks completed files so they are skipped on subsequent polls.

### Tear Down

```bash
cd deploy
./deploy.sh down
```

This removes all containers and volumes (Loki data, Grafana state, forwarder state).

## Services

| Service          | Port | Description                              |
|------------------|------|------------------------------------------|
| Grafana          | 3000 | Dashboard UI (`admin` / `admin`)         |
| Loki             | 3100 | Log aggregation backend                  |
| spoolfile2loki   | —    | Reads spool files, pushes to Loki        |

## Spool File Format

Each line is a JSON object with two fields:

```json
{"ts": 1710000000000, "event": {"meta": {"name": "dns_query", "origin": "sensor-01", "sensor_id": 42911, "type": "network"}, ...}}
```

- **ts** — Unix milliseconds (integer) or ISO 8601 string
- **event** — Arbitrary JSON payload; `event.meta` fields (`name`, `origin`, `sensor_id`, `type`) become Loki labels

## Configuration Reference

See `spoolfile2loki/config.yaml.example` for all options. Key settings:

| Field            | Default                    | Description                                    |
|------------------|----------------------------|------------------------------------------------|
| `loki_endpoint`  | (required)                 | Loki base URL                                  |
| `spool_file`     | —                          | Single spool file path (mutually exclusive with `spool_dir`) |
| `spool_dir`      | —                          | Directory of rolling spool files               |
| `mock`           | `false`                    | Enable mock mode with embedded test data       |
| `poll_interval`  | `60s`                      | How often to check for new events              |
| `batch_size`     | `100`                      | Events per Loki push request                   |
| `state_file`     | `spoolfile2loki.state`     | Tracks forwarding progress across restarts     |
| `labels`         | `{}`                       | Extra labels applied to every Loki stream      |
| `log_level`      | `info`                     | `debug`, `info`, `warning`, `error`            |
| `loki_retry`     | `max_retries: 10, retry_delay: 2s` | Retry policy; crashes after max retries |
