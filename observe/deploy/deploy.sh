#!/usr/bin/env bash
#
# deploy.sh — bring up the spoolfile2loki stack.
#
# Usage:
#   ./deploy.sh              # mock mode (default)
#   ./deploy.sh mock         # mock mode
#   ./deploy.sh dir /path    # directory mode, reads rolling NDJSON files from /path
#   ./deploy.sh down         # tear everything down
#
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-mock}"

case "$MODE" in
  down)
    docker compose down -v
    exit 0
    ;;
  mock)
    echo "==> Starting in MOCK mode (embedded test data)"
    CONFIG_FILE="spoolfile2loki-mock.yaml"
    EXTRA_ARGS=()
    ;;
  dir)
    SPOOL_DIR="${2:?Usage: $0 dir /path/to/spool}"
    SPOOL_DIR="$(cd "$SPOOL_DIR" 2>/dev/null && pwd)" || {
      echo "ERROR: directory does not exist: $2" >&2
      exit 1
    }
    echo "==> Starting in DIR mode, reading from: $SPOOL_DIR"
    CONFIG_FILE="spoolfile2loki-dir.yaml"
    export SPOOL_DIR
    EXTRA_ARGS=()
    ;;
  *)
    echo "Usage: $0 [mock|dir /path|down]" >&2
    exit 1
    ;;
esac

export CONFIG_FILE
docker compose up --build -d "${EXTRA_ARGS[@]}"

echo ""
echo "Stack is running:"
echo "  Grafana:  http://localhost:3000  (admin/admin)"
echo "  Loki:     http://localhost:3100"
echo ""
echo "To view logs:  docker compose logs -f spoolfile2loki"
echo "To stop:       ./deploy.sh down"
