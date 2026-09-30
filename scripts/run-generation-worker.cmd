@echo off
cd /d "%~dp0.."
uv run --env-file .env --package generation-worker watchfiles --filter python "uv run --package generation-worker python -m generation_worker.worker" apps/workers/generation/src packages
