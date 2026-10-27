@echo off
cd /d "%~dp0.."
uv run --env-file .env --package execution-worker watchfiles --filter python ".venv/Scripts/python.exe -m execution_worker.worker" apps/workers/execution/src packages
