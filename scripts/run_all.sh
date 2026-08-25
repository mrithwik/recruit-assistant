#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}" --reload
