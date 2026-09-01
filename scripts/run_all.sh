#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir/../backend"

# API_HOST/API_PORT only see genuinely-exported shell variables — .env is
# loaded for every other setting by pydantic-settings, but purely inside
# the Python process that starts after this line runs, so the shell here
# never sees it on its own. env_value.sh pulls just these two keys out
# (handling quoting/whitespace/CRLF — see that file) rather than `source`-
# ing the whole file, which would break on lines with unescaped spaces
# (an app password, say) that aren't valid as literal bash.
env_host=$(bash "$script_dir/env_value.sh" API_HOST "$script_dir/../.env")
env_port=$(bash "$script_dir/env_value.sh" API_PORT "$script_dir/../.env")
API_HOST="${API_HOST:-$env_host}"
API_PORT="${API_PORT:-$env_port}"

exec python -m uvicorn app.main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT:-8000}" --reload
