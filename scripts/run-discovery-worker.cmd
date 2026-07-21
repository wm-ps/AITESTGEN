@echo off
cd /d "%~dp0.."
uv run --env-file .env --package discovery-worker watchfiles "uv run --package discovery-worker python -m discovery_worker.worker" apps/workers/discovery/src packages
