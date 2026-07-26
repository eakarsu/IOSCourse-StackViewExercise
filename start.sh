#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
CANONICAL_AI_FILE="/Users/erolakarsu/external/ai.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi
if [[ "$(stat -f '%Lp' "$ENV_FILE")" != "600" ]]; then
  echo ".env must have mode 600" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${API_PORT:?API_PORT is required}"
: "${UI_PORT:?UI_PORT is required}"
: "${UI_ORIGIN:?UI_ORIGIN is required}"
: "${RUNTIME_DB_PATH:?RUNTIME_DB_PATH is required}"
: "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY is required}"
: "${OPENROUTER_MODEL:?OPENROUTER_MODEL is required}"
: "${OPENROUTER_BASE_URL:?OPENROUTER_BASE_URL is required}"

[[ "$API_PORT" =~ ^[0-9]+$ && "$UI_PORT" =~ ^[0-9]+$ && "$API_PORT" != "$UI_PORT" ]] || { echo "API_PORT and UI_PORT must be distinct numeric ports" >&2; exit 1; }
[[ "$UI_ORIGIN" == "http://127.0.0.1:$UI_PORT" ]] || { echo "UI_ORIGIN is invalid" >&2; exit 1; }
[[ "$OPENROUTER_BASE_URL" == "https://openrouter.ai/api/v1" ]] || { echo "OPENROUTER_BASE_URL is invalid" >&2; exit 1; }
[[ -f "$RUNTIME_DB_PATH" ]] || { echo "runtime database missing; run python3 -m runtime.prepare" >&2; exit 1; }

cd "$PROJECT_ROOT"
python3 -m runtime.verify_ai_environment "$ENV_FILE" "$CANONICAL_AI_FILE"

for port in "$API_PORT" "$UI_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "port $port is already in use" >&2
    exit 1
  fi
done

api_pid=""
ui_pid=""
cleanup() {
  trap - INT TERM EXIT
  [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true
  [[ -n "$ui_pid" ]] && kill "$ui_pid" 2>/dev/null || true
  [[ -n "$api_pid" ]] && wait "$api_pid" 2>/dev/null || true
  [[ -n "$ui_pid" ]] && wait "$ui_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

python3 -m runtime.companion &
api_pid=$!
python3 -m runtime.ui_server &
ui_pid=$!

while kill -0 "$api_pid" 2>/dev/null && kill -0 "$ui_pid" 2>/dev/null; do
  sleep 0.2
done

echo "a runtime service stopped unexpectedly" >&2
exit 1
