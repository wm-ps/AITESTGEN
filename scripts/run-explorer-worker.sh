#!/usr/bin/env bash
cd "$(dirname "$0")/.."
# Vantage Explorer worker (docs/vantage-explorer/PLAN.md) — same watch pattern as run-generation-worker.sh.
exec uv run --env-file .env --package explorer-worker watchfiles --filter python ".venv/bin/python -m explorer_worker.worker" apps/workers/explorer/src packages/explorer_core
