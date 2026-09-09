#!/usr/bin/env bash
cd "$(dirname "$0")/.."
# Invoke the venv directly for the watched command — see
# run-generation-worker.sh's comment for why (nested `uv run` made
# watchfiles' restart signal unreliable, orphaning the worker process).
exec uv run --env-file .env --package execution-worker watchfiles ".venv/bin/python -m execution_worker.worker" apps/workers/execution/src packages
