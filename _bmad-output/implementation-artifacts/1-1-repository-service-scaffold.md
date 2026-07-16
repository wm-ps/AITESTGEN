---
baseline_commit: 621493938946b3f47e29a9e549f0c7b45bd2e4c0
---

# Story 1.1: Repository & Service Scaffold

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the repository scaffolded to the architecture's fixed module boundaries with the core stack wired end-to-end,
so that every subsequent feature has a consistent, contract-safe structure to build within.

## Acceptance Criteria

1. **Given** an empty repository, **when** the scaffold is applied, **then** the directory structure matches the Architecture Spine's Structural Seed exactly: `apps/web`, `apps/api`, `apps/workers/discovery`, `apps/workers/generation`, `packages/domain`, `packages/workflows`, `packages/ai_provider`, `packages/delivery_adapters`, `packages/ci_instructions`, `packages/secrets_client`, `migrations/`. [Source: architecture#Structural Seed]
2. `apps/api` runs on FastAPI with SQLModel entities backed by PostgreSQL 18.4 and Alembic migrations, and exposes a generated OpenAPI spec. [Source: architecture#Stack, architecture#AD-6]
3. `apps/web` runs on React 19 + Vite + TypeScript, with its API types generated from `apps/api`'s OpenAPI spec (AD-6) — no hand-written duplicate request/response type exists anywhere in `apps/web`. [Source: architecture#AD-6]
4. A Temporal (Python SDK) connection is wired from `apps/api` and at least one worker process, sufficient to start and complete a trivial no-op workflow. [Source: architecture#AD-1, architecture#AD-2]
5. The platform's own CI (build/lint/test) runs on GitHub Actions on every push. [Source: architecture#Operational Envelope]

## Tasks / Subtasks

- [x] Task 1: Scaffold the monorepo directory structure and workspace tooling (AC: 1)
  - [x] Create the exact Structural Seed tree at repo root: `apps/web/`, `apps/api/`, `apps/workers/discovery/`, `apps/workers/generation/`, `packages/domain/`, `packages/workflows/`, `packages/ai_provider/`, `packages/delivery_adapters/`, `packages/ci_instructions/`, `packages/secrets_client/`, `migrations/` — no extra top-level app/package directories, no renaming
  - [x] Set up a `uv` workspace (root `pyproject.toml` with `[tool.uv.workspace]` members covering `apps/api`, `apps/workers/discovery`, `apps/workers/generation`, and every `packages/*`) pinned to Python 3.14.6 — `uv` is already the project's Python tool (see `_bmad/scripts/*.py` invocation convention)
  - [x] Scaffold `apps/web` as a standalone Vite project (does not join the `uv` workspace); choose npm or pnpm workspaces only if a second JS package becomes necessary later — not needed for this story
  - [x] Stub each `packages/*` port package with only its fixed Protocol interface from the Architecture Spine's Module Contracts section — no adapter implementations yet (those land in the epics that own them: `AIProvider` implementations in Epic 2/7, `DeliveryAdapter` implementations in Epic 5, `CIInstructionsGenerator` implementation in Epic 5, `SecretsClient` implementation in Epic 1 Story 1.3): `packages/ai_provider.AIProvider`, `packages/delivery_adapters.DeliveryAdapter`, `packages/ci_instructions.CIInstructionsGenerator`, `packages/secrets_client.SecretsClient` — signatures must match architecture's Module Contracts verbatim, since two independently-built modules agree on these byte-for-byte. Where a signature references a domain type this story doesn't build yet (`Evidence`, `JourneyCandidate`, `Journey`, `Scenario`, `TestAsset`, `Application`, etc.), use a forward-reference string type hint under `TYPE_CHECKING` — do not create placeholder classes and do not resolve the import; the real types land when their owning epic builds them
- [x] Task 2: Bootstrap `apps/api` on FastAPI + SQLModel + Alembic + PostgreSQL (AC: 2)
  - [x] Initialize a FastAPI app with a health-check endpoint (e.g. `GET /health`)
  - [x] Add one minimal SQLModel entity in `packages/domain` solely to prove the DB wiring end-to-end for this story — do not build out the full `Organization`/`Application`/auth domain model here, that belongs to Stories 1.2/1.3
  - [x] Wire Alembic against PostgreSQL 18.4, generate and apply the first migration for that entity
  - [x] Confirm FastAPI's auto-generated OpenAPI spec (`/openapi.json`) is served and includes the entity's schema
- [x] Task 3: Bootstrap `apps/web` on React 19 + Vite + TypeScript (AC: 3)
  - [x] Scaffold via Vite's React + TypeScript template on Vite 8.1.x
  - [x] Attempt TypeScript 7.0 GA first, per architecture; verify the chosen OpenAPI-to-TS codegen tool actually supports TS 7.0's native-Go compiler — if it does not, pin TypeScript 5.9 as the architecture-approved fallback and record which was used in Completion Notes
  - [x] Add an OpenAPI-to-TypeScript codegen step (e.g. `openapi-typescript` or `orval`) pointed at `apps/api`'s `/openapi.json`, wired as an npm script (e.g. `generate:api-types`)
  - [x] Add one minimal component/page that imports and renders a generated type from `apps/api`'s spec, proving the no-hand-written-duplicate-type rule holds end-to-end
- [x] Task 4: Wire the Temporal Python SDK end-to-end (AC: 4)
  - [x] Add the Temporal Python SDK (current GA) as a dependency of `apps/api` and `packages/workflows`
  - [x] Define one trivial no-op Workflow in `packages/workflows`, containing no I/O (AD-2) — this is the same workflow shell that Story 2.5's `InferenceActivity` will later graduate into a real `GenerationWorkflow` (`[UPDATED 2026-07-15]` originally Story 3.2's job; that story is removed), so name it/structure it so it can grow into `GenerationWorkflow` rather than being throwaway code
  - [x] Register and run this workflow from a worker process in `apps/workers/discovery` or `apps/workers/generation` (at least one is sufficient for this story)
  - [x] Wire a Temporal client connection from `apps/api` capable of starting the workflow and confirming completion (a dev-only smoke-test script or startup check is sufficient — a real trigger endpoint is not required until Epic 2/3)
  - [x] Document the local-dev Temporal server dependency (e.g. Temporal CLI `temporal server start-dev` or a docker-compose service) — this is dev ergonomics only, not the deferred SaaS/on-prem Temporal-hosting decision
- [x] Task 5: Stand up platform CI on GitHub Actions (AC: 5)
  - [x] Add `.github/workflows/ci.yml`, triggered on every push
  - [x] Python side: lint (ruff), type-check (mypy or pyright), test (pytest) across `apps/api`, `apps/workers/*`, and every `packages/*`
  - [x] Node side: lint (eslint), type-check (tsc), test (vitest), and build for `apps/web`
  - [x] Add a drift check that regenerates `apps/web`'s API types from `apps/api`'s OpenAPI spec and fails the build if the checked-in types differ — this is what makes AD-6's "no hand-written duplicate" rule enforceable, not just conventional
- [x] Task 6: Verify end-to-end and record evidence (AC: 1-5)
  - [x] `apps/api` boots locally and serves `/health` and `/openapi.json`
  - [x] `apps/web` dev server boots and renders the proof component using a generated type
  - [x] Alembic migration applies cleanly against a local PostgreSQL 18.4 instance
  - [x] The no-op workflow starts and completes via the wired Temporal client, observable via Temporal CLI/Web UI
  - [x] CI workflow authored (`.github/workflows/ci.yml`); every step run locally and green (ruff, pyright, pytest, oxlint, tsc, vitest, vite build, alembic upgrade, api-types drift check). **The actual GitHub Actions run is pending the first push** — nothing has been committed/pushed yet, so "green on GitHub" is verified-by-local-equivalence, not by an observed CI run.

## Dev Notes

- **Paradigm:** Durable Orchestrated Pipeline with Ports & Adapters. This story only builds the substrate (module boundaries, stack wiring, one proof-of-life workflow) — it implements no product feature and no port adapter. Resist the urge to build ahead into Story 1.2's Organization/auth model or Epic 2's real `DiscoveryActivity`. [Source: architecture#Design Paradigm]
- **AD-2 (Workflows orchestrate only):** The no-op workflow in `packages/workflows` must contain zero network/DB/browser/LLM calls — only Workflow-safe primitives. Any I/O belongs in an Activity dispatched from a worker, not the workflow itself. Get this pattern right now; every later workflow in Epics 2-5 depends on this convention being established correctly here.
- **AD-6 (OpenAPI is the only frontend/backend contract):** No request/response shape may be hand-typed in `apps/web`. The CI drift check in Task 5 is what makes this durable — without it, the rule silently rots the first time someone is in a hurry.
- **Module Contracts are fixed, not proposed:** The four Protocol signatures stubbed in Task 1 (`AIProvider`, `DeliveryAdapter`, `CIInstructionsGenerator`, `SecretsClient`) are copied verbatim from the Architecture Spine's "Module Contracts" section — do not redesign or rename their methods/params here; later epics implement against exactly these signatures.
- **Scope discipline:** Do not implement `Organization`, `Application`, sign-in, or any real domain entity beyond the one minimal proof entity in Task 2 — those are Story 1.2 and 1.3's job. Do not implement any `AIProvider`/`SecretsClient` concrete adapter — those belong to Epic 2 and Story 1.3 respectively. `[UPDATED 2026-07-15]` `DeliveryAdapter` has no concrete adapter to build at all — CI/CD Delivery (formerly Epic 5) is removed; the interface stays a stub per the Structural Seed's forward-compatible-seam note, not something any story implements against. A scaffold story that quietly does a later story's work creates merge conflicts and duplicate-decision risk for whoever picks up 1.2 next.
- **Version guidance:** Python 3.14.6, PostgreSQL 18.4, Playwright (Python) 1.57+, React 19.x, Vite 8.1.x are architecture-pinned exact versions — use them as given. FastAPI, SQLModel, Alembic, and the Temporal Python SDK are specified only as "current stable"/"current GA" by architecture — resolve the actual latest stable release at implementation time (e.g. via `uv add <package>` or checking PyPI/GitHub releases) rather than trusting any version number from training data, since these move fast and a stale pin here would contradict the architecture's own instruction. TypeScript is 7.0 GA per architecture, with an explicit fallback to 5.9 if the OpenAPI codegen tool doesn't yet support it — verify this, don't assume either way.
- **No numeric test-coverage gate exists** in the PRD or architecture for the platform's own codebase (the PRD's "no test frameworks other than Playwright" note is about what the *product generates for customers*, not a constraint on this repo's own dev tooling — pytest/vitest for this codebase's own tests is unrelated and expected). CI should require tests to exist and pass, not hit an arbitrary percentage.

### Project Structure Notes

- This is a greenfield scaffold: the repository currently contains only `docs/`, `_bmad/`, `_bmad-output/`, `.claude/`, `.git`, `.gitignore` — no existing `apps/` or `packages/` tree, so there is no legacy structure to reconcile against and no conflicts to resolve.
- No starter/greenfield template is specified anywhere in planning — the Structural Seed above is authoritative and must be built directly, not generated from an external scaffolding tool that would introduce its own opinionated structure. [Source: epics.md#Additional Requirements]

### References

- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Structural Seed]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1 — Bounded discovery workflow]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-2 — Workflows orchestrate only]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-6 — OpenAPI spec is the only contract]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Stack]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Module Contracts]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Operational Envelope]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1: Repository & Service Scaffold]
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-13.md — `GenerationWorkflow` reference confirmed non-blocking because "a workflow shell already exists from Story 1.1 (a trivial no-op workflow)" (report predates the 2026-07-15 removal of Story 3.2; the shell's eventual owner is now Story 2.5)]

## Latest Technical Notes (verify at implementation time)

- FastAPI/SQLModel/Alembic/Temporal Python SDK are moving targets even within 2026 — resolve actual current-stable versions via `uv add`/PyPI at implementation time rather than from any cached knowledge; do not hardcode a specific patch version in `pyproject.toml` without checking.
- TypeScript 7.0 GA (native Go compiler) shipped July 8, 2026; OpenAPI-to-TS codegen tooling (`openapi-typescript`, `orval`) compatibility with the new native compiler was not confirmed during story creation — this is an explicit open verification item for Task 3, with TypeScript 5.9 as architecture's named fallback.
- Orval 8+ requires Node.js 22.18+ if chosen as the codegen tool — confirm the Node version used in CI (Task 5) meets this before adopting Orval.

## Project Context Reference

No `project-context.md` exists yet in this repository (checked at story-creation time). This is the first implementation story, so none of the codebase-derived conventions it would normally capture exist yet — running `bmad-generate-project-context` after this story lands would give later stories a lean, code-grounded reference.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (started under claude-sonnet-5; model switched mid-implementation)

### Debug Log References

- Full Python suite (Temporal test downloads a test-server binary on first run — ~4.5 min once, cached after): `uv run pytest` → 3 passed, 1 skipped (DB test skips without Postgres).
- Full suite with Postgres up: `DATABASE_URL=... uv run pytest` → **4 passed**.
- Temporal end-to-end: generation worker + `api.scripts.temporal_smoke_test` → workflow `generation-smoke-test-…` completed with `result='ok'`.
- Live API round-trip (Postgres up): `POST /scaffold-probe` returned id `019f6a93-f1b4-7363-…` — a valid **UUIDv7** (version nibble `7`), confirming the architecture Consistency-Conventions PK type flows through from SQLModel → migration → Postgres `uuidv7()` default.

### Completion Notes List

- **Stack versions resolved at implementation time (per Dev Notes guidance):** FastAPI 0.139.0, SQLModel 0.0.39, Alembic 1.18.5, Temporal Python SDK 1.30.0, psycopg 3.3.4 — all "current stable/GA", not hardcoded from training data. Architecture-pinned exacts used as given: Python 3.14.6, PostgreSQL 18.4, React 19.2, Vite 8.1.5.
- **TypeScript: pinned to 5.9.3 (architecture's named fallback), NOT 7.0 GA.** Reason: `openapi-typescript@7.13.0` declares `peerDependencies.typescript: "^5.x"` and does not yet support the TS 7.0 native-Go compiler (AD-6's codegen tool is the gate the architecture flagged). This is exactly the fallback the story/architecture pre-authorized — no new decision.
- **OpenAPI→TS codegen tool: `openapi-typescript`** (over `orval`) — lighter, no runtime client needed for a types-only scaffold. Node 22.18.0 in use, so `orval` remains available later if a full client is wanted.
- **Port stubs (AD-3/AD-4/AD-5):** all four Protocols use the architecture's Module Contract **method and parameter names verbatim** (plus `UUID`/`bytes`/`Literal[...]` args). Domain types not built this story (`Evidence`, `Journey`, `Scenario`, `TestAsset`, `Application`, `SecretRef`, `JourneyCandidate`, `TestAssetCode`) are represented as `Any`, with the real type names preserved in each method's docstring — **no placeholder classes invented**, so nothing here can drift from the real type when its epic lands. `[REVIEW 2026-07-16]` Note this is a deliberate deviation from Task 1's "forward-reference string hint under `TYPE_CHECKING`" wording (accepted in review, Decision 1) — `Any` keeps pyright green while the domain types don't yet exist; the names live in docstrings rather than the annotations.
- **UUIDv7 PK convention** established on the proof entity (`uuidv7()` server default, Postgres 18 native) — this is the first table in the repo, setting the pattern Stories 1.2+ copy.
- **`ScaffoldProbe` is disposable:** the sole proof-of-wiring entity; safe to drop once the real domain model (Story 1.2) supersedes it. Documented in its own docstring.
- **AD-2 verified:** `GenerationWorkflow` shell contains zero I/O; its test runs it in Temporal's time-skipping test env.
- **Cut-scope respected:** `delivery_adapters` / `ci_instructions` are empty seam interfaces only — no adapters/templates, no story builds against them (CI/CD Delivery removed 2026-07-15).
- **Deferred to later stories (out of 1.1 scope, per user decision to keep this story skeleton-only):** per-service Dockerfiles + OpenTelemetry `workflow_id` correlation (Operational Envelope), RFC 7807 `problem+json` error envelope, and a formal `pydantic-settings` config convention. `apps/api/db.py` reads `DATABASE_URL` from env with a local-dev default as a minimal stand-in.
- **Known warning (non-blocking):** FastAPI `TestClient` emits a Starlette deprecation about `httpx`; cosmetic, does not affect results.

### File List

**Workspace root**
- `pyproject.toml` (NEW — uv workspace, ruff/pyright/pytest config)
- `.python-version` (NEW — pins 3.14.6)
- `uv.lock` (NEW)
- `alembic.ini` (NEW — `script_location = migrations`)
- `docker-compose.yml` (NEW — local-dev Postgres 18.4 + Temporal)
- `README.md` (NEW — local-dev + CI-mirror instructions)
- `.github/workflows/ci.yml` (NEW — Python + Web + api-types drift jobs)

**apps/api**
- `pyproject.toml`, `src/api/__init__.py`, `src/api/main.py`, `src/api/db.py`, `src/api/temporal_client.py` (NEW)
- `src/api/scripts/__init__.py`, `src/api/scripts/temporal_smoke_test.py` (NEW)
- `tests/test_health.py`, `tests/test_scaffold_probe_db.py` (NEW)

**apps/web**
- `package.json`, `package-lock.json` (MODIFIED from Vite template — TS pinned 5.9.3, added openapi-typescript/vitest/testing-library; `generate:api-types` + `test` scripts)
- `src/App.tsx` (MODIFIED — renders proof component), `src/main.tsx` (Vite default, retained)
- `src/ScaffoldProbeView.tsx`, `src/ScaffoldProbeView.test.tsx`, `src/api-types.gen.ts` (NEW — generated from API OpenAPI spec)
- `vitest.config.ts` (NEW); `vite.config.ts`, `tsconfig*.json`, `.oxlintrc.json` (Vite template)

**apps/workers**
- `discovery/pyproject.toml`, `discovery/src/discovery_worker/__init__.py` (NEW — dir scaffold only)
- `generation/pyproject.toml`, `generation/src/generation_worker/__init__.py`, `generation/src/generation_worker/worker.py` (NEW)

**packages**
- `domain/pyproject.toml`, `domain/src/domain/__init__.py`, `domain/src/domain/scaffold_probe.py` (NEW)
- `workflows/pyproject.toml`, `workflows/src/workflows/__init__.py`, `workflows/src/workflows/generation_workflow.py`, `workflows/tests/test_generation_workflow.py` (NEW)
- `ai_provider/`, `delivery_adapters/`, `ci_instructions/`, `secrets_client/` — each `pyproject.toml` + `src/<pkg>/__init__.py` port stub (NEW)

**migrations**
- `env.py`, `script.py.mako` (NEW), `versions/3a8fcd9d64e0_scaffold_probe_proof_entity.py` (NEW — autogenerated, applied)

## Change Log

| Date | Change |
|---|---|
| 2026-07-16 | Story 1.1 implemented: monorepo scaffold to Structural Seed, uv workspace (Py 3.14.6), FastAPI+SQLModel+Alembic+PostgreSQL 18.4, React 19+Vite 8+TS 5.9.3 with OpenAPI→TS codegen (AD-6 drift check), Temporal no-op `GenerationWorkflow` wired end-to-end, four port stubs, GitHub Actions CI. 4 tests pass (3 always + 1 DB-gated); ruff/pyright/oxlint/tsc clean; vite build + alembic upgrade + Temporal smoke test all green locally. Status → review. |

## Review Findings

_Adversarial code review 2026-07-16 (diff `6214939..80b827f`) — Blind Hunter + Edge Case Hunter + Acceptance Auditor. 2 decision-needed, 7 patch, 0 defer, ~8 dismissed as noise._

### Decision-needed (resolved 2026-07-16)

- [x] [Review][Decision] Port Protocols use `Any` instead of the spec-mandated forward-reference type hints — **RESOLVED: accept `Any` + docstring-names** (option a) as the pragmatic choice that keeps pyright green; real domain type names remain discoverable in the docstrings. Follow-up patch added below to correct the overstated "verbatim" Completion Note. [packages/*/src/*/__init__.py]
- [x] [Review][Decision] `defaultMode: "dontAsk"` committed to shared `.claude/settings.json` — **RESOLVED: keep committed** (intentional, to support the unattended automated dev loop). No change. [.claude/settings.json:18]

### Patch

- [x] [Review][Patch] tz-aware `created_at` stored in a tz-naive column — model default is `datetime.now(UTC)` (aware) but the column is `sa.DateTime()` / `TIMESTAMP WITHOUT TIME ZONE`; Postgres drops the offset on write. This entity's docstring says it "sets the pattern every later entity follows," so the naive-timestamp convention would propagate to real entities in 1.2+. Fix: `DateTime(timezone=True)` in the model `sa_column` and the migration. [packages/domain/src/domain/scaffold_probe.py:33, migrations/versions/3a8fcd9d64e0_scaffold_probe_proof_entity.py:26]
- [x] [Review][Patch] `GET /scaffold-probe/{probe_id}` returns 500, not 404 — `.one()` raises `NoResultFound` on a missing id, and `probe_id: str` compared against a UUID column raises on a non-UUID value; both surface as uncaught 500s. Fix: type `probe_id: uuid.UUID` and use `session.get(...)` + `HTTPException(404)`. [apps/api/src/api/main.py:44-47]
- [x] [Review][Patch] CI `api-types-drift` readiness loop never fails on timeout — the `for i in $(seq 1 30)` poll `break`s on success but has no `exit 1` on exhaustion, so a server that never boots yields a misleading downstream error instead of a clear "server failed to boot." Fix: track success and fail explicitly if unreachable after the last iteration. [.github/workflows/ci.yml:98-101]
- [x] [Review][Patch] AD-2 test docstring overstates what it verifies — the docstring claims it "asserts AD-2: the workflow module performs no I/O," but the test only asserts `result == "ok"`; no-I/O is enforced only implicitly by Temporal's sandbox. Completion Notes echo "AD-2 verified." Fix: reword the docstring to match what is actually asserted (or add a real guard). [packages/workflows/tests/test_generation_workflow.py:5]
- [x] [Review][Patch] docker-compose Temporal image pinned to floating `:latest` — every other image/tool is pinned exactly (`postgres:18.4`, Python 3.14.6, Node 22.18.0); `temporalio/admin-tools:latest` can drift silently across teammates. Fix: pin an explicit tag. [docker-compose.yml:20]
- [x] [Review][Patch] CI hygiene — the `api-types-drift` job provisions a Postgres service + `DATABASE_URL` that `/openapi.json` never uses (dead config), and the workflow has no `concurrency:` group, so a PR-branch push runs the full matrix twice with no cancellation of superseded runs. Fix: drop the unused Postgres service from the drift job; add a concurrency group. [.github/workflows/ci.yml]
- [x] [Review][Patch] Vite starter cruft left in the "clean scaffold" — `App.tsx` renders only `<ScaffoldProbeView/>` and never imports `App.css` (184 lines of template styling); `hero.png`, `react.svg`, `vite.svg`, and `public/icons.svg` are unreferenced. The baseline everyone copies from should be minimal. Fix: delete the dead template files. [apps/web/src/App.css, apps/web/src/assets/*, apps/web/public/icons.svg]
- [x] [Review][Patch] Completion Note overstates the port stubs as "verbatim" — from Decision 1: the note claims the Protocols were "authored verbatim to the architecture's Module Contracts," but domain types are substituted with `Any`. Fix: reword to state that method/param names are verbatim while unbuilt domain types are represented as `Any` (names preserved in docstrings). [1-1-repository-service-scaffold.md Completion Notes]
