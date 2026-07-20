---
name: test
description: 'Bring up every local-dev dependency for AITestGen (Postgres/Temporal/Vault via Docker, migrations, seed data, API, discovery worker, web app) so the user can validate the app end-to-end without remembering the runbook. Use when the user types /test or asks to spin up / start / bring up the app for validation.'
---

# /test — spin up AITestGen for validation

The three long-lived processes (API, discovery worker, web) each get their
own **visible terminal window** via Windows' native `start` — not the Bash
tool's background mode — so the user can watch logs live and Ctrl+C /
troubleshoot per-process. Closing a window is how the user stops that
process.

**Every `start` window-launch command below MUST be run with the Bash tool's
`dangerouslyDisableSandbox: true`.** Without it, the Bash tool's sandbox kills
the whole process tree — including detached windows — the moment the tool
call that spawned them returns, so the window/process silently dies a
second or two after appearing to start. This is the #1 cause of "the web app
/ worker didn't start" — the launch command succeeded, the process just got
reaped right after. `dangerouslyDisableSandbox` is safe here: these are
ordinary local dev-server processes the user explicitly asked to keep
running.

All three already pick up code changes without a manual restart — no wrapper
needed for the API (uvicorn `--reload`) or the web app (Vite's built-in HMR).
The discovery worker has no built-in reload, so it's wrapped in `watchfiles`
(already installed — a transitive dep of `uvicorn[standard]`) to restart it
on file changes.

Steps 2-4 are independent of each other and of the migration/seed steps —
**launch all three windows and run migrations/seeding in one batch of
parallel tool calls** right after Docker is up, rather than serially. `uv
run` and `npm run dev` each sync/install their own deps on demand, so
nothing downstream is blocked waiting on a separate "install everything
first" pass. Serializing all of this behind itself is the other reason
bring-up used to feel slow.

1. `docker compose up -d --wait` — starts Postgres 18.4 + Temporal dev server +
   dev-mode Vault and waits for Postgres's healthcheck (`--wait` needs Docker
   Compose v2.1.1+; if unsupported, drop the flag and just re-run the next
   step once — alembic will fail fast if Postgres isn't ready yet).
Then, in parallel (single message, multiple tool calls):

2. Check `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/openapi.json`.
   If it's not `200`, open the API in its own window (hot-reloads on `.py`
   changes already, via `--reload`); use the Bash tool's sandbox-disable option:
   ```
   cmd //c start "AITestGen API" cmd //k "uv run --package api uvicorn api.main:app --reload --port 8000"
   ```
6. Check if the discovery worker is already running (e.g.
   `ps -W | grep -i discovery_worker` — this environment's Git Bash doesn't
   have `pgrep`). If not, open it in its own window, wrapped in `watchfiles`
   so edits to its source or the shared `packages/` restart it automatically
   (needed for an onboarded Application's DiscoveryRun to actually execute):
   ```
   cmd //c start "AITestGen Discovery Worker" cmd //k "uv run --package discovery-worker watchfiles \"python -m discovery_worker.worker\" apps/workers/discovery/src packages"
   ```
7. In `apps/web`: run `npm install` only if `node_modules` is missing, then
   `npm run generate:api-types` (regenerates TS types from the now-running
   API), then check
   `curl -s -o /dev/null -w '%{http_code}' http://localhost:5173`. If it's not
   `200`, open it in its own window (Vite's dev server hot-reloads by
   default):
   ```
   cmd //c start "AITestGen Web" cmd //k "cd apps\web && npm run dev"
   ```
8. Report back to the user:
   - Web app: http://localhost:5173
   - API: http://localhost:8000 (docs at `/docs`)
   - Temporal UI: http://localhost:8233
   - Sign-in: `dev@example.com` / `devpassword123`
   - Each process is in its own titled window ("AITestGen API" /
     "AITestGen Discovery Worker" / "AITestGen Web") — watch logs there, and
     close a window to stop that process.

Skip the generation worker and the Temporal smoke test — those are a separate
Story 1.1 wiring proof, not part of validating the app.
