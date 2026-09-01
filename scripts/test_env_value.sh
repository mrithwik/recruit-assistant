#!/usr/bin/env bash
# Tests for env_value.sh — every .env shape that's come up across two
# rounds of review: absent key, comments, quoting, whitespace, CRLF, and
# their combinations. Run directly: bash scripts/test_env_value.sh
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
tmp_env="$(mktemp)"
trap 'rm -f "$tmp_env"' EXIT

failures=0

check() {
  local description="$1" expected="$2" actual="$3"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $description — expected '$expected', got '$actual'"
    failures=$((failures + 1))
  else
    echo "ok: $description"
  fi
}

value() {
  bash "$script_dir/env_value.sh" "$1" "$tmp_env"
}

# --- No file at all ---
check "missing file" "" "$(bash "$script_dir/env_value.sh" API_HOST "$tmp_env.does-not-exist")"

# --- Empty file / key absent ---
: > "$tmp_env"
check "empty file" "" "$(value API_HOST)"

printf 'USE_MOCK_LLM=true\n' > "$tmp_env"
check "key not present" "" "$(value API_HOST)"

# --- Commented-out line is ignored ---
printf '#API_HOST=0.0.0.0\n' > "$tmp_env"
check "commented-out line ignored" "" "$(value API_HOST)"

# --- Plain value ---
printf 'API_HOST=0.0.0.0\n' > "$tmp_env"
check "plain value" "0.0.0.0" "$(value API_HOST)"

# --- Inline comment ---
printf 'API_HOST=0.0.0.0  # widen for LAN testing\n' > "$tmp_env"
check "inline comment stripped" "0.0.0.0" "$(value API_HOST)"

# --- Duplicate lines — last one wins ---
printf 'API_PORT=8000\nAPI_PORT=9001\n' > "$tmp_env"
check "duplicate lines, last wins" "9001" "$(value API_PORT)"

# --- Double-quoted value (QA round 2 finding) ---
printf 'API_HOST="0.0.0.0"\n' > "$tmp_env"
check "double-quoted value" "0.0.0.0" "$(value API_HOST)"

# --- Single-quoted value ---
printf "API_HOST='0.0.0.0'\n" > "$tmp_env"
check "single-quoted value" "0.0.0.0" "$(value API_HOST)"

# --- Whitespace padded INSIDE the quotes (QA round 3 finding) — the trim
# passes have to run again after the quote-strip, not just before it, or
# this padding is never exposed/removed. ---
printf 'API_HOST=" 0.0.0.0 "\n' > "$tmp_env"
check "whitespace padded inside quotes" "0.0.0.0" "$(value API_HOST)"

printf "API_HOST='\t0.0.0.0\t'\n" > "$tmp_env"
check "tabs padded inside quotes" "0.0.0.0" "$(value API_HOST)"

# --- Trailing whitespace, no comment (QA round 2 finding) ---
printf 'API_HOST=0.0.0.0   \n' > "$tmp_env"
check "trailing whitespace, no comment" "0.0.0.0" "$(value API_HOST)"

# --- CRLF line ending (QA round 2 finding) ---
printf 'API_HOST=0.0.0.0\r\n' > "$tmp_env"
check "CRLF line ending" "0.0.0.0" "$(value API_HOST)"

# --- Combined: quoted + inline comment + CRLF ---
printf 'API_HOST="0.0.0.0"  # widen for LAN testing\r\n' > "$tmp_env"
check "quoted + comment + CRLF combined" "0.0.0.0" "$(value API_HOST)"

# --- A different key on the same file isn't cross-matched ---
printf 'API_HOST=0.0.0.0\nAPI_HOST_FOO=bar\n' > "$tmp_env"
check "similarly-prefixed key not cross-matched" "0.0.0.0" "$(value API_HOST)"

# --- Known, deliberately-unhandled edge cases (not asserted here) ---
# Mismatched quote types (API_HOST="0.0.0.0') and a literal `#` inside a
# quoted value both require deliberately malformed .env syntax rather than
# a plausible real config shape, and are lower priority than everything
# above — noted, not fixed.

echo
if [ "$failures" -eq 0 ]; then
  echo "All checks passed."
  exit 0
else
  echo "$failures check(s) failed."
  exit 1
fi
