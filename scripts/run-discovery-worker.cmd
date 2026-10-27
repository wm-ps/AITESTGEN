@echo off
cd /d "%~dp0.."
uv run --env-file .env --package discovery-worker watchfiles --filter python ".venv/Scripts/python.exe -m discovery_worker.worker" apps/workers/discovery/src packages
