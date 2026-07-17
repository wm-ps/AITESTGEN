---
baseline_commit: 48b6499e08423320a0156e02720f1e8e2ba7d66c
---

# Story 2.2: Autonomous Exploration Captures Evidence

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

*Updated 2026-07-15 — no configurable scope; Discovery always explores the entire Application (FR-4 removed).*

As a user,
I want the platform to autonomously explore my entire Application,
so that raw discovery signal is captured as the basis for journey mapping.

## Acceptance Criteria

1. **Given** a running Discovery Run, **when** `DiscoveryActivity` navigates pages, exercises UI actions and forms, and invokes APIs across the entire Application, **then** each captured page, action, form, API call, and state transition is written as an `Evidence` row tagged with `discovery_run_id`. [Source: epics.md#Story 2.2; FR-6; architecture#AD-8]
2. Large binary artifacts (screenshots, DOM snapshots) are referenced via an object-storage key, never stored inline in Postgres. [Source: architecture#AD-8]
3. The Discovery Progress screen's live-feed list shows the most recently captured pages/actions/API calls, newest first, in monospace, appended as discovery proceeds. [Source: epics.md#Story 2.2; DESIGN.md#Typography — mono-inline]

## Tasks / Subtasks

- [x] Task 1: Add the `Evidence` domain entity (AC: 1, 2)
  - [x] Add `Evidence` (`discovery_run_id` FK — immutable once set, `type` [`page` | `action` | `form` | `api_call` | `state_transition`], structured metadata, `object_storage_key` nullable, `journey_id` nullable, `captured_at`) to `packages/domain`, following the UUIDv7/UUIDv4 id convention from Story 1.3
  - [x] **`journey_id` must stay null from this story.** Per AD-8, `InferenceActivity` (Story 2.5) — not `DiscoveryActivity` — is the sole writer of `Evidence.journey_id`. Do not set it here even provisionally; a captured row with no Journey yet is the correct, expected state until Story 2.5 runs
  - [x] Alembic migration
- [x] Task 2: Add a thin object-storage abstraction for binary evidence (AC: 2)
  - [x] Architecture fixes the *shape* (structured metadata in Postgres, binaries referenced by object-storage key, never inline — AD-8) but explicitly defers the specific backend provider, and — unlike `AIProvider`/`DeliveryAdapter`/`SecretsClient` — does not name a formal Protocol port for this in the Module Contracts section. Build a small internal abstraction anyway (e.g. `put(key, bytes) -> None` / `get(key) -> bytes`), consistent with the rest of the system's ports-and-adapters discipline, so the backend stays swappable when the deferred deployment-topology decision lands
  - [x] Recommended default adapter: **MinIO** (S3-compatible, self-hostable, trivial for local/CI, and swappable later for real S3/GCS/Azure Blob without changing the abstraction's shape since they all speak roughly the same object-key model) — a cloud-provider bucket is an equally valid alternative if preferred; document whichever is chosen in Completion Notes
  - [x] Screenshots and full DOM snapshots are written through this abstraction; the `Evidence.object_storage_key` column stores only the returned key, never the binary itself
- [x] Task 3: Build the real autonomous exploration loop in `DiscoveryActivity` (AC: 1, 2)
  - [x] Replace Story 2.1's stub with real behavior: establish a session using the Application's stored credentials (via `SecretsClient`, from Stories 1.3/1.4), then navigate every page reachable across the entire Application (`[UPDATED 2026-07-15]` no scope restriction — FR-4 removed), exercise UI actions/forms with generic/synthetic input data, and capture invoked API calls via Playwright's request/response interception
  - [x] Neither the PRD nor the Architecture Spine specifies an exact traversal algorithm — FR-6's description is "navigates the Application the way a thorough tester would." Treat the following as a sound, non-binding default rather than a spec to match exactly: breadth-first link/navigation-graph traversal; generic placeholder values keyed by input field type/name for form-filling; `page.on("request")`/`page.on("response")` (or the current Playwright-Python equivalent) to capture API calls
  - [x] For each captured page visit, UI action, form submission, API call, and detected state transition, write an `Evidence` row tagged with `discovery_run_id`; route any screenshot/DOM snapshot through Task 2's object store and store only the key
  - [x] **Do not implement FR-7's stop-condition logic here** (exhaustive-traversal detection) — that is Story 2.3's job, and it is also what actually sets `DiscoveryRun.status` to `complete`. `[UPDATED 2026-07-15]` There is no time-budget cutoff to implement — FR-5 is removed, and exhaustive traversal is the only stop condition (accepted risk, PRD §12 item 7: no safety cap against unbounded exploration). This story only needs the capture loop to be boundable for testing purposes — use a simple, clearly-marked placeholder (e.g. a max-iteration safety cap, test-only, not a product feature) rather than building real stop-condition detection prematurely; Story 2.3 replaces this placeholder with the real rule
- [x] Task 4: Build the Discovery Progress live-feed list (AC: 3)
  - [x] Show the most recently captured pages/actions/API calls, newest first, rendered in `{typography.mono-inline}` (raw evidence only — never authored UI copy, per the standing typography rule), appended as discovery proceeds
  - [x] No push channel is architecturally required — client-side polling of a simple "recent Evidence for this run" read endpoint is a reasonable default, consistent with the "boring technology" bias elsewhere in the architecture. A WebSocket/SSE push channel is a valid alternative but not required by any AC. (Note: the review-queue pending-count badge this reasoning was originally cross-referenced against is cut as of 2026-07-15 — see Story 3.1 — this story's live-feed polling is unaffected either way)
- [x] Task 5: Verify end-to-end and record evidence (AC: 1-3)
  - [x] Running a Discovery Run against a locally-hosted test target produces `Evidence` rows of each type (`page`, `action`, `form`, `api_call`, `state_transition`), all tagged with the correct `discovery_run_id` and `journey_id=null`
  - [x] A captured screenshot/DOM snapshot exists in the object store under the key referenced by its `Evidence` row, not inline in Postgres
  - [x] Discovery Progress's live-feed list updates with newest-first entries in monospace as a run proceeds

## Dev Notes

- **AD-8's Evidence-attribution split is the single most important rule in this story**: Discovery captures and tags with `discovery_run_id` only; attribution to a specific Journey (`journey_id`) happens later and elsewhere (Story 2.5's `InferenceActivity`). Getting this backwards — e.g. having `DiscoveryActivity` guess at a `journey_id` — would break the "which evidence supports *this* Journey" traceability the entire review-trust mechanic depends on.
- **The traversal algorithm is a genuine, acknowledged gap in the planning artifacts**, not an oversight on this story's part — FR-6 describes the desired outcome ("the way a thorough tester would") without prescribing a mechanism. The default given in Task 3 is a starting point; if pilot feedback later shows it's insufficient for real applications, that's a product/algorithm iteration, not a sign this story was implemented wrong.
- **Object storage has no named architectural port**, unlike the other three port packages — this is a deliberate observation, not an inconsistency to "fix" by inventing a `packages/object_store` structural-seed entry that doesn't exist in Story 1.1's fixed directory tree. Build the abstraction inside `apps/workers/discovery` (or wherever `DiscoveryActivity` lives) rather than adding a new top-level package.
- **Task boundary with Story 2.3, restated for clarity:** this story makes the capture loop *boundable* (test-only placeholder); Story 2.3 makes it *correct* (real exhaustive-traversal detection, and the actual `DiscoveryRun.status` transition). Don't let this story's placeholder stopping point leak into being treated as the real FR-7 implementation during code review. `[UPDATED 2026-07-15]` No time-budget detection to build anywhere — FR-5 removed.

### Project Structure Notes

- Adds `Evidence` to `packages/domain`, an object-storage abstraction inside `apps/workers/discovery`, and replaces Story 2.1's `DiscoveryActivity` stub with real behavior. No new top-level directories beyond Story 1.1's Structural Seed.
- **Depends on Stories 1.1–1.4 and 2.1 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. This story specifically needs Story 2.1's `DiscoveryRun`/`DiscoveryWorkflow`/stub `DiscoveryActivity`, and Stories 1.3/1.4's `SecretsClient`-stored Application credentials. `[UPDATED 2026-07-15]` Story 1.5 no longer exists.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: Autonomous Exploration Captures Evidence]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md §4.2 — FR-6, FR-7]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8 — evidence pointer granularity; #Deferred — object-storage backend provider]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Typography — mono-inline]
- [Source: _bmad-output/implementation-artifacts/2-1-start-a-discovery-run.md — `DiscoveryActivity` stub this story replaces with real behavior]

## Previous Story Intelligence

Story 2.1 remains `ready-for-dev`, so there is no implemented stub `DiscoveryActivity` yet to build on top of — check its File List once implemented for the exact stub signature/dispatch shape before starting Task 3. Stories 1.1–1.4 are also all still `ready-for-dev`; this story specifically needs 1.3/1.4's `SecretsClient`-backed Application credentials to be resolvable. Story 1.5 no longer exists (removed 2026-07-15).

## Latest Technical Notes

- Playwright Python 1.57+ is architecture-pinned (Story 1.1) — verify the current request/response interception API surface against whatever exact version is installed at implementation time, since Playwright's API has moved across versions.
- MinIO (if chosen for Task 2) — use its current-stable client library and server image; verify at implementation time rather than assuming a version.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run pytest apps/ packages/ -q` against a throwaway `postgres:18.4` container
  (`localhost:15434`) + the existing dev-mode Vault/Temporal containers + a newly added
  dev-mode MinIO container (`docker compose up -d minio`, `localhost:9000`) → **19 passed**
  (14 pre-existing + 5 new: the real crawl loop against a live local target
  (`test_crawler.py`), the full `discovery_activity` against real Postgres/Vault/MinIO
  (`test_discovery_activity_integration.py`), the rewritten workflow-dispatch test with a fake
  Activity, and 2 evidence-feed-endpoint tests).
- `uv run ruff check` / `uv run pyright` (apps/api, packages/domain, packages/workflows,
  apps/workers/discovery) → all clean.
- `npx vitest run` (apps/web) → **11 passed** (9 pre-existing + 2 new: `EvidenceLiveFeed`
  rendering + the updated `DiscoverJourneysPlaceholder` test). `npx tsc -b` / `npx oxlint` clean.
- Regenerated `apps/web/src/api-types.gen.ts` from a live API run (AD-6) after adding the
  evidence-feed endpoint.
- Real Playwright chromium (already cached in this environment) drives a purpose-built local
  test-target FastAPI app (`apps/workers/discovery/tests/fixtures/target_app.py` — not shipped
  product code, a test fixture only) through `discovery_activity` end-to-end, proving: session
  establishment via a generic login-form heuristic, BFS page traversal, form fill+submit,
  standalone-button clicks, and `fetch`-triggered API-call capture via
  `page.on("response")` — all 5 `Evidence` types produced.
- Cleaned up: no throwaway containers were removed yet — the same long-lived
  `aitestgen-pg-epic2` Postgres container and the compose-managed MinIO service are reused
  across Stories 2.2–2.5 in this session and torn down/left running per the final story's
  Debug Log.

### Completion Notes List

- **Object storage: MinIO**, added to `docker-compose.yml` as a first-class local-dev service
  (ports 9000 API / 9001 console, `minioadmin`/`minioadmin`) — not a throwaway workaround, a real
  new dependency per Task 2's recommendation. `ObjectStore.put(data, discovery_run_id) -> key` /
  `get(key) -> bytes` (`apps/workers/discovery/src/discovery_worker/object_store.py`), backed by
  the official `minio` Python client (S3-compatible). Deliberately deviates from the task's literal
  `put(key, bytes) -> None` example shape — `put` generates and returns the key itself rather than
  requiring the caller to invent one — the story explicitly flags that shape as "e.g.", not
  binding.
- **`Evidence.details` (not `metadata`)** — `metadata` is a reserved attribute name on SQLModel's
  declarative base (`SQLModel.metadata`); using it as a field name would shadow it. `details`
  (JSONB) holds the structured, per-type payload (URL, method, status, fields, ...) instead of
  five separately-typed columns — one JSONB column is the pragmatic choice given how much the
  shape varies across the 5 Evidence types, not premature under-normalization.
- **`Evidence.journey_id` has no FK constraint yet, in either the migration or the Python model** —
  the `journey` table doesn't exist until Story 2.5. The column is added now as a plain, nullable,
  indexed `UUID` with no `ForeignKey(...)` reference; Story 2.5 adds the FK (both the Python
  `ForeignKey("journey.id")` and an `ALTER TABLE` migration) once `journey` actually exists, same
  as any real incremental schema evolution.
- **`DiscoveryActivityInput`/`DiscoveryWorkflow.run` extended** (not left at Story 2.1's
  `application_id`/`secret_ref` alone) — `discovery_run_id` was added since the real Activity needs
  it to tag `Evidence` rows and (in later stories) update `DiscoveryRun.status`. Story 2.1's own
  test (`test_discovery_workflow.py`) was rewritten to use a **fake** `"DiscoveryActivity"`
  registration instead of the real one — the old test asserted the stub's trivial
  `"dispatched:{id}"` return value, which no longer holds now that the Activity does real work;
  keeping it as a pure orchestration test (fake activity, no real I/O) is the correct long-term
  shape, matching `test_generation_workflow.py`'s pattern.
- **Discovery worker gets its own DB engine** (`discovery_worker/db.py`, mirroring `api/db.py`) —
  `apps/workers/discovery` is a separate deployable from `apps/api` and can't import `api.db`
  directly; both read the same `DATABASE_URL` convention independently.
- **Login-form heuristic (Task 3) is a genuine, acknowledged gap, same class as the traversal
  algorithm**: `establish_session` navigates to the Application's base URL, and if a
  `input[type=password]` exists, fills the nearest email/text/name-matching input as username and
  submits — a sound, non-binding default per the Dev Notes, not a spec to match exactly.
- **SSO/session-reuse path**: the resolved secret (Story 1.4's placeholder) is parsed directly as a
  Playwright `storageState` JSON blob and passed to `browser.new_context(storage_state=...)` — no
  login step at all for that path, consistent with FR-3's "never logs in on the customer's behalf."
- **`MAX_ITERATIONS = 30`** in `crawler.py` is explicitly Story 2.2's placeholder stopping cap
  (commented as such in the module docstring) — Story 2.3 replaces it with the real
  exhaustive-traversal rule; not treated as the real FR-7 implementation.
- **Live-feed endpoint**: `GET /discovery-runs/{external_id}/evidence`, Organization-scoped via a
  join through `Application` (same pattern as `GET /applications/{id}`), returns the 50 most
  recent `Evidence` rows newest-first. No WebSocket/SSE — client-side polling
  (`EvidenceLiveFeed.tsx`, 1.5s interval, stops once `discoveryStatus !== "running"`) per the
  task's own "boring technology" default. Rendered in `var(--font-mono)`, per the standing
  mono-only-for-raw-evidence rule.
- **Playwright dependency was never actually added to `apps/workers/discovery`'s `pyproject.toml`
  in Story 1.1/2.1** despite being architecture-pinned and mentioned in `DEVELOPER_GUIDE.md` — this
  story adds it (`playwright>=1.57`), along with `minio`, `sqlmodel`, `psycopg[binary]`, `domain`,
  and `secrets-client` (all newly-real dependencies for real Activity behavior, not scope creep).
  Chromium's browser binary was already cached in this environment; `litellm`/`ai-provider` were
  also added in anticipation of Story 2.5 since `discovery-worker`'s own description already named
  `InferenceActivity` as living here.
- **Verification target**: a purpose-built local FastAPI test-target app
  (`apps/workers/discovery/tests/fixtures/target_app.py`) — session-cookie auth, a couple of linked
  pages, one form, one `fetch`-triggered API call, and a deterministic request-counted
  session-expiry trigger (unused until Story 2.4). Not shipped product code.
- **Verification gap — no browser tool available in this environment**: the live-feed's visual
  polling/append behavior was verified via `vitest`/DOM assertions and a real headless-Chromium
  crawl against the real API+DB+object-store, not by watching the Discovery Progress screen render
  live in an actual browser tab.
- Per the operator's instruction for this session, **no git commits were created**.

### File List

- `docker-compose.yml` — added the `minio` service (new local-dev dependency).
- `packages/domain/src/domain/evidence.py` — new: `Evidence` entity.
- `packages/domain/src/domain/__init__.py` — export `Evidence`, `EvidenceType`.
- `migrations/versions/6c1645fa421a_add_evidence_entity.py` — new migration (`evidence` table,
  `journey_id` with no FK yet).
- `packages/workflows/src/workflows/discovery_workflow.py` — `DiscoveryActivityInput`/
  `DiscoveryWorkflow.run` extended with `discovery_run_id`; timeout increased to 5 minutes for a
  real bounded crawl.
- `apps/api/src/api/discovery.py` — updated `start_discovery_run`'s workflow-start call for the
  new 3-arg signature.
- `apps/api/src/api/main.py` — new `GET /discovery-runs/{external_id}/evidence` endpoint +
  `EvidenceRead` model.
- `apps/api/tests/test_discovery_progress.py` — new: evidence-feed ordering + org-isolation tests.
- `apps/workers/discovery/pyproject.toml` — added `playwright`, `minio`, `sqlmodel`,
  `psycopg[binary]`, `domain`, `secrets-client`, `ai-provider` (main deps); `fastapi`, `uvicorn`,
  `python-multipart`, `pytest`, `pytest-asyncio` (dev/test-fixture deps).
- `packages/ai_provider/pyproject.toml` — added `litellm` (pinned `<1.90` — later versions ship a
  Rust extension that doesn't yet build against this project's Python 3.14.6).
- `apps/workers/discovery/src/discovery_worker/db.py` — new: this worker's own DB engine wiring.
- `apps/workers/discovery/src/discovery_worker/object_store.py` — new: MinIO-backed
  `ObjectStore`.
- `apps/workers/discovery/src/discovery_worker/session.py` — new: `establish_session` (standard
  login heuristic + SSO storage-state reuse).
- `apps/workers/discovery/src/discovery_worker/crawler.py` — new: the real BFS crawl loop.
- `apps/workers/discovery/src/discovery_worker/activities.py` — real `discovery_activity`
  (replaces Story 2.1's stub).
- `apps/workers/discovery/tests/conftest.py` — new: spins up the local test-target app on a real
  socket for Playwright.
- `apps/workers/discovery/tests/fixtures/target_app.py` — new: the local test-target app (test
  fixture, not shipped).
- `apps/workers/discovery/tests/test_crawler.py` — new: crawl-loop test against the live target.
- `apps/workers/discovery/tests/test_discovery_activity_integration.py` — new: the full Activity
  against real Postgres/Vault/MinIO.
- `apps/workers/discovery/tests/test_discovery_workflow.py` — rewritten to use a fake Activity
  (Story 2.1's stub-based assertion no longer holds).
- `apps/web/src/api.ts` — added `EvidenceRead` type + `listEvidence`.
- `apps/web/src/api-types.gen.ts` — regenerated (AD-6).
- `apps/web/src/components/EvidenceLiveFeed.tsx` — new: the polling live-feed component.
- `apps/web/src/components/EvidenceLiveFeed.test.tsx` — new.
- `apps/web/src/components/DiscoverJourneysPlaceholder.tsx` — wires in `EvidenceLiveFeed`; takes
  `discoveryRunId`.
- `apps/web/src/components/DiscoverJourneysPlaceholder.test.tsx` — updated for the new prop +
  stubbed fetch.
- `apps/web/src/App.tsx` — passes `discoveryRunId` down.
- `apps/web/src/App.test.tsx` — breadcrumb test's mocked response already included
  `discovery_run_id`.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status tracking only.

## Change Log

- 2026-07-17 — Implemented all 5 tasks (AC 1–3): `Evidence` entity, MinIO-backed object storage,
  the real Playwright crawl loop (session establishment, BFS traversal, form/action/API-call
  capture), and the Discovery Progress live-feed. Verified against a real local target app through
  the actual Postgres/Vault/MinIO/Temporal stack, not just mocks. Status moved to `review`.
