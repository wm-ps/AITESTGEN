# AITestGen — Application Intelligence Platform

Monorepo scaffolded to the architecture spine's fixed module boundaries
(see `_bmad-output/planning-artifacts/architecture/`). Story 1.1 wires the
core stack end-to-end; no product feature is implemented yet.

## Layout

```
apps/
  web/          React 19 + Vite + TypeScript SPA (API types generated from apps/api's OpenAPI spec — AD-6)
  api/          FastAPI service (auth, CRUD, curation; starts/queries workflows)
  workers/
    discovery/   DiscoveryActivity (Playwright) + InferenceActivity  [built in Epic 2]
    generation/  GenerationWorkflow worker; Scenario/Playwright generation  [built in Epic 4]
packages/
  domain/           SQLModel entities shared by api + workers
  workflows/        Temporal workflows — orchestration only, no I/O (AD-2)
  ai_provider/      AIProvider port (AD-3)
  delivery_adapters/  DeliveryAdapter port — retained seam only, feature removed (AD-4)
  ci_instructions/    CIInstructionsGenerator port — retained seam only, feature removed
  secrets_client/   SecretsClient port (AD-5); implementations land in Story 1.3
migrations/       Alembic migration scripts (script_location = ./migrations)
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.14.6 is auto-installed via `.python-version`)
- Node.js 22.18+ (for `apps/web`)
- Docker (for local Postgres + Temporal)

## Local development

Start the local-dev dependencies (Postgres 18.4 + a Temporal dev server —
**dev ergonomics only**, not the deferred production Temporal-hosting decision):

```bash
docker compose up -d
```

Install and apply migrations:

```bash
uv sync --all-packages
uv run alembic upgrade head
```

Run the API (serves http://localhost:8000, OpenAPI at `/openapi.json`):

```bash
uv run --package api uvicorn api.main:app --reload --port 8000
```

Run the web app (http://localhost:5173):

```bash
cd apps/web
npm install
npm run generate:api-types   # regenerate TS types from the running API's OpenAPI spec (AD-6)
npm run dev
```

Run the generation worker, then the Temporal end-to-end smoke test:

```bash
uv run --package generation-worker python -m generation_worker.worker
uv run --package api python -m api.scripts.temporal_smoke_test
```

## Tests & checks (mirrors CI)

```bash
uv run ruff check .          # Python lint
uv run pyright               # Python type-check
uv run pytest                # Python tests (DB test skips if no Postgres reachable)

cd apps/web
npm run lint                 # oxlint
npx tsc -b                   # type-check
npm test                     # vitest
npx vite build               # production build
```
