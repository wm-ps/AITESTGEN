# AITestGen — Application Intelligence Platform

Monorepo scaffolded to the architecture spine's fixed module boundaries
(see `_bmad-output/planning-artifacts/architecture/`). Story 1.1 wired the
core stack end-to-end; Stories 1.2 (sign-in, Organization scoping) and 1.3
(Application onboarding) add the first real product features.

> 📘 **New to this codebase? Read the [Developer Guide](docs/DEVELOPER_GUIDE.md)** —
> it explains what each module does, where it deploys, the core architecture rules,
> and a step-by-step runbook for bringing the whole stack up locally.

## Layout

```
apps/
  web/          React 19 + Vite + TypeScript SPA (API types generated from apps/api's OpenAPI spec — AD-6)
  api/          FastAPI service (auth, CRUD, curation; starts/queries workflows)
  workers/
    discovery/   Runs the no-op DiscoveryWorkflow shell today; DiscoveryActivity (Playwright) + InferenceActivity land in Epic 2
    generation/  GenerationWorkflow worker; Scenario/Playwright generation  [built in Epic 4]
packages/
  domain/           SQLModel entities shared by api + workers (Organization, PlatformUser, Application, DiscoveryRun)
  workflows/        Temporal workflows — orchestration only, no I/O (AD-2)
  ai_provider/      AIProvider port (AD-3)
  delivery_adapters/  DeliveryAdapter port — retained seam only, feature removed (AD-4)
  ci_instructions/    CIInstructionsGenerator port — retained seam only, feature removed
  secrets_client/   SecretsClient port (AD-5); VaultSecretsClient adapter lands in Story 1.3
migrations/       Alembic migration scripts (script_location = ./migrations)
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.14.6 is auto-installed via `.python-version`)
- Node.js 22.18+ (for `apps/web`)
- Docker (for local Postgres + Temporal + Vault)

## Local development

Start the local-dev dependencies (Postgres 18.4 + a Temporal dev server + a dev-mode
Vault — **dev ergonomics only**, not the deferred production hosting decisions):

```bash
docker compose up -d
```

Install and apply migrations:

```bash
uv sync --all-packages
uv run alembic upgrade head
```

Seed a dev Organization + user (no self-service registration exists — see Story 1.2):

```bash
uv run --package api python -m api.scripts.seed_dev_data
# creates dev@example.com / devpassword123 in "Dev Organization"
# pass your own email/password/org name/display name as positional args to override
```

Run the API (serves http://localhost:8000, OpenAPI at `/openapi.json`):

```bash
uv run --package api uvicorn api.main:app --reload --port 8000
```

Run the discovery worker (needed for onboarding an Application to actually start its
DiscoveryRun's workflow — otherwise it just sits queued):

```bash
uv run --package discovery-worker python -m discovery_worker.worker
```

Run the web app (http://localhost:5173), then sign in with the seeded credentials above:

```bash
cd apps/web
npm install
npm run generate:api-types   # regenerate TS types from the running API's OpenAPI spec (AD-6)
npm run dev
```

Run the generation worker, then the Temporal end-to-end smoke test (Story 1.1's original
proof-of-wiring check — unrelated to onboarding/discovery):

```bash
uv run --package generation-worker python -m generation_worker.worker
uv run --package api python -m api.scripts.temporal_smoke_test
```

## Tests & checks (mirrors CI)

```bash
uv run ruff check .          # Python lint
uv run pyright               # Python type-check
uv run pytest                # Python tests (DB/Vault/Temporal-dependent tests skip if unreachable)

cd apps/web
npm run lint                 # oxlint
npx tsc -b                   # type-check
npm test                     # vitest
npx vite build               # production build
```
