---
baseline_commit: 48b6499e08423320a0156e02720f1e8e2ba7d66c
---

# Story 2.2: Autonomous Exploration Captures the Application Model

*Renamed 2026-07-18, was "...Captures Evidence" — the generic `Evidence` table is removed in full, not merely renamed; this story now writes typed rows directly. See `sprint-change-proposal-2026-07-18.md`.*

Status: review <!-- reworked and re-verified 2026-07-18 (this session) against the typed-capture design — see Change Log -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

*Updated 2026-07-15 — no configurable scope; Discovery always explores the entire Application (FR-4 removed). Rewritten 2026-07-18 — reworked to (a) add crawl-optimization ACs (page-fingerprint dedup, navigation-first, representative-action sampling), then (b), same day, to remove the generic `Evidence` capture record entirely — `DiscoveryActivity` now writes directly into typed tables (`Page`/`Form`/`FormField`/`ValidationRule`/`Action`/`ApiEndpoint`/`PageTransition`). The original implementation below (Change Log 2026-07-17) predates both rounds of this rework and was built entirely against the now-removed `Evidence` design.*

As a user,
I want the platform to autonomously explore my entire Application,
so that a structured record of it is captured as the basis for journey mapping.

## Acceptance Criteria

1. **`[REWRITTEN 2026-07-18]` Given** a running Discovery Run, **when** `DiscoveryActivity` navigates pages, exercises UI actions and forms, and invokes APIs across the entire Application, **then** each observation is written directly as a typed row: a page visit as `Page`, a form submission as `Form` (+ `FormField`/`ValidationRule`), a UI action as `Action`, an API call as `ApiEndpoint`, a navigation as `PageTransition` — every row tagged with both `application_id` and `discovery_run_id`, and (where the column exists) `merged_into_id = null`. There is no intermediate generic capture record. [Source: epics.md#Story 2.2; FR-6, FR-30; architecture#AD-8, #AD-14]
2. Large binary artifacts (screenshots) are referenced via `Page.object_storage_key` (an object-storage key), never stored inline in Postgres. [Source: architecture#AD-8]
3. The Discovery Progress screen's live-feed list shows the most recently captured pages/actions/API calls, newest first, in monospace, appended as discovery proceeds. [Source: epics.md#Story 2.2; DESIGN.md#Typography — mono-inline]
4. **`[ADDED 2026-07-18]`** **Given** the same logical page is reachable via more than one navigation path, **when** the crawler computes a page fingerprint, **then** that page is explored and captured once, not once per path (page-fingerprint deduplication) — a crawl-time optimization, distinct from Story 2.5's cross-run `merged_into_id` resolution. [Source: epics.md#Story 2.2; FR-6; architecture#AD-15]
5. **`[ADDED 2026-07-18]`** **Given** a page exposes both unexplored navigation links and already-explored interaction targets, **when** the crawler chooses what to do next, **then** it prioritizes unexplored navigation paths before repeating interactions on an already-visited page (navigation-first). [Source: epics.md#Story 2.2; FR-6; architecture#AD-15]
6. **`[ADDED 2026-07-18]`** **Given** a page contains a repeated identical action pattern (e.g., an "Edit" button repeated once per grid row), **when** the crawler encounters it, **then** it exercises one representative instance of that pattern, not every individual instance (representative-action sampling) — consistent with FR-7/AD-15's clarification that "exhaustive" applies at the level of distinct pages/action patterns. **`[UPDATED 2026-07-19]`** Sampling is additionally bounded to a small number (`_MAX_ACTIONS_PER_PAGE`) of distinct action *labels* per page, page-body content tried before nav/header/footer chrome, so a shared site-wide button doesn't crowd out a page-specific call-to-action. [Source: epics.md#Story 2.2; FR-7; architecture#AD-15]
7. **`[ADDED 2026-07-19]`** **Given** a page is reachable only via a non-link action (e.g. a client-side "Add to Cart" button, not a plain `<a href>`), **when** that action navigates to a same-origin destination, **then** the destination is enqueued for further crawling like any other discovered page, and the navigation is recorded as a `PageTransition` — previously such a destination was captured as an `Action`/`Transition` but never explored past the click, a structural blind spot this closes. [Source: FR-6; architecture#AD-15]
8. **`[ADDED 2026-07-19]`** **Given** a `Form` with an identical shape and starting field values (hidden fields included) is reachable identically from more than one page, **when** the crawler encounters it again, **then** it is captured once, not once per page it appears on (representative-form sampling, mirrors AC 6 for forms). Any observable difference — including a hidden field's value — means the forms are genuinely distinct and both get captured. [Source: FR-6; architecture#AD-15]
9. **`[ADDED 2026-07-19]`** **Given** a destination fails to load (network/DNS error) or responds with a 4xx/5xx status, **when** the crawler reaches it, **then** it is marked visited and skipped — no `Page` row is written and it is never explored further, since it isn't a real business page to build a Journey/Scenario against. [Source: FR-6, FR-7; architecture#AD-15]

## Tasks / Subtasks

- [x] Task 1: Add the raw-capture domain entities (AC: 1, 2) `[REWRITTEN 2026-07-18 — replaces the old Evidence entity task]`
  - [x] Add `Page` (`application_id` FK, `discovery_run_id` FK — immutable once set, `merged_into_id` nullable self-FK [null = canonical], `journey_id` nullable, `url`, `title`, `object_storage_key` nullable, `created_at`) to `packages/domain`, following the UUIDv7/UUIDv4 id convention from Story 1.3
  - [x] Add `Form` (`application_id`, `discovery_run_id`, `page_id` FK, `merged_into_id` nullable self-FK, `journey_id` nullable, `action_url`, `method`, `created_at`) + `FormField` (`form_id` FK, `name`, `input_type`, `required`, `default_value` nullable, `captured_selector` nullable str — see Dev Notes; `component_id` nullable FK, added by Story 2.5 once it derives this field's `Component`) + `ValidationRule` (`form_field_id` FK, `rule_type`, `value` nullable)
  - [x] Add `Action` (`application_id`, `discovery_run_id`, `page_id` FK, `description`, `representative` [bool — set `true` for the one instance AC 6 samples], `created_at`) — no `merged_into_id`; raw Action rows are historical capture detail, never merged into each other (Story 2.5's `Component` is the deduped/canonical unit built *from* grouped Actions)
  - [x] Add `ApiEndpoint` (`application_id`, `discovery_run_id`, `page_id` FK, `merged_into_id` nullable self-FK, `journey_id` nullable, `method`, `path`, `created_at`)
  - [x] Add `PageTransition` (`application_id`, `discovery_run_id`, `from_page_id` FK, `to_page_id` FK, `triggered_by_action_id` nullable FK, `created_at`) — no `merged_into_id` needed; Story 2.5 resolves duplicate edges once from/to are canonical
  - [x] **`journey_id` (on `Page`/`Form`/`ApiEndpoint`) must stay null from this story.** Per AD-8, `InferenceActivity` (Story 2.6) — not `DiscoveryActivity` — is the sole writer of `journey_id`, and only onto canonical (`merged_into_id IS NULL`) rows. Do not set it here even provisionally
  - [x] One Alembic migration for all entities in this task
- [x] Task 2: Add a thin object-storage abstraction for screenshots (AC: 2)
  - [x] Architecture fixes the *shape* (structured columns in Postgres, binaries referenced by object-storage key, never inline — AD-8) but explicitly defers the specific backend provider, and — unlike `AIProvider`/`DeliveryAdapter`/`SecretsClient` — does not name a formal Protocol port for this in the Module Contracts section. Build a small internal abstraction anyway (e.g. `put(key, bytes) -> None` / `get(key) -> bytes`), consistent with the rest of the system's ports-and-adapters discipline, so the backend stays swappable when the deferred deployment-topology decision lands
  - [x] Recommended default adapter: **MinIO** (S3-compatible, self-hostable, trivial for local/CI, and swappable later for real S3/GCS/Azure Blob without changing the abstraction's shape since they all speak roughly the same object-key model) — a cloud-provider bucket is an equally valid alternative if preferred; document whichever is chosen in Completion Notes
  - [x] Screenshots are written through this abstraction; `Page.object_storage_key` stores only the returned key, never the binary itself
- [x] Task 3: Build the real autonomous exploration loop in `DiscoveryActivity` (AC: 1, 2, 4-9) `[REWRITTEN 2026-07-18]` `[EXTENDED 2026-07-19]`
  - [x] Establish a session using the Application's stored credentials (via `SecretsClient`, from Stories 1.3/1.4), then navigate every page reachable across the entire Application (`[UPDATED 2026-07-15]` no scope restriction — FR-4 removed), exercise UI actions/forms with generic/synthetic input data, and capture invoked API calls via Playwright's request/response interception
  - [x] Neither the PRD nor the Architecture Spine specifies an exact traversal algorithm — FR-6's description is "navigates the Application the way a thorough tester would." Treat the following as a sound, non-binding default rather than a spec to match exactly: breadth-first link/navigation-graph traversal; generic placeholder values keyed by input field type/name for form-filling; `page.on("request")`/`page.on("response")` (or the current Playwright-Python equivalent) to capture API calls
  - [x] For each page visit, write a `Page` row directly (not a generic record); for each form submission, `Form`+`FormField`(+`ValidationRule`); for each UI action, `Action`; for each API call, `ApiEndpoint`; for each detected navigation, `PageTransition`. Route any screenshot through Task 2's object store and store only the key on `Page.object_storage_key`
  - [x] **When filling each field (not just on submit), capture its selector onto `FormField.captured_selector`** — whatever's reasonably available (label association, `data-testid`, `name`/`id`, or a CSS path fallback). This is easy to skip since only the final submission strictly needs to succeed for `Form`/`FormField` rows to get written — but skipping it leaves Story 2.5 with no way to derive a usable locator for that field at all
  - [x] **Page-fingerprint dedup (AC 4):** compute a fingerprint for the current page (e.g. normalized URL) before crawling it; if already visited *within this run*, skip re-crawling it — a crawl-time, in-memory optimization, distinct from Story 2.5's cross-run canonical-merge resolution (which additionally recognizes the same *logical* page across different literal URLs and across different Discovery Runs)
  - [x] **Navigation-first (AC 5):** when choosing what to explore next, prefer an unvisited navigation target over repeating an interaction already exercised on the current page
  - [x] **Representative-action sampling (AC 6):** when a page contains multiple instances of what is recognizably the same action pattern (e.g. a repeated "Edit" button, one per grid row), exercise only one instance and mark its `Action.representative = true`; do not write an `Action` row (or repeat the interaction) for the other instances. `[EXTENDED 2026-07-19]` Cap the number of distinct action labels exercised per page to a small constant; try page-body content before nav/header/footer chrome so a shared button doesn't crowd out a page-specific one
  - [x] **`[ADDED 2026-07-19]`** **Button-triggered navigation continuation (AC 7):** when a clicked action navigates to a new same-origin URL, enqueue that URL for further crawling (not just capture the click) and record the edge as a `PageTransition`
  - [x] **`[ADDED 2026-07-19]`** **Representative-form sampling (AC 8):** before filling a form, compute a signature from its action/method/shape and every field's starting name+value (hidden fields included); skip re-capturing a form whose signature was already seen this run
  - [x] **`[ADDED 2026-07-19]`** **Broken/error-destination handling (AC 9):** a navigation that raises (network/DNS error) or resolves to a 4xx/5xx response is marked visited and skipped — no `Page` row, no further exploration from it
  - [x] **Do not implement FR-7's stop-condition logic here** (exhaustive-traversal detection) — that is Story 2.3's job, and it is also what actually sets `DiscoveryRun.status` to `complete`. `[UPDATED 2026-07-15]` There is no time-budget cutoff to implement — FR-5 is removed, and exhaustive traversal is the only stop condition (accepted risk, PRD §12 item 7: no safety cap against unbounded exploration). This story only needs the capture loop to be boundable for testing purposes — use a simple, clearly-marked placeholder (e.g. a max-iteration safety cap, test-only, not a product feature) rather than building real stop-condition detection prematurely; Story 2.3 replaces this placeholder with the real rule
- [x] Task 4: Build the Discovery Progress live-feed list (AC: 3)
  - [x] Show the most recently captured pages/actions/API calls, newest first, rendered in `{typography.mono-inline}` (raw capture only — never authored UI copy, per the standing typography rule), appended as discovery proceeds. Union across `Page`/`Action`/`ApiEndpoint` ordered by `created_at`, not a single table's feed
  - [x] No push channel is architecturally required — client-side polling of a simple "recent captures for this run" read endpoint is a reasonable default, consistent with the "boring technology" bias elsewhere in the architecture. A WebSocket/SSE push channel is a valid alternative but not required by any AC
- [x] Task 5: Verify end-to-end and record evidence (AC: 1-9)
  - [x] Running a Discovery Run against a locally-hosted test target produces `Page`/`Form`/`Action`/`ApiEndpoint`/`PageTransition` rows, all tagged with the correct `application_id`/`discovery_run_id`, `merged_into_id=null` (where applicable), and `journey_id=null`
  - [x] A captured screenshot exists in the object store under the key referenced by its `Page.object_storage_key`, not inline in Postgres
  - [x] Visiting the same URL twice within one run produces exactly one `Page` row (AC 4); a repeated identical action pattern produces exactly one `Action` row with `representative=true` (AC 6)
  - [x] Discovery Progress's live-feed list updates with newest-first entries in monospace as a run proceeds
  - [x] **`[ADDED 2026-07-19]`** A button-triggered navigation's destination gets its own `Page` row and is explored further (AC 7); an identically-shaped form reachable from two pages produces one `Form` row, not two (AC 8); a broken/4xx-5xx destination produces no `Page` row (AC 9)

## Dev Notes

- **`[REWRITTEN 2026-07-18]` There is no generic `Evidence` table — this is a deliberate removal, not a naming change.** The prior design (a flat `type` + JSONB `details` record) duplicated what these typed tables already hold and added an indirection layer with no benefit. Every observation is written directly to its typed table.
- **`journey_id`/`merged_into_id` attribution split is the single most important rule in this story**: this story writes `Page`/`Form`/`ApiEndpoint` with `merged_into_id=null` and `journey_id=null` always — it never resolves duplicates (Story 2.5's job) and never attributes a Journey (Story 2.6's job). `Action`/`PageTransition` never get either field. Getting this backwards — e.g. having `DiscoveryActivity` guess at a `journey_id` or decide two pages are duplicates itself — would break AD-14's single-writer-per-responsibility rule and the "which capture supports *this* Journey" traceability the whole review-trust mechanic depends on.
- **The traversal algorithm is a genuine, acknowledged gap in the planning artifacts**, not an oversight on this story's part — FR-6 describes the desired outcome ("the way a thorough tester would") without prescribing a mechanism. The default given in Task 3 is a starting point; if pilot feedback later shows it's insufficient for real applications, that's a product/algorithm iteration, not a sign this story was implemented wrong.
- **Object storage has no named architectural port**, unlike the other three port packages — this is a deliberate observation, not an inconsistency to "fix" by inventing a `packages/object_store` structural-seed entry that doesn't exist in Story 1.1's fixed directory tree. Build the abstraction inside `apps/workers/discovery` (or wherever `DiscoveryActivity` lives) rather than adding a new top-level package.
- **Task boundary with Story 2.3, restated for clarity:** this story makes the capture loop *boundable* (test-only placeholder); Story 2.3 makes it *correct* (real exhaustive-traversal detection, and the actual `DiscoveryRun.status` transition). Don't let this story's placeholder stopping point leak into being treated as the real FR-7 implementation during code review. `[UPDATED 2026-07-15]` No time-budget detection to build anywhere — FR-5 removed.
- **`[ADDED 2026-07-19]` A form's quantity-like field (name/id matching `qty`/`quantity`/`count`/`amount`/`number`) is filled with `"1"` rather than the generic `_GENERIC_VALUES` string.** A field's declared `type` alone isn't reliable — a quantity box is routinely `type="text"` on real sites, and a generic string there breaks the flow (e.g. a 500 on "Add to Cart") instead of landing on a real page. This is a data-quality fix to the existing generic-value-filling behavior (Task 3), not a new AC — it doesn't change what gets captured, only whether the interaction succeeds.
- **Locator capture is new scope for this rework, needed by Story 2.5 — for both actions AND form fields**: to let Story 2.5 synthesize `ComponentLocator` rows with real fidelity, capture whatever selector information is reasonably available at two separate moments, not just one: (a) when an `Action` (button/link) is exercised — the element's accessible role/name, a `data-testid` if present, or a CSS path as a fallback; and (b) **when a `FormField` is filled** — the same kind of selector info for the input itself (e.g. its `<label>` association, `data-testid`, `name`/`id` attribute, or CSS path). It's easy to only do (a), since clicking is the more visible interaction — but a form field with no captured selector info leaves Story 2.5 unable to derive a usable locator for it at all (not just a lower-fidelity one). Store the captured selector on the respective `Action`/`FormField` row (simple string field(s), or reuse `Action.description` for actions if that's sufficient — a judgment call, not a prescribed schema).

### Project Structure Notes

- Adds `Page`, `Form`, `FormField`, `ValidationRule`, `Action`, `ApiEndpoint`, `PageTransition` to `packages/domain`, an object-storage abstraction inside `apps/workers/discovery`, and replaces Story 2.1's `DiscoveryActivity` stub with real behavior. No new top-level directories beyond Story 1.1's Structural Seed.
- **Depends on Stories 1.1–1.4 and 2.1 being actually implemented**, not just created. This story specifically needs Story 2.1's `DiscoveryRun`/`DiscoveryWorkflow`/stub `DiscoveryActivity`, and Stories 1.3/1.4's `SecretsClient`-stored Application credentials. `[UPDATED 2026-07-15]` Story 1.5 no longer exists.
- **This is the second rework of an already-implemented story** (see Change Log) — the 2026-07-17 build's domain model (`Evidence`), migration, and most of `activities.py`/`crawler.py` will need real, substantial code changes, not incremental additions. Expect to touch nearly every file in the original File List below.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.2: Autonomous Exploration Captures the Application Model]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md §4.2 — FR-6, FR-7, FR-30]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8 — typed capture, canonical/merge model; #AD-14 — single-writer rule; #Deferred — object-storage backend provider]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Typography — mono-inline]
- [Source: _bmad-output/implementation-artifacts/2-1-start-a-discovery-run.md — `DiscoveryActivity` stub this story replaces with real behavior]
- [Source: _bmad-output/implementation-artifacts/2-5-application-model-builder.md — the sibling story that merges/derives from what this story captures]

## Previous Story Intelligence

Story 2.1 remains `ready-for-dev`, so there is no implemented stub `DiscoveryActivity` yet to build on top of — check its File List once implemented for the exact stub signature/dispatch shape before starting Task 3. Stories 1.1–1.4 are also all still `ready-for-dev`; this story specifically needs 1.3/1.4's `SecretsClient`-backed Application credentials to be resolvable. Story 1.5 no longer exists (removed 2026-07-15).

## Latest Technical Notes

- Playwright Python 1.57+ is architecture-pinned (Story 1.1) — verify the current request/response interception API surface against whatever exact version is installed at implementation time, since Playwright's API has moved across versions.
- MinIO (if chosen for Task 2) — use its current-stable client library and server image; verify at implementation time rather than assuming a version.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

**`[HISTORICAL — superseded 2026-07-18]`** Everything below this line describes the 2026-07-17 implementation, built entirely against the now-removed `Evidence` design. It is retained as history, not as a description of the current target — see Tasks/Dev Notes above for what this story now actually requires. Expect the rework to touch nearly every file listed below.

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
  the `journey` table doesn't exist until Story 2.6. The column is added now as a plain, nullable,
  indexed `UUID` with no `ForeignKey(...)` reference; Story 2.6 adds the FK (both the Python
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
  also added in anticipation of Story 2.6 since `discovery-worker`'s own description already named
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
- 2026-07-18 — Sprint Change Proposal (Application Model Builder): status reverted `review` →
  `in-progress`; ACs 4-6 added (page-fingerprint dedup, navigation-first, representative-action
  sampling). Rework against these new ACs not yet implemented — the Dev Agent Record/File
  List/Completion Notes above describe the 2026-07-17 implementation only, predating this change.
  See `sprint-change-proposal-2026-07-18.md`.
- 2026-07-18 [second pass, same day] — the generic `Evidence` table concept removed in full (not
  merely deferred): rewrote Tasks 1/3/4/5 and Dev Notes so `DiscoveryActivity` writes directly into
  seven typed tables (`Page`/`Form`/`FormField`/`ValidationRule`/`Action`/`ApiEndpoint`/
  `PageTransition`) instead of one generic `Evidence` record, each scoped by `application_id`
  (making the model reusable across re-discovery, not just per-run) plus `discovery_run_id`
  (provenance). Story renamed from "...Captures Evidence" to "...Captures the Application Model".
  Tasks reset to unchecked — the 2026-07-17 implementation was built entirely against the removed
  design and needs real rework, not incremental patching. See `sprint-change-proposal-2026-07-18.md`.
- 2026-07-18 [this session] — Implemented the full rework: `Page`/`Form`/`FormField`/
  `ValidationRule`/`Action`/`ApiEndpoint`/`PageTransition` domain entities (`packages/domain`),
  migration `d1e9a4b6f2c3` (drops `evidence`, adds the typed tables), rewrote `crawler.py` to emit
  typed captures with page-fingerprint dedup (AC 4), navigation-first traversal (AC 5, satisfied by
  construction — a page's interactions run exactly once, at first visit), representative-action
  sampling by grouping standalone buttons by label (AC 6), and selector capture on both actions and
  form fields. Rewrote `discovery_activity` in `activities.py` to persist each typed capture
  directly (no `Evidence` row). Verified via `uv run pytest` against real Postgres/Vault/MinIO/a
  local target app (extended with a repeated "Edit" button grid to exercise AC 6): all typed rows
  written correctly, dedup/sampling ACs pass. `ruff`/`pyright` clean. Status moved to `review`.
- 2026-07-19 — Crawl-engine follow-up (ACs 7-9 added): `crawler.py` now (a) enqueues and further
  explores same-origin destinations reached only via a button click, closing a prior blind spot
  where such a flow was captured but never traversed past the first click; (b) dedupes forms with
  an identical action/method/shape and starting field values (hidden fields included) across pages
  — needed since a hidden field can be the only thing distinguishing two otherwise-identical forms
  (e.g. a per-product "Add to Cart"), so hidden fields are now included when filling/capturing;
  (c) skips destinations that error (network/DNS failure) or respond 4xx/5xx, marking them visited
  without writing a `Page` row; (d) bounds representative-action sampling to
  `_MAX_ACTIONS_PER_PAGE` distinct labels per page, page-body content before nav/header/footer
  chrome; and (e) records a `PageTransition` for ordinary link-followed BFS navigation, not only
  click/submit-triggered navigation, so Story 2.5's navigation graph isn't built almost entirely
  from the minority of interaction-triggered edges. Also fills quantity-like fields with `"1"`
  instead of a generic string (data-quality fix, no new AC). PRD FR-6/FR-7/§12 item 7, Architecture
  AD-15, and this story's ACs/Tasks/Dev Notes updated to match.
