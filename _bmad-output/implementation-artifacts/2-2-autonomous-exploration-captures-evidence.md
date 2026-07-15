# Story 2.2: Autonomous Exploration Captures Evidence

Status: ready-for-dev

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

- [ ] Task 1: Add the `Evidence` domain entity (AC: 1, 2)
  - [ ] Add `Evidence` (`discovery_run_id` FK — immutable once set, `type` [`page` | `action` | `form` | `api_call` | `state_transition`], structured metadata, `object_storage_key` nullable, `journey_id` nullable, `captured_at`) to `packages/domain`, following the UUIDv7/UUIDv4 id convention from Story 1.3
  - [ ] **`journey_id` must stay null from this story.** Per AD-8, `InferenceActivity` (Story 2.5) — not `DiscoveryActivity` — is the sole writer of `Evidence.journey_id`. Do not set it here even provisionally; a captured row with no Journey yet is the correct, expected state until Story 2.5 runs
  - [ ] Alembic migration
- [ ] Task 2: Add a thin object-storage abstraction for binary evidence (AC: 2)
  - [ ] Architecture fixes the *shape* (structured metadata in Postgres, binaries referenced by object-storage key, never inline — AD-8) but explicitly defers the specific backend provider, and — unlike `AIProvider`/`DeliveryAdapter`/`SecretsClient` — does not name a formal Protocol port for this in the Module Contracts section. Build a small internal abstraction anyway (e.g. `put(key, bytes) -> None` / `get(key) -> bytes`), consistent with the rest of the system's ports-and-adapters discipline, so the backend stays swappable when the deferred deployment-topology decision lands
  - [ ] Recommended default adapter: **MinIO** (S3-compatible, self-hostable, trivial for local/CI, and swappable later for real S3/GCS/Azure Blob without changing the abstraction's shape since they all speak roughly the same object-key model) — a cloud-provider bucket is an equally valid alternative if preferred; document whichever is chosen in Completion Notes
  - [ ] Screenshots and full DOM snapshots are written through this abstraction; the `Evidence.object_storage_key` column stores only the returned key, never the binary itself
- [ ] Task 3: Build the real autonomous exploration loop in `DiscoveryActivity` (AC: 1, 2)
  - [ ] Replace Story 2.1's stub with real behavior: establish a session using the Application's stored credentials (via `SecretsClient`, from Stories 1.3/1.4), then navigate every page reachable across the entire Application (`[UPDATED 2026-07-15]` no scope restriction — FR-4 removed), exercise UI actions/forms with generic/synthetic input data, and capture invoked API calls via Playwright's request/response interception
  - [ ] Neither the PRD nor the Architecture Spine specifies an exact traversal algorithm — FR-6's description is "navigates the Application the way a thorough tester would." Treat the following as a sound, non-binding default rather than a spec to match exactly: breadth-first link/navigation-graph traversal; generic placeholder values keyed by input field type/name for form-filling; `page.on("request")`/`page.on("response")` (or the current Playwright-Python equivalent) to capture API calls
  - [ ] For each captured page visit, UI action, form submission, API call, and detected state transition, write an `Evidence` row tagged with `discovery_run_id`; route any screenshot/DOM snapshot through Task 2's object store and store only the key
  - [ ] **Do not implement FR-7's stop-condition logic here** (exhaustive-traversal detection) — that is Story 2.3's job, and it is also what actually sets `DiscoveryRun.status` to `complete`. `[UPDATED 2026-07-15]` There is no time-budget cutoff to implement — FR-5 is removed, and exhaustive traversal is the only stop condition (accepted risk, PRD §12 item 7: no safety cap against unbounded exploration). This story only needs the capture loop to be boundable for testing purposes — use a simple, clearly-marked placeholder (e.g. a max-iteration safety cap, test-only, not a product feature) rather than building real stop-condition detection prematurely; Story 2.3 replaces this placeholder with the real rule
- [ ] Task 4: Build the Discovery Progress live-feed list (AC: 3)
  - [ ] Show the most recently captured pages/actions/API calls, newest first, rendered in `{typography.mono-inline}` (raw evidence only — never authored UI copy, per the standing typography rule), appended as discovery proceeds
  - [ ] No push channel is architecturally required — client-side polling of a simple "recent Evidence for this run" read endpoint is a reasonable default, consistent with the "boring technology" bias elsewhere in the architecture. A WebSocket/SSE push channel is a valid alternative but not required by any AC. (Note: the review-queue pending-count badge this reasoning was originally cross-referenced against is cut as of 2026-07-15 — see Story 3.1 — this story's live-feed polling is unaffected either way)
- [ ] Task 5: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] Running a Discovery Run against a locally-hosted test target produces `Evidence` rows of each type (`page`, `action`, `form`, `api_call`, `state_transition`), all tagged with the correct `discovery_run_id` and `journey_id=null`
  - [ ] A captured screenshot/DOM snapshot exists in the object store under the key referenced by its `Evidence` row, not inline in Postgres
  - [ ] Discovery Progress's live-feed list updates with newest-first entries in monospace as a run proceeds

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

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
