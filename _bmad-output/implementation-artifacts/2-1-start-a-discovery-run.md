# Story 2.1: Start a Discovery Run

Status: ready-for-dev

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

- [ ] Task 1: Add the `DiscoveryRun` domain entity (AC: 1)
  - [ ] Add `DiscoveryRun` (`application_id` FK, `status`, `started_at`) to `packages/domain`, following the UUIDv7-internal/UUIDv4-external id convention established in Story 1.3
  - [ ] `status` is one of `running | complete | failed` per AD-10 (`[UPDATED 2026-07-15]` no `incomplete` value — FR-5/time-budget removed, so the only stop condition is exhaustive traversal) — this story only ever sets `running`; the other transitions belong to Stories 2.3 (`complete`) and 2.4 (`failed`), which will each add their own supporting columns (e.g. 2.4 adds `failure_reason`) — don't pre-build those columns speculatively here
  - [ ] Organization scoping is transitive through `Application.organization_id` — reuse whatever central scoping mechanism Story 1.2 actually built (a query-layer filter or FastAPI dependency) rather than adding a redundant direct `organization_id` column here, unless Story 1.2's implementation specifically requires every scoped table to carry one; check its File List before deciding
  - [ ] Alembic migration
- [ ] Task 2: Build `DiscoveryWorkflow` — a new workflow, not a reuse of Story 1.1's shell (AC: 1)
  - [ ] Add `DiscoveryWorkflow` to `packages/workflows`: bounded, orchestration-only (AD-2) — no network/DB/browser calls inside the workflow itself, only a call to a Discovery Activity
  - [ ] **This must be a new, separate workflow definition.** Story 1.1's trivial no-op workflow was explicitly earmarked for `GenerationWorkflow`, graduated by Story 2.5's `InferenceActivity` (`[UPDATED 2026-07-15]` originally Story 3.2, now removed) — not this one. Reusing or renaming that shell for `DiscoveryWorkflow` would leave Epic 2/4 without the shell they're each depending on. Build `DiscoveryWorkflow` fresh, following the same orchestration-only pattern 1.1 demonstrated, but as its own definition
- [ ] Task 3: Stub `DiscoveryActivity` — dispatched, not yet functional (AC: 1)
  - [ ] Add a `DiscoveryActivity` to `apps/workers/discovery`, dispatched by `DiscoveryWorkflow`, accepting the `Application` (and its `secret_ref`) — for this story, it only needs to prove the dispatch path end-to-end (API → Temporal → worker → Activity); it does **not** need to perform any real Playwright navigation or capture any `Evidence` yet
  - [ ] The actual autonomous crawling behavior (pages, actions, forms, API calls) is Story 2.2's job, exactly as Story 1.1 deliberately left its own workflow's Activity as a no-op proof rather than building real behavior ahead of its owning story. Don't reach into 2.2's scope here
- [ ] Task 4: `[REWRITTEN 2026-07-15]` Build the `DiscoveryRun`-creation logic as a function Story 1.3's onboarding endpoint calls — not a separate endpoint (AC: 1)
  - [ ] Previously specified as a standalone POST endpoint (e.g. `/applications/{id}/discovery-runs`), gated on `Application.status="ready"` (set by the now-removed Story 1.5). Both are gone: Story 1.3's Connect App submission is a single atomic creation with no draft/ready distinction, so there is no separate endpoint to call and no status precondition to check
  - [ ] Implement the shared logic — create the `DiscoveryRun` row (`status=running`) and start `DiscoveryWorkflow` via the Temporal client wired in Story 1.1 — as a function/service Story 1.3's Task 3 calls directly in the same request that creates the `Application`, not as an independently user-triggered action
- [ ] Task 5: Build the Discovery Progress screen (AC: 1, 2) — **`[UPDATED 2026-07-15]`**
  - [ ] Story 1.3's Connect App submission directly starts the Discovery Run and navigates into the pipeline (its Task 3/4) — there is no separate "Applications screen" action or table row to build; that surface remains unconfirmed to exist at all in the current IA
  - [ ] Build Discovery Progress: shows the status pill reading "Running" with a pulsing dot, using `DESIGN.md`'s documented `status-pill` component/tokens (this is the pill's first real, in-spec use). **`[GAP]`** whether Discovery Progress is a distinct screen/step in the current pipeline (between Connect App and Discover Journeys) or a transient loading state was not confirmed during UX review — build it as a distinct step for now, but re-verify against a fuller prototype export
  - [ ] Application-name breadcrumb *is* shown on Discovery Progress per UX-DR16 — this is the first Application-scoped screen built; get the breadcrumb-inclusion rule right here since every later Application-scoped screen (Discover Journeys, Review Scenarios, ...) follows the same rule
- [ ] Task 6: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Creating an Application (Story 1.3) creates a `DiscoveryRun(status=running)` row and a running `DiscoveryWorkflow` in the same request, observable via Temporal CLI/Web UI — with no separate action taken
  - [ ] Discovery Progress shows the "Running" status pill with a pulsing dot for the new run

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

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
