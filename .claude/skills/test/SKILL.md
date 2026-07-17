---
name: test
description: 'Bring up every local-dev dependency for AITestGen (Postgres/Temporal/Vault via Docker, migrations, seed data, API, discovery worker, web app) so the user can validate the app end-to-end without remembering the runbook. Use when the user types /test or asks to spin up / start / bring up the app for validation.'
---

# /test — spin up AITestGen for validation

Run these in order. Every step through seeding is idempotent (safe to re-run).
For the long-lived processes, check the port first so repeat `/test` runs
don't spawn duplicates.

1. `docker compose up -d --wait` — starts Postgres 18.4 + Temporal dev server +
   dev-mode Vault and waits for Postgres's healthcheck (`--wait` needs Docker
   Compose v2.1.1+; if unsupported, drop the flag and just re-run the next
   step once — alembic will fail fast if Postgres isn't ready yet).
2. `uv sync --all-packages`
3. `uv run alembic upgrade head`
4. `uv run --package api python -m api.scripts.seed_dev_data` — creates
   `dev@example.com` / `devpassword123` in "Dev Organization" (no-op if it
   already exists).
5. Check `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/openapi.json`.
   If it's not `200`, start the API in the background:
   `uv run --package api uvicorn api.main:app --reload --port 8000`
6. Check if the discovery worker is already running (e.g.
   `pgrep -f discovery_worker.worker`). If not, start it in the background:
   `uv run --package discovery-worker python -m discovery_worker.worker`
   (needed for an onboarded Application's DiscoveryRun to actually execute).
7. In `apps/web`: run `npm install` only if `node_modules` is missing, then
   `npm run generate:api-types` (regenerates TS types from the now-running
   API), then check
   `curl -s -o /dev/null -w '%{http_code}' http://localhost:5173`. If it's not
   `200`, start it in the background: `npm run dev`.
8. Report back to the user:
   - Web app: http://localhost:5173
   - API: http://localhost:8000 (docs at `/docs`)
   - Temporal UI: http://localhost:8233
   - Sign-in: `dev@example.com` / `devpassword123`

Skip the generation worker and the Temporal smoke test — those are a separate
Story 1.1 wiring proof, not part of validating the app.
