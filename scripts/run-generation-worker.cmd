@echo off
cd /d "%~dp0.."
uv run --env-file .env --package generation-worker watchfiles "uv run --package generation-worker python -m generation_worker.worker" apps/workers/generation/src packages
