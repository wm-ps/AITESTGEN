@echo off
cd /d "%~dp0.."
uv run --env-file .env --package explorer-worker watchfiles --filter python ".venv/Scripts/python.exe -m explorer_worker.worker" apps/workers/explorer/src packages/explorer_core
