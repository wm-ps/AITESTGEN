#!/usr/bin/env bash
cd "$(dirname "$0")/.."
# Invoke the venv directly for the watched command, not another `uv run` —
# two nested process layers made watchfiles' SIGINT/SIGKILL on file-change
# unreliable at reaching the actual python process, leaving it orphaned and
# still polling Temporal after a restart (same reasoning as the Dockerfiles'
# own direct-venv invocation).
exec uv run --env-file .env --package generation-worker watchfiles ".venv/bin/python -m generation_worker.worker" apps/workers/generation/src packages
