@echo off
cd /d "%~dp0.."
uv run --env-file .env --package execution-worker watchfiles "uv run --package execution-worker python -m execution_worker.worker" apps/workers/execution/src packages
