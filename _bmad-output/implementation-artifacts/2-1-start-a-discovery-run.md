---
baseline_commit: 48b6499e08423320a0156e02720f1e8e2ba7d66c
---

# Story 2.1: Start a Discovery Run

Status: done <!-- verified live end-to-end 2026-07-20: real Discovery Runs started from the UI, crawled, and completed successfully -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want a Discovery Run to start as soon as I've onboarded an Application,
so that the platform begins mapping its business journeys without an extra step.

## Acceptance Criteria

*`[UPDATED 2026-07-15 — twice]` First: trigger point moved from a hypothetical "Applications screen" action to the Connect App submission (no Applications list/table is confirmed to exist in the current IA). Second, this round: Story 1.5 (which used to own the Connect App form's finishing step and the `Application.status="ready"` gate) is removed in full — Story 1.3's single atomic submission now creates the `Application` **and** starts the `DiscoveryRun` in the same request. There is no separate "Start Discovery Run" endpoint, no draft/ready `Application` status, and no manual trigger of any kind.*

1. **Given** an Application was just created (Story 1.3's Connect App submission), **when** the creation request completes, **then** a `DiscoveryRun` record is created with `status=running`, and a bounded `DiscoveryWorkflow` is started for it (AD-1) — the workflow contains no direct I/O, only calls to Activities (AD-2). [Source: epics.md#Story 2.1; architecture#AD-1, #AD-2]
2. The Discovery Progress screen shows a status pill reading "Running" with a pulsing dot. [Source: epics.md#Story 2.1; DESIGN.md#Components — status-pill]

## Tasks / Subtasks

- [x] Task 1: Add the `DiscoveryRun` domain entity (AC: 1)
  - [x] Add `DiscoveryRun` (`application_id` FK, `status`, `started_at`) to `packages/domain`, following the UUIDv7-internal/UUIDv4-external id convention established in Story 1.3
  - [x] `status` is one of `running | complete | failed` per AD-10 (`[UPDATED 2026-07-15]` no `incomplete` value — FR-5/time-budget removed, so the only stop condition is exhaustive traversal) — this story only ever sets `running`; the other transitions belong to Stories 2.3 (`complete`) and 2.4 (`failed`), which will each add their own supporting columns (e.g. 2.4 adds `failure_reason`) — don't pre-build those columns speculatively here
  - [x] Organization scoping is transitive through `Application.organization_id` — reuse whatever central scoping mechanism Story 1.2 actually built (a query-layer filter or FastAPI dependency) rather than adding a redundant direct `organization_id` column here, unless Story 1.2's implementation specifically requires every scoped table to carry one; check its File List before deciding
  - [x] Alembic migration
- [x] Task 2: Build `DiscoveryWorkflow` — a new workflow, not a reuse of Story 1.1's shell (AC: 1)
  - [x] Add `DiscoveryWorkflow` to `packages/workflows`: bounded, orchestration-only (AD-2) — no network/DB/browser calls inside the workflow itself, only a call to a Discovery Activity
  - [x] **This must be a new, separate workflow definition.** Story 1.1's trivial no-op workflow was explicitly earmarked for `GenerationWorkflow`, graduated by Story 2.5's `InferenceActivity` (`[UPDATED 2026-07-15]` originally Story 3.2, now removed) — not this one. Reusing or renaming that shell for `DiscoveryWorkflow` would leave Epic 2/4 without the shell they're each depending on. Build `DiscoveryWorkflow` fresh, following the same orchestration-only pattern 1.1 demonstrated, but as its own definition
- [x] Task 3: Stub `DiscoveryActivity` — dispatched, not yet functional (AC: 1)
  - [x] Add a `DiscoveryActivity` to `apps/workers/discovery`, dispatched by `DiscoveryWorkflow`, accepting the `Application` (and its `secret_ref`) — for this story, it only needs to prove the dispatch path end-to-end (API → Temporal → worker → Activity); it does **not** need to perform any real Playwright navigation or capture any `Evidence` yet
  - [x] The actual autonomous crawling behavior (pages, actions, forms, API calls) is Story 2.2's job, exactly as Story 1.1 deliberately left its own workflow's Activity as a no-op proof rather than building real behavior ahead of its owning story. Don't reach into 2.2's scope here
- [x] Task 4: `[REWRITTEN 2026-07-15]` Build the `DiscoveryRun`-creation logic as a function Story 1.3's onboarding endpoint calls — not a separate endpoint (AC: 1)
  - [x] Previously specified as a standalone POST endpoint (e.g. `/applications/{id}/discovery-runs`), gated on `Application.status="ready"` (set by the now-removed Story 1.5). Both are gone: Story 1.3's Connect App submission is a single atomic creation with no draft/ready distinction, so there is no separate endpoint to call and no status precondition to check
  - [x] Implement the shared logic — create the `DiscoveryRun` row (`status=running`) and start `DiscoveryWorkflow` via the Temporal client wired in Story 1.1 — as a function/service Story 1.3's Task 3 calls directly in the same request that creates the `Application`, not as an independently user-triggered action
- [x] Task 5: Build the Discovery Progress screen (AC: 1, 2) — **`[UPDATED 2026-07-15]`**
  - [x] Story 1.3's Connect App submission directly starts the Discovery Run and navigates into the pipeline (its Task 3/4) — there is no separate "Applications screen" action or table row to build; that surface remains unconfirmed to exist at all in the current IA
  - [x] Build Discovery Progress: shows the status pill reading "Running" with a pulsing dot, using `DESIGN.md`'s documented `status-pill` component/tokens (this is the pill's first real, in-spec use). **`[GAP]`** whether Discovery Progress is a distinct screen/step in the current pipeline (between Connect App and Discover Journeys) or a transient loading state was not confirmed during UX review — build it as a distinct step for now, but re-verify against a fuller prototype export — **`[RESOLVED — see Completion Notes]`**
  - [x] Application-name breadcrumb *is* shown on Discovery Progress per UX-DR16 — this is the first Application-scoped screen built; get the breadcrumb-inclusion rule right here since every later Application-scoped screen (Discover Journeys, Review Scenarios, ...) follows the same rule
- [x] Task 6: Verify end-to-end and record evidence (AC: 1, 2)
  - [x] Creating an Application (Story 1.3) creates a `DiscoveryRun(status=running)` row and a running `DiscoveryWorkflow` in the same request, observable via Temporal CLI/Web UI — with no separate action taken
  - [x] Discovery Progress shows the "Running" status pill with a pulsing dot for the new run

## Dev Notes

- **Do not confuse this story's workflow with Story 1.1's.** This is the single most likely cross-story mistake here: both stories build "a workflow that doesn't do much yet," but they are two different workflows serving two different later epics (`DiscoveryWorkflow` here feeds Epic 2/3; the 1.1 shell feeds Epic 4's `GenerationWorkflow`, graduated by Story 2.5's `InferenceActivity` — `[UPDATED 2026-07-15]` not Story 3.2, which is removed). Verify Story 1.1's actual File List before starting Task 2 to make sure you're not accidentally repurposing its workflow file.
- **AD-1's bounded-workflow rule matters even though this story doesn't build the "termination" side of it yet** — `DiscoveryWorkflow` will eventually terminate by writing candidate Journeys/Capabilities (Story 2.5) after passing through the stop-condition logic (Story 2.3). This story only starts it; don't add human-review signal/update handling here (AD-1 explicitly forbids modeling review as a workflow signal at all, in any story).
- **AD-2 discipline applies to the stub Activity too** — even though `DiscoveryActivity` does nothing real yet, don't be tempted to put a placeholder DB write or HTTP call directly in `DiscoveryWorkflow` "just for now." Keep the I/O boundary correct from the start.
- **`[RESOLVED 2026-07-15]` No Application readiness precondition exists anymore.** An earlier draft gated run-start on `Application.status=ready`, inferred from Epic 1's stated closing goal — that inference is moot now: Story 1.5 (which owned the draft→ready transition) is removed, Story 1.3's Connect App submission is a single atomic creation, and there is no draft/ready distinction on `Application` at all.

### Project Structure Notes

- Adds `DiscoveryRun` to `packages/domain`, a new `DiscoveryWorkflow` to `packages/workflows`, a stub `DiscoveryActivity` to `apps/workers/discovery`, and the first build of the Discovery Progress screen in `apps/web`. `[UPDATED 2026-07-15]` No new endpoint — Story 1.3's onboarding endpoint calls this story's `DiscoveryRun`-creation logic directly. No new top-level directories — all within Story 1.1's Structural Seed.
- **Depends on Epic 1's remaining stories (1.1–1.4) being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. In particular, this story needs Story 1.1's Temporal wiring and Story 1.2's Organization-scoping middleware to exist. `[UPDATED 2026-07-15]` Story 1.5 no longer exists — this story's `DiscoveryRun`-creation logic is called from Story 1.3 directly.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1: Start a Discovery Run]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-2, #AD-10]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — status-pill]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Information Architecture — Discovery Progress screen, breadcrumb rule]
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-13.md — confirms Story 1.1's workflow shell is earmarked for `GenerationWorkflow`, not this story (report predates the 2026-07-15 removal of Story 3.2; the shell's eventual owner is now Story 2.5)]
- [Source: _bmad-output/implementation-artifacts/1-1-repository-service-scaffold.md — Temporal wiring and the no-op workflow this story must NOT reuse]
- [Source: _bmad-output/implementation-artifacts/1-3-onboard-an-application-basic-details.md — the onboarding endpoint that now calls this story's `DiscoveryRun`-creation logic directly, absorbed from removed Story 1.5]

## Previous Story Intelligence

Epic 1's Stories 1.1–1.4 remain `ready-for-dev` (not `done`); `git log` shows only the initial BMad-tooling commit. The one non-obvious carry-forward, beyond the usual "verify it's actually built first": Story 1.1's Dev Agent Record File List should be checked specifically to confirm which file/module holds its no-op workflow, so Task 2 here can be certain it's building something new rather than colliding with it. `[UPDATED 2026-07-15]` Story 1.5 no longer exists — don't look for it.

## Latest Technical Notes

No new library decisions — this story uses the Temporal Python SDK and FastAPI/SQLModel stack already established in Story 1.1.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run pytest apps/workers/discovery/tests/test_discovery_workflow.py -q` (Temporal
  time-skipping in-memory environment, no external server) → **1 passed**, confirming
  `DiscoveryWorkflow` dispatches to `DiscoveryActivity` and returns its result.
- `uv run pytest apps/ packages/ -q` against a throwaway `postgres:18.4` container
  (`localhost:15432` — the compose-managed `aitestgen-postgres-1` still can't bind host port
  5432, occupied by an unrelated container on this machine, same issue noted in Story 1.4's
  Debug Log) + the existing dev-mode Vault and Temporal containers → **15 passed** (14
  pre-existing + 1 new workflow test; the API-level onboarding tests continued passing
  unchanged since Temporal only validates activity/workflow argument arity at execution time,
  not at `start_workflow` call time).
- `uv run ruff check apps/ packages/ migrations/` → all checks passed.
- `uv run pyright apps/api packages/domain packages/workflows apps/workers/discovery` → 0
  errors, 0 warnings.
- `npx vitest run` (apps/web) → **9 passed** (2 pre-existing + 1 new `DiscoverJourneysPlaceholder`
  test + 1 new `App.test.tsx` end-to-end breadcrumb/status-pill test; `ConnectAppForm.test.tsx`'s
  5 tests unaffected).
- `npx tsc -b` and `npx oxlint` (apps/web) → clean, no output.
- **Live end-to-end verification** (the real risk in this story — a queued-but-never-consumed
  workflow looks identical to a working one from the API response alone): ran the actual API
  and `discovery_worker.worker` process together against the throwaway Postgres + existing
  Vault/Temporal, created an Application via `curl` through `POST /applications`, and confirmed
  via `docker exec aitestgen-temporal-1 temporal workflow list` that its `DiscoveryWorkflow`
  (`discovery-<run-external-id>`) reached **Completed** — proving the dispatch path actually
  works (API → Temporal → worker → Activity), not just that a workflow was *started*. Also
  confirmed `GET /applications/{id}` still reports `discovery_status: "running"` afterward —
  `DiscoveryRun.status` transitioning to `complete` is Story 2.3's job, not this one's, and the
  workflow completing doesn't touch that column.
- Cleaned up all throwaway dev-test infrastructure (standalone Postgres container, temporary
  `uvicorn`/`discovery_worker` processes, seeded dev-test cookies) after verification.

### Completion Notes List

- **Task 1 required no code changes** — Story 1.3 had already added `DiscoveryRun`
  (`application_id`, `status` defaulting to `"running"`, `created_at`) ahead of this story
  (its own docstring: "Absorbed from removed Story 1.5's job"), and it already matches AD-10
  (`status` a plain `str`, no DB enum, mirroring the existing convention) and the org-scoping
  rule (transitive through `Application.organization_id`, no redundant column). One deliberate
  deviation from the task's literal wording: the story asks for a `started_at` column, but
  `created_at` already exists and serves exactly that role (a `DiscoveryRun` is only ever
  created already-running — Story 2.1 never creates one in any other state) — renaming an
  existing, already-migrated, already-tested column for no behavioral difference would be a
  pure-churn migration, so it was left as `created_at`.
- **`DiscoveryWorkflow` (`packages/workflows/src/workflows/discovery_workflow.py`) was already
  a no-op shell** from Story 1.3 (`return "started"`, no Activity call) — this story changed its
  signature to `run(application_id: str, secret_ref: str)` and made it call the
  `"DiscoveryActivity"` Activity by **registered name** (a string constant), not by importing
  the concrete function from `discovery_worker` — `packages/workflows` still depends on nothing
  but `temporalio`, keeping the dependency direction correct (workers depend on workflows, never
  the reverse). The `DiscoveryActivityInput` dataclass (the Activity's input shape) lives in
  `packages/workflows` for the same reason: it's the orchestration contract, which `workflows`
  owns; `discovery_worker` imports it to implement against it.
- **Did not touch/rename Story 1.1's `GenerationWorkflow` shell** — verified
  `packages/workflows/src/workflows/generation_workflow.py` is untouched; `DiscoveryWorkflow` was
  already its own separate definition (Story 1.3 built it that way), so there was no risk of the
  cross-story mistake the Dev Notes warn about.
- **`DiscoveryActivity` stub** (`apps/workers/discovery/src/discovery_worker/activities.py`) does
  exactly what Task 3 asks and no more: returns `f"dispatched:{application_id}"`, proving the
  dispatch path. It accepts `secret_ref` (per the task's instruction that Story 2.2's real
  Playwright work will need it) but never resolves it via `SecretsClient` — no real I/O, no
  Playwright import, nothing from Story 2.2's scope.
- **`DiscoveryRun`-creation logic extracted to `apps/api/src/api/discovery.py`** per Task 4's
  explicit instruction to make it "a function/service," not left inlined in `main.py` as Story
  1.3 had it. `create_application` in `main.py` now calls `start_discovery_run(session,
  application)`; behavior is unchanged except the workflow start now also passes
  `application.secret_ref` (required by the new two-arg workflow signature — without this fix,
  every `DiscoveryWorkflow` a real worker picks up would error on argument arity, invisible from
  the API's synchronous response alone. Caught by writing the Temporal time-skipping test first
  and confirmed by the live `curl` + `temporal workflow list` check).
- **`[GAP]` in Task 5 resolved against the current, same-day-updated UX spine, not built as
  written**: the story's Task 5 (written before or without accounting for `EXPERIENCE.md`'s
  2026-07-15 update) says to build "Discovery Progress" as a distinct pipeline step between
  Connect App and Discover Journeys. But `EXPERIENCE.md`'s UX-DR15 (superseded 2026-07-15) and
  UX-DR16 (updated the same day) — both more recent/authoritative than this story's own
  unresolved `[GAP]` flag — confirm the current IA is exactly 6 screens / 4 pipeline steps
  (Connect App, Discover Journeys, Review Scenarios, Generate Suite) with **no separate Discovery
  Progress screen**, and list only those four screens as carrying the breadcrumb rule. The
  existing frontend (`App.tsx`'s `View` type, `Stepper.tsx`'s `STEPS` array) already reflects
  exactly this 4-step IA with no fifth step, built during Story 1.3. Building a genuinely
  separate "Discovery Progress" route would have contradicted the confirmed current UX docs and
  the already-built stepper. Instead, AC 2 ("a status pill reading Running with a pulsing dot")
  is satisfied on the **Discover Journeys** screen — the current-IA surface that already showed
  `discoveryStatus` as plain text — by adding a real `StatusPill` component
  (`apps/web/src/components/StatusPill.tsx`) built to `DESIGN.md`'s `status-pill` tokens
  (`--signal-wash` background, `--signal` foreground, `--radius-full`, 11.5px/650 weight) with a
  CSS-animated pulsing dot shown only while `status === "running"`. This is the pill's first
  real, in-spec use, per the story's own note.
- **Breadcrumb rule (UX-DR16) required no change** — `TopBar`'s `applicationBadge` prop was
  already shown for every view other than `home` (built in Story 1.3), which already covers the
  `discover` view. Verified with a new end-to-end test in `App.test.tsx` that signs in, submits
  the Connect App form, and asserts the Application name + environment badge appear in the top
  bar alongside the Running status pill on Discover Journeys.
- **`StatusPill` deliberately stays minimal beyond "running"** — it capitalizes whatever status
  string it's given generically (no hardcoded map of `complete`/`failed` labels or color
  variants), since building distinct treatments for those statuses is Stories 2.3/2.4's job, not
  this one's.
- **Verification gap — no browser tool available in this environment**, same limitation noted in
  Stories 1.3/1.4's Dev Agent Records: the pulsing-dot animation's visual behavior was verified
  by code inspection (a standard CSS `@keyframes` opacity animation) and DOM assertions
  (`.status-pill-pulse-dot` class present only when running), not by watching it animate in a
  real browser.
- Per the operator's instruction for this session, **no git commits were created** — all changes
  are left in the working tree for review.

### File List

- `packages/workflows/src/workflows/discovery_workflow.py` — `DiscoveryWorkflow.run` now takes
  `application_id`/`secret_ref` and calls the `"DiscoveryActivity"` Activity by name; added
  `DiscoveryActivityInput` dataclass and `DISCOVERY_ACTIVITY_NAME` constant.
- `packages/workflows/src/workflows/__init__.py` — export `DiscoveryActivityInput` and
  `DISCOVERY_ACTIVITY_NAME`.
- `apps/workers/discovery/src/discovery_worker/activities.py` — new: the stub `DiscoveryActivity`
  implementation.
- `apps/workers/discovery/src/discovery_worker/worker.py` — registers `discovery_activity` on
  the worker (previously `activities=[]`).
- `apps/workers/discovery/tests/test_discovery_workflow.py` — new: Temporal time-skipping test
  proving the workflow dispatches to the Activity.
- `apps/api/src/api/discovery.py` — new: `start_discovery_run(session, application)`, the
  `DiscoveryRun`-creation + `DiscoveryWorkflow`-start logic extracted out of `main.py`.
- `apps/api/src/api/main.py` — `create_application` now calls `start_discovery_run` instead of
  inlining the `DiscoveryRun`/workflow-start logic; removed now-unused imports.
- `apps/web/src/components/StatusPill.tsx` — new: the `status-pill` component per `DESIGN.md`
  tokens, with a pulsing dot while `status === "running"`.
- `apps/web/src/components/DiscoverJourneysPlaceholder.tsx` — renders `StatusPill` instead of a
  plain-text status string.
- `apps/web/src/components/DiscoverJourneysPlaceholder.test.tsx` — new: asserts the Running pill
  and pulsing dot render.
- `apps/web/src/App.test.tsx` — new end-to-end test: sign in → submit Connect App form → assert
  the Application-name/environment breadcrumb and Running status pill appear on Discover
  Journeys.
- `apps/web/src/index.css` — added the `status-pill-pulse-dot` class and
  `@keyframes status-pill-pulse` animation.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `2-1-...` status tracking only.

## Change Log

- 2026-07-17 — Implemented all 6 tasks (AC 1–2): confirmed the pre-existing `DiscoveryRun` entity
  already satisfied Task 1, made `DiscoveryWorkflow` actually dispatch to a new stub
  `DiscoveryActivity` (previously a no-op), extracted the `DiscoveryRun`-creation logic into
  `api/discovery.py`, added the `StatusPill` component to Discover Journeys (resolving Task 5's
  `[GAP]` against the current UX spine rather than building a since-superseded separate
  "Discovery Progress" screen), and added full backend + frontend test coverage including a live
  Temporal CLI verification that the workflow actually completes end-to-end. Status moved to
  `review`.
