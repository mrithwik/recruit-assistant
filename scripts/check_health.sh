#!/usr/bin/env bash
set -euo pipefail

PORT="${API_PORT:-8000}"
if curl -sf "http://localhost:${PORT}/health" > /dev/null; then
  echo "Backend healthy on :${PORT}"
else
  echo "Backend not responding on :${PORT}" >&2
  exit 1
fi
