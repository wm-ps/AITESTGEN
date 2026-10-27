@echo off
cd /d "%~dp0.."
uv run --env-file .env --package generation-worker watchfiles --filter python ".venv/Scripts/python.exe -m generation_worker.worker" apps/workers/generation/src packages
