#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_ENV_FILE="$PROJECT_DIR/.env"
MAX_SESSION_WORKERS=12

read_env_value() {
  local key="$1"
  local file="$2"
  local line

  [ -f "$file" ] || return 1
  line="$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$file" | tail -n 1)"
  [ -n "$line" ] || return 1
  line="${line%$'\r'}"
  line="${line#\"}"
  line="${line%\"}"
  line="${line#\'}"
  line="${line%\'}"
  printf '%s' "$line"
}

worker_count="${SESSION_WORKER_COUNT:-}"
if [ -z "$worker_count" ]; then
  worker_count="$(read_env_value SESSION_WORKER_COUNT "$COMPOSE_ENV_FILE" || true)"
fi
worker_count="${worker_count:-6}"

if ! [[ "$worker_count" =~ ^[0-9]+$ ]] ||
   [ "$worker_count" -lt 1 ] ||
   [ "$worker_count" -gt "$MAX_SESSION_WORKERS" ]; then
  printf 'SESSION_WORKER_COUNT must be an integer from 1 to %s (current: %s).\n' \
    "$MAX_SESSION_WORKERS" "$worker_count" >&2
  exit 1
fi

services=(mysql redis backend frontend)
for ((index = 0; index < worker_count; index++)); do
  services+=("session_worker_${index}")
done

cd "$PROJECT_DIR"
printf 'Starting %s session worker(s)...\n' "$worker_count"
SESSION_WORKER_COUNT="$worker_count" docker compose up -d --build "${services[@]}"

unused_workers=()
for ((index = worker_count; index < MAX_SESSION_WORKERS; index++)); do
  unused_workers+=("session_worker_${index}")
done
if [ "${#unused_workers[@]}" -gt 0 ]; then
  docker compose stop "${unused_workers[@]}"
fi

