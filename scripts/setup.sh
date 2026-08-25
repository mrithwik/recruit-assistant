#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pip install -e ".[dev]"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — defaults to USE_MOCK=true, no API keys required to start."
fi

mkdir -p data
echo "Backend setup complete. Run 'make run' to start it, and 'make install-frontend && make run-frontend' for the UI."
