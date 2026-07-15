# Story 1.1: Repository & Service Scaffold

Status: ready-for-dev

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

- [ ] Task 1: Scaffold the monorepo directory structure and workspace tooling (AC: 1)
  - [ ] Create the exact Structural Seed tree at repo root: `apps/web/`, `apps/api/`, `apps/workers/discovery/`, `apps/workers/generation/`, `packages/domain/`, `packages/workflows/`, `packages/ai_provider/`, `packages/delivery_adapters/`, `packages/ci_instructions/`, `packages/secrets_client/`, `migrations/` — no extra top-level app/package directories, no renaming
  - [ ] Set up a `uv` workspace (root `pyproject.toml` with `[tool.uv.workspace]` members covering `apps/api`, `apps/workers/discovery`, `apps/workers/generation`, and every `packages/*`) pinned to Python 3.14.6 — `uv` is already the project's Python tool (see `_bmad/scripts/*.py` invocation convention)
  - [ ] Scaffold `apps/web` as a standalone Vite project (does not join the `uv` workspace); choose npm or pnpm workspaces only if a second JS package becomes necessary later — not needed for this story
  - [ ] Stub each `packages/*` port package with only its fixed Protocol interface from the Architecture Spine's Module Contracts section — no adapter implementations yet (those land in the epics that own them: `AIProvider` implementations in Epic 2/7, `DeliveryAdapter` implementations in Epic 5, `CIInstructionsGenerator` implementation in Epic 5, `SecretsClient` implementation in Epic 1 Story 1.3): `packages/ai_provider.AIProvider`, `packages/delivery_adapters.DeliveryAdapter`, `packages/ci_instructions.CIInstructionsGenerator`, `packages/secrets_client.SecretsClient` — signatures must match architecture's Module Contracts verbatim, since two independently-built modules agree on these byte-for-byte
- [ ] Task 2: Bootstrap `apps/api` on FastAPI + SQLModel + Alembic + PostgreSQL (AC: 2)
  - [ ] Initialize a FastAPI app with a health-check endpoint (e.g. `GET /health`)
  - [ ] Add one minimal SQLModel entity in `packages/domain` solely to prove the DB wiring end-to-end for this story — do not build out the full `Organization`/`Application`/auth domain model here, that belongs to Stories 1.2/1.3
  - [ ] Wire Alembic against PostgreSQL 18.4, generate and apply the first migration for that entity
  - [ ] Confirm FastAPI's auto-generated OpenAPI spec (`/openapi.json`) is served and includes the entity's schema
- [ ] Task 3: Bootstrap `apps/web` on React 19 + Vite + TypeScript (AC: 3)
  - [ ] Scaffold via Vite's React + TypeScript template on Vite 8.1.x
  - [ ] Attempt TypeScript 7.0 GA first, per architecture; verify the chosen OpenAPI-to-TS codegen tool actually supports TS 7.0's native-Go compiler — if it does not, pin TypeScript 5.9 as the architecture-approved fallback and record which was used in Completion Notes
  - [ ] Add an OpenAPI-to-TypeScript codegen step (e.g. `openapi-typescript` or `orval`) pointed at `apps/api`'s `/openapi.json`, wired as an npm script (e.g. `generate:api-types`)
  - [ ] Add one minimal component/page that imports and renders a generated type from `apps/api`'s spec, proving the no-hand-written-duplicate-type rule holds end-to-end
- [ ] Task 4: Wire the Temporal Python SDK end-to-end (AC: 4)
  - [ ] Add the Temporal Python SDK (current GA) as a dependency of `apps/api` and `packages/workflows`
  - [ ] Define one trivial no-op Workflow in `packages/workflows`, containing no I/O (AD-2) — this is the same workflow shell that Story 2.5's `InferenceActivity` will later graduate into a real `GenerationWorkflow` (`[UPDATED 2026-07-15]` originally Story 3.2's job; that story is removed), so name it/structure it so it can grow into `GenerationWorkflow` rather than being throwaway code
  - [ ] Register and run this workflow from a worker process in `apps/workers/discovery` or `apps/workers/generation` (at least one is sufficient for this story)
  - [ ] Wire a Temporal client connection from `apps/api` capable of starting the workflow and confirming completion (a dev-only smoke-test script or startup check is sufficient — a real trigger endpoint is not required until Epic 2/3)
  - [ ] Document the local-dev Temporal server dependency (e.g. Temporal CLI `temporal server start-dev` or a docker-compose service) — this is dev ergonomics only, not the deferred SaaS/on-prem Temporal-hosting decision
- [ ] Task 5: Stand up platform CI on GitHub Actions (AC: 5)
  - [ ] Add `.github/workflows/ci.yml`, triggered on every push
  - [ ] Python side: lint (ruff), type-check (mypy or pyright), test (pytest) across `apps/api`, `apps/workers/*`, and every `packages/*`
  - [ ] Node side: lint (eslint), type-check (tsc), test (vitest), and build for `apps/web`
  - [ ] Add a drift check that regenerates `apps/web`'s API types from `apps/api`'s OpenAPI spec and fails the build if the checked-in types differ — this is what makes AD-6's "no hand-written duplicate" rule enforceable, not just conventional
- [ ] Task 6: Verify end-to-end and record evidence (AC: 1-5)
  - [ ] `apps/api` boots locally and serves `/health` and `/openapi.json`
  - [ ] `apps/web` dev server boots and renders the proof component using a generated type
  - [ ] Alembic migration applies cleanly against a local PostgreSQL 18.4 instance
  - [ ] The no-op workflow starts and completes via the wired Temporal client, observable via Temporal CLI/Web UI
  - [ ] CI workflow is green on a clean push

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

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
