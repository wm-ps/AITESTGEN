#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

check_url() { curl -s -o /dev/null -w '%{http_code}' "$1" 2>/dev/null; }

# Web has no dependency on Postgres/Temporal/Vault - start it before/alongside
# docker instead of after it. (Deliberately NOT also backgrounding a `uv sync`
# prewarm here - measured on Windows that piling every sync on top of docker
# and npm install at once causes enough CPU/disk contention to be a net
# slowdown instead of a speedup.)
if [ "$(check_url http://localhost:5173)" != "200" ]; then
  echo "[dev-up] starting web in parallel with docker..."
  (cd apps/web && { [ -d node_modules ] || npm install; } && npm run dev) >logs/web.log 2>&1 &
fi

echo "[dev-up] docker compose up -d --wait ..."
if ! docker compose up -d --wait; then
  echo "[dev-up] docker compose failed - is Docker running?"
  exit 1
fi

if [ "$(check_url http://localhost:8000/openapi.json)" != "200" ]; then
  echo "[dev-up] starting API..."
  uv run --env-file .env --package api uvicorn api.main:app --reload --port 8000 >logs/api.log 2>&1 &
fi

if ! pgrep -f "discovery_worker.worker" >/dev/null 2>&1; then
  echo "[dev-up] starting discovery worker..."
  scripts/run-discovery-worker.sh >logs/discovery-worker.log 2>&1 &
fi

if ! pgrep -f "generation_worker.worker" >/dev/null 2>&1; then
  echo "[dev-up] starting generation worker..."
  scripts/run-generation-worker.sh >logs/generation-worker.log 2>&1 &
fi

# Best-effort, backgrounded: refresh generated API types once the API
# responds. Web is already up by now - this never blocks it.
scripts/wait-and-gen-types.sh >logs/typegen.log 2>&1 &

cat <<'EOF'

[dev-up] AITestGen is up (or was already running):
  Web:      http://localhost:5173
  API:      http://localhost:8000/docs
  Temporal: http://localhost:8233
  Sign-in:  dev@example.com / devpassword123
  Logs:     logs/{web,api,discovery-worker,generation-worker,typegen}.log
  Stop:     pkill -f 'npm run dev' / pkill -f uvicorn / pkill -f discovery_worker.worker / pkill -f generation_worker.worker
            (docker compose down for Postgres/Temporal/Vault)
EOF
