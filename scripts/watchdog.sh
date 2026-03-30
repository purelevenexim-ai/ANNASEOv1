#!/usr/bin/env bash
set -euo pipefail

# Simple watchdog that pings the local health endpoint and restarts the app
# Usage: watchdog.sh [health_url] [service_name] [compose_dir]

HEALTH_URL=${1:-http://127.0.0.1:8000/healthz}
SERVICE_NAME=${2:-annaseo}
COMPOSE_DIR=${3:-/opt/annaseo}

if ! curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "$(date -Is) [watchdog] health check failed against $HEALTH_URL"
  if command -v docker >/dev/null 2>&1 && [ -f "$COMPOSE_DIR/docker-compose.yml" ]; then
    echo "Restarting docker compose services in $COMPOSE_DIR"
    (cd "$COMPOSE_DIR" && docker compose restart) || true
  else
    echo "Restarting systemd service $SERVICE_NAME"
    systemctl restart "$SERVICE_NAME" || true
  fi
else
  echo "$(date -Is) [watchdog] healthy"
fi
