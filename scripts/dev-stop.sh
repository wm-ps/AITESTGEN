#!/usr/bin/env bash
# Stop everything scripts/dev-start.sh started: web, API, both workers, and the
# Docker services (Postgres/Temporal/Vault).
set -uo pipefail

# Resolve the repo root from this script's own location (following symlinks)
# rather than from the caller's cwd, so this works from anywhere.
src=${BASH_SOURCE[0]}
while [ -L "$src" ]; do
  dir=$(cd -P "$(dirname "$src")" && pwd)
  src=$(readlink "$src")
  case $src in /*) ;; *) src=$dir/$src ;; esac
done
ROOT=$(cd -P "$(dirname "$src")/.." && pwd)

cd "$ROOT" || exit 1

KEEP_DOCKER=0
WIPE_VOLUMES=0
DRY_RUN=0

usage() {
  cat <<EOF
Usage: scripts/dev-stop.sh [options]

Stops the local AITestGen dev stack: web (5173), API (8000), discovery worker,
generation worker, and the docker compose services.

Options:
  --keep-docker   Stop only the app processes; leave Postgres/Temporal/Vault up
  --volumes, -v   Also delete docker volumes (WIPES the local database)
  --dry-run, -n   Print what would be stopped, kill nothing
  --help, -h      Show this message
EOF
}

while [ $# -gt 0 ]; do
  case $1 in
    --keep-docker) KEEP_DOCKER=1 ;;
    --volumes|-v) WIPE_VOLUMES=1 ;;
    --dry-run|-n) DRY_RUN=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "[dev-stop] unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# --- pid discovery -----------------------------------------------------------

# pgrep -f, minus this script and its own subshells.
match_pids() {
  pgrep -f "$1" 2>/dev/null | grep -vx "$$" | grep -vx "$PPID"
}

# PIDs listening on a TCP port.
port_pids() { lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null; }

# Walk up from $1 collecting ancestors that are launcher wrappers (npm/uv/node)
# rather than unrelated processes. Stops at the first non-matching ancestor, so
# it can never climb out into your shell or launchd.
wrapper_ancestors() {
  local pid=$1 ppid cmd
  while :; do
    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
    [ -z "$ppid" ] && break
    [ "$ppid" -le 1 ] && break
    cmd=$(ps -o command= -p "$ppid" 2>/dev/null)
    case $cmd in
      *"npm run dev"*|*"npm exec"*|*"uv run"*|*watchfiles*|*vite*)
        echo "$ppid"; pid=$ppid ;;
      *) break ;;
    esac
  done
}

# True if the process's working directory is inside this checkout. This is the
# safety net: it means we never kill another project that happens to hold port
# 5173/8000, nor a second checkout of this same repo.
in_repo() {
  local cwd
  cwd=$(lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)
  case $cwd in
    "$ROOT"|"$ROOT"/*) return 0 ;;
    *) return 1 ;;
  esac
}

# Everything for one logical service: deduped, numeric, and repo-scoped.
collect() {
  local p
  for p in $({ for p in "$@"; do echo "$p"; done; } | grep -E '^[0-9]+$' | sort -un); do
    in_repo "$p" && echo "$p"
  done
}

api_pids() {
  local pids
  pids=$(match_pids 'uvicorn api\.main:app')
  # Reload children of uvicorn don't always carry the full cmdline.
  pids="$pids $(port_pids 8000)"
  for p in $(port_pids 8000); do pids="$pids $(wrapper_ancestors "$p")"; done
  collect $pids
}

web_pids() {
  local pids
  # `npm run dev` has a bare cmdline, so anchor on the repo-scoped vite child
  # and the port listener, then climb to the npm parent.
  pids=$(match_pids "$ROOT/apps/web")
  pids="$pids $(port_pids 5173)"
  for p in $(port_pids 5173) $pids; do pids="$pids $(wrapper_ancestors "$p")"; done
  collect $pids
}

worker_pids() { collect $(match_pids "$1"); }

# --- killing -----------------------------------------------------------------

alive() { kill -0 "$1" 2>/dev/null; }

# TERM, wait up to ~5s, then KILL whatever is left.
stop_pids() {
  local label=$1; shift
  local pids="$*"

  if [ -z "${pids// /}" ]; then
    echo "[dev-stop] $label: not running"
    return 0
  fi

  if [ "$DRY_RUN" = 1 ]; then
    echo "[dev-stop] $label: would stop $(echo "$pids" | tr '\n' ' ')"
    ps -o pid=,command= -p "$(echo "$pids" | tr ' \n' ',,' | sed 's/,*$//')" 2>/dev/null \
      | sed 's/^/               /' | cut -c1-120
    return 0
  fi

  echo "[dev-stop] $label: stopping $(echo "$pids" | tr '\n' ' ')"
  for p in $pids; do kill -TERM "$p" 2>/dev/null; done

  local waited=0
  while [ "$waited" -lt 50 ]; do
    local remaining=""
    for p in $pids; do alive "$p" && remaining="$remaining $p"; done
    [ -z "${remaining// /}" ] && return 0
    sleep 0.1
    waited=$((waited + 1))
  done

  for p in $pids; do
    if alive "$p"; then
      echo "[dev-stop] $label: pid $p ignored SIGTERM, sending SIGKILL"
      kill -KILL "$p" 2>/dev/null
    fi
  done
}

# --- go ----------------------------------------------------------------------

[ "$DRY_RUN" = 1 ] && echo "[dev-stop] dry run - nothing will be killed"

stop_pids "web (5173)"          "$(web_pids)"
stop_pids "api (8000)"          "$(api_pids)"
stop_pids "discovery worker"    "$(worker_pids 'discovery_worker\.worker')"
stop_pids "generation worker"   "$(worker_pids 'generation_worker\.worker')"

if [ "$KEEP_DOCKER" = 1 ]; then
  echo "[dev-stop] docker: left running (--keep-docker)"
elif [ "$DRY_RUN" = 1 ]; then
  if [ "$WIPE_VOLUMES" = 1 ]; then
    echo "[dev-stop] docker: would run 'docker compose down --volumes' (DELETES local db)"
  else
    echo "[dev-stop] docker: would run 'docker compose down'"
  fi
elif [ "$WIPE_VOLUMES" = 1 ]; then
  echo "[dev-stop] docker compose down --volumes (deleting local database) ..."
  docker compose down --volumes
else
  echo "[dev-stop] docker compose down ..."
  docker compose down
fi

# --- report ------------------------------------------------------------------

if [ "$DRY_RUN" = 1 ]; then
  echo "[dev-stop] dry run complete"
  exit 0
fi

leftovers=$(collect $(web_pids) $(api_pids) \
  $(worker_pids 'discovery_worker\.worker') \
  $(worker_pids 'generation_worker\.worker'))

if [ -n "${leftovers// /}" ]; then
  echo "[dev-stop] WARNING: still alive after stop:" >&2
  ps -o pid=,command= -p "$(echo "$leftovers" | tr ' \n' ',,' | sed 's/,*$//')" 2>/dev/null >&2
  exit 1
fi

echo "[dev-stop] AITestGen stopped. Bring it back with scripts/dev-start.sh"
