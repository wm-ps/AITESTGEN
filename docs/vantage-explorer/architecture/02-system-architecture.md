# 2. System architecture

> Diagram: [System architecture](diagrams/explorer-system.html). Use its guided views: *Start a run*, *Explore the app*, *Watch and answer*, *Hand off to Vantage*.

## Design principles

1. **A standalone module.** Explorer has its own worker, its own tables (all prefixed `explorer_`) and its own LLM client. From the classic discovery world it reads only the `application` row and the app's saved login. Classic discovery still exists behind a flag.
2. **Orchestration in Temporal, work in activities.** The workflow only sequences steps. Every browser and model action runs inside an activity, so a run survives worker restarts and can wait days for a human without using resources.
3. **Everything is journaled row by row.** Each screen, event, mission and test is written as it happens. That is what makes the live view, pause/resume and the "resume from where it stopped" logic possible.
4. **The app is evidence, not truth.** See [document 5](05-trust-safety-and-proof.md).

## Components

| Component | Code location | Technology | Responsibility |
|---|---|---|---|
| **Explorer tab** | `apps/web/src/explorer/` | React + TypeScript (Vite SPA) | Start/pause/resume runs, live view, questions, screens, scenarios, App Summary review. Polls the API; it has no websocket. |
| **Vantage API, `/explorer` router** | `apps/api/src/api/explorer.py` (mounted in `main.py`) | FastAPI, SQLModel | 34 endpoints: start runs, the confirm signal, stop/pause/resume, answers, knowledge and documents, roles, downloads. Enforces tenant isolation by organization. |
| **Discovery hook** | `apps/api/src/api/discovery.py` | FastAPI | When `EXPLORER_REPLACES_DISCOVERY` is not `0` (the default), onboarding a new app starts Explorer instead of the classic crawler. |
| **Temporal** | external service, `explorer-task-queue` | Temporal (Python SDK `temporalio>=1.9`) | Runs `ExplorerRunWorkflow`, holds the "App Summary confirmed" signal, and handles cancellation for Stop/Pause. |
| **Explorer worker** | `apps/workers/explorer/` (package `explorer-worker`) | Python 3, `temporalio`, Playwright (`>=1.57`), `httpx`, SQLModel/psycopg | Registers the workflow and 16 activities. Does all browser driving, model calls, judging, proving and the hand-off. |
| **explorer_core** | `packages/explorer_core/` | SQLModel | Shared table definitions, status constants, Temporal names (`EXPLORER_TASK_QUEUE`, signal names, workflow id format) and the "needs you" email helper. Used by both the API and the worker. |
| **Headless Chromium** | launched by the worker | Playwright Chromium, 1440×900, headless | One browser per activity: the first look, each mission, the hunt, breadth checks, and each test build/proof. Records `.webm` video when asked. |
| **LLM gateway** | `LITELLM_BASE_URL` | OpenAI-compatible `/chat/completions` through the company LiteLLM gateway | Two GPT-5.6 tiers. **Thinking** (`gpt-5.6-sol`) reads screens, decides steps, summarizes, plans, judges and picks proofs. **Fast** (`gpt-5.6-luna`) only picks where to look next. Every call must return a JSON object. |
| **PostgreSQL** | `DATABASE_URL` | Postgres + Alembic migrations | All `explorer_*` tables, including screenshot JPEGs and recording `.webm`/`.mp4` bytes. |
| **Vault** | `secrets_client` package | HashiCorp Vault | The app's login, and the logins of extra "roles" for the who-can-see-what check. Explorer stores only `secret_ref`. |
| **Classic Vantage** | `Journey`, `Scenario`, `TestSuite`, `TestAsset`… tables; generation worker | Existing Vantage pipeline | Receives Explorer's proven tests (Stage 8). The generation worker reuses Explorer's already-proven Playwright code when it type-checks. |
| **SMTP** | `SMTP_*` env vars | `smtplib` | Emails the run's starter when the run needs them. Without `SMTP_HOST` it logs instead of sending. |
| **ffmpeg + a bold font** | on the worker machine | ffmpeg CLI | Builds the MP4 highlight video. It is skipped, with a feed message, when either is missing. |

## Why these choices

| Choice | Reason |
|---|---|
| Temporal workflow per run | A run lasts from minutes to days and waits on a person. Signals and durable timers make "wait up to 14 days for confirmation" free, and cancellation gives clean Stop/Pause. |
| Activities never auto-retry (`maximum_attempts=1`) | A half-driven browser session can't be safely replayed. Each activity turns its own failure into a visible failed run, mission or test. The pool helper gives a crashed item **one** extra try. |
| Polling instead of websockets | Simple and stateless. Events have an integer id, so the UI asks for `events?after=<last id>` every 1.5 s. |
| Screenshots and videos in Postgres | No object-store setup for Explorer. Each shot is a 60–150 KB JPEG. This is marked as a `ponytail:` shortcut: move to the object store if runs grow to thousands of shots. |
| A separate LLM client (not `ai_provider`) | Keeps Explorer standalone and pinned to GPT-5.6 with JSON-mode output. |
| Plain-text memory recall | Knowledge is matched by keywords and recency, not vector search. This is also marked as a `ponytail:` shortcut: upgrade when an app's knowledge grows past a few hundred items. |

## How the pieces talk

```
Browser ──HTTPS──▶ Explorer tab ──REST (poll)──▶ API ──start / signal / cancel──▶ Temporal
                                                  │                                  │
                                                  ▼                                  ▼ activities
                                              Postgres ◀──────── journal ─────── Explorer worker
                                                                                     │   │   │
                                                         Vault (login) ◀─────────────┘   │   └──▶ LiteLLM ▶ GPT-5.6
                                                                                         ▼
                                                                     Headless Chromium ──▶ App under test
```

- **The API never talks to the worker directly.** It starts, signals or cancels the workflow, and otherwise reads and writes Postgres.
- **Answers to questions need no signal.** The API stores the answer, and the waiting mission sees it by polling the database every 5 s.
- **The worker writes classic Vantage rows directly** in the promote step. It does not call the API.

## Deployables and processes

| Process | Start command | Notes |
|---|---|---|
| API | existing Vantage API process | The router is part of the API. |
| Explorer worker | `uv run --env-file .env --package explorer-worker python -m explorer_worker.worker` | Dev scripts run it under `watchfiles` for hot reload. See [document 8](08-operations-and-configuration.md). |
| Web | existing Vite dev server or build | |

If no worker is polling `explorer-task-queue`, starting a run returns **503 `EXPLORER_UNAVAILABLE`**, and onboarding records a failed discovery run with reason `worker_unavailable`.

## Tenant and security boundaries

- Every endpoint resolves the caller's organization (`CurrentOrgIdDep`) and joins through `Application.organization_id`. A run, mission, test, question or shot from another organization returns 404. There are no finer role checks.
- Logins never reach the model. Sign-in is done by code. Generated tests write `{{username}}`/`{{password}}` placeholders, which the exported project resolves from its own config.
- "Simulated server answers" in the hunt are intercepted inside Explorer's own browser (`page.route`). Nothing is sent to the real server.
