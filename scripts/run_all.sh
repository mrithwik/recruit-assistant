#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"

# API_HOST/API_PORT below only see genuinely-exported shell variables —
# pydantic-settings loads .env for every other setting, but purely inside
# the Python process that starts after this line runs, so the shell here
# never sees it on its own (QA caught this: setting API_HOST in .env
# silently did nothing). Pulling just these two keys out with grep/cut
# instead of `source`-ing the whole file: .env commonly holds values with
# unescaped spaces (an app password, say) that make it invalid as a literal
# bash script, so sourcing it wholesale breaks on lines that have nothing
# to do with these two settings.
if [ -f ../.env ]; then
  # `|| true` on each: under `set -e`, grep finding no match (the common
  # case — .env usually won't even have an API_HOST line) exits 1, which
  # would otherwise kill this script silently before it ever reaches the
  # exec below. Absence here just means "nothing to override with."
  env_host=$( { grep -E '^API_HOST=' ../.env || true; } | tail -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//')
  env_port=$( { grep -E '^API_PORT=' ../.env || true; } | tail -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//')
  API_HOST="${API_HOST:-$env_host}"
  API_PORT="${API_PORT:-$env_port}"
fi

exec python -m uvicorn app.main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}" --reload
