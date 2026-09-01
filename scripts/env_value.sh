#!/usr/bin/env bash
# Extract one KEY=value from a .env file, for the shell that launches
# uvicorn (see run_all.sh) — pydantic-settings parses .env correctly for
# every setting the Python process reads itself, but the shell that starts
# that process never sees it on its own, so API_HOST/API_PORT need pulling
# out here before exec'ing uvicorn.
#
# Handles what a real .env commonly contains: the key simply being absent,
# inline `# comments`, surrounding single or double quotes, trailing
# whitespace, and CRLF line endings (a file saved on Windows, or checked
# out with core.autocrlf=true) — each of those broke a naive
# grep/cut/sed version during review; every case here has a matching test
# in scripts/test_env_value.sh.
#
# Used by both run_all.sh and the Makefile's `run` target — one
# implementation instead of two that can drift out of sync with each other.
#
# Usage: env_value.sh KEY FILE
set -euo pipefail

key="$1"
file="$2"

if [ ! -f "$file" ]; then
  exit 0
fi

{ grep -E "^${key}=" "$file" || true; } \
  | tail -1 \
  | cut -d= -f2- \
  | tr -d '\r' \
  | sed \
      -e 's/[[:space:]]*#.*//' \
      -e 's/^[[:space:]]*//' \
      -e 's/[[:space:]]*$//' \
      -e 's/^"\(.*\)"$/\1/' \
      -e "s/^'\\(.*\\)'\$/\\1/"
