#!/usr/bin/env bash
# Bring up the full Joy stack and (optionally) seed demo data.
set -euo pipefail

cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

docker compose up -d --build

echo "Waiting for the API to become healthy..."
until curl -sf http://localhost:8080/health >/dev/null 2>&1; do sleep 2; done

if [ "${SEED:-0}" = "1" ]; then
  python scripts/seed_demo.py
fi

echo "Joy is up: http://localhost:8080  (Jaeger UI: http://localhost:16686)"
