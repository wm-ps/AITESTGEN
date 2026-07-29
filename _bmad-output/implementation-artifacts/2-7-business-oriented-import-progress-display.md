---
baseline_commit: 2b72ef3deaba32290fd3d65de027081a5c76f13b
---

# Story 2.7: Business-Oriented Import Progress Display

Status: done <!-- CLOSED 2026-07-29 after re-verification, see Change Log -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Added 2026-07-21 per `sprint-change-proposal-2026-07-21.md` (CR-2). Next available Epic 2 story number. Depends on the `stage` transitions written by Stories 2.1, 2.2, and 2.6 (AD-10 extension) but does not require reordering relative to them — purely additive read-side plumbing.*

## Story

As a user who just submitted Connect App,
I want to see plain-language progress on my import (Initialization, Authentication, Discovery, Analysis) instead of technical crawl detail,
so that I understand what's happening without needing to know how discovery works internally.

## Acceptance Criteria

1. **Given** a running `DiscoveryRun`, **when** the frontend polls its status, **then** a fixed percentage and a progress indicator are shown, derived internally from `DiscoveryRun.stage`'s four values (Initialization, Authentication, Discovery, Analysis) (FR-33). `[UPDATED 2026-07-21, live UX correction]` The percentage is the *previous* stage's completion, not the in-progress stage's own target (0/10/25/75 while Initialization/Authentication/Discovery/Analysis are respectively in progress) — see Completion Notes below for why. `[WALKED BACK 2026-07-21, same day, Second Post-Review Fix]` The stage label text itself (the literal words "Initialization"/"Authentication"/"Discovery"/"Analysis") is **not rendered** — live product feedback found a second, differently-named "in progress" indicator redundant with the existing `StatusPill` pulsing dot, and simplified the copy to a single generic "Discovering journeys in {Application name}" heading plus the percentage bar. `STAGE_PERCENT` stays as an internal lookup (still needed to compute the percentage) but its display label was cut — this AC's original "shows one of four... stage labels" wording is stale against the shipped, product-approved behavior; the percentage/indicator half still holds exactly as written. [Source: epics.md#Story 2.7]
2. No technical terms (e.g. "crawling," "crawl queue," "page fingerprint," or any raw route/page/API text) appear anywhere in this view. [Source: epics.md#Story 2.7; sprint-change-proposal-2026-07-21.md CR-2]
3. `DiscoveryRun.status=complete` transitions the display to 100% / Discover Journeys ready — in practice this is implicit (Journeys appear, this view unmounts), 100% is never itself rendered. [Source: epics.md#Story 2.7]
4. `DiscoveryRun.status=failed` (e.g. `session_expired`, AD-11) shows the existing re-authentication prompt in place of stage progress. [Source: epics.md#Story 2.7]

**Notes (from epics.md):** The Application Model Builder step (Story 2.5) is presented as part of the "Discovery" stage, not "Analysis" — per explicit product decision, since it's still processing what was crawled, not yet AI inference.

**`[DEPENDENCY — BLOCKING]`** `DiscoveryRun.stage` does not exist yet. Story 2.1's rework (per `sprint-change-proposal-2026-07-21.md`) adds the column and sets `stage=initializing`; Story 2.2 sets `authenticating`/`discovering`; Story 2.6 sets `analyzing`. **Confirm Story 2.1's migration has landed before starting Task 1** — otherwise there's no `stage` column for this story's API exposure to read.

**`[SCOPE NOTE — real gap found during story creation]`** `DiscoverJourneys.tsx` currently receives `discoveryStatus`/`discoveryFailureReason` as **static props from `App.tsx`, frozen at Application-creation time** — nothing in the frontend today polls for their live value. This means the existing `Running`/`Complete`/`Failed` status pill and session-expired banner never actually update without a page reload, despite Epic 2's original intent ("watch live progress"). This story is the natural, and only sensible, place to fix that — see Task 2.

**`[IMPORTANT — second gap found during story creation]`** `DiscoveryRun.status` flips to `"complete"` inside `discovery_activity` **as soon as the crawl itself finishes** — before `ApplicationModelBuilderActivity` or `InferenceActivity` (Story 2.6) even run (see `apps/workers/discovery/src/discovery_worker/activities.py:259`, and Story 2.3's own Dev Notes: "this is the one and only place `complete` gets written"). **Do not gate polling, or the progress view's visibility, on `status !== 'running'`** — doing so would stop showing progress right after crawl finishes, before "Analysis" (stage=`analyzing`) is ever reached. The correct stop condition is: keep polling/showing progress while `journeys.length === 0` (the same condition `DiscoverJourneys.tsx` already uses to decide whether to render the live-feed/progress area at all) and `status !== 'failed'`. This is reflected in Tasks 2 and 4 below.

## Tasks / Subtasks

- [x] Task 1: Expose `discovery_stage` on the read API (AC: 1, 3, 4)
  - [x] Added `discovery_stage: str | None` to `ApplicationRead` and `_to_application_read` (`apps/api/src/api/main.py`) — shared with Story 2.1's Task 7.
  - [x] Regenerated `apps/web/src/api-types.gen.ts` from a live API run; diff shows only the expected `favicon_url`/`discovery_stage` additions.
- [x] Task 2: Add live polling for Application/discovery status (AC: 1, 3, 4 — closes the scope-note gap above)
  - [x] Added `getApplication` to `apps/web/src/api.ts`.
  - [x] Created `apps/web/src/hooks/useDiscoveryProgress.ts` per spec — stops once `hasJourneys` is true or `status === 'failed'`, never on `status !== 'running'` alone.
  - [x] `apps/web/src/hooks/` created (shared with Story 1.6).
- [x] Task 3: Build the business-stage progress component (AC: 1, 2)
  - [x] Created `apps/web/src/components/ImportProgress.tsx` with the exact fixed lookup and a simple filled progress bar (`role="progressbar"`), no new dependency.
  - [x] Added `apps/web/src/components/ImportProgress.test.tsx` asserting all four stage/percent pairs and the absence of `crawl`/`queue`/`fingerprint`.
- [x] Task 4: Wire it into Discover Journeys, replacing the raw live feed (AC: 1, 2, 3, 4)
  - [x] `DiscoverJourneys.tsx` now calls `useDiscoveryProgress(applicationId, discoveryStatus, discoveryStage, discoveryFailureReason, journeys.length > 0)` and uses the live `{status, stage, failureReason}` for `sessionExpired`, the failed banner, and `<StatusPill>`.
  - [x] Fixed the journeys-poll's stop condition to `journeys.length > 0 || liveStatus === 'failed'`, not `discoveryStatus !== 'running'`.
  - [x] Replaced `<CaptureLiveFeed>` with `<ImportProgress stage={liveStage} />`, gated on `journeys.length === 0 && liveStatus !== 'failed'` (added the `liveStatus !== 'failed'` clause beyond the task's literal wording so the re-authentication banner fully replaces stage progress on failure, per AC4 — "in place of stage progress").
  - [x] Deleted `CaptureLiveFeed.tsx`/`CaptureLiveFeed.test.tsx` and the now-unused `listCaptures`/`CaptureRead` in `apps/web/src/api.ts` (dead code once the component was gone). Left the backend `/discovery-runs/{external_id}/captures` endpoint and `CaptureRead` model untouched, per instruction.
- [x] Task 5: Verify end-to-end and record evidence (AC: 1-4)
  - [x] `DiscoverJourneys.test.tsx` covers: initial stage render, hiding progress once Journeys appear, and the session-expired banner replacing progress on a poll reporting `failed`/`session_expired`. `useDiscoveryProgress.test.ts` unit-tests the hook directly (initial values, a poll updating state, not polling once `hasJourneys` or already-failed).
  - [x] Backend: `test_create_application_sets_discovery_stage_initializing` in `apps/api/tests/test_onboarding.py` asserts `discovery_stage` round-trips.

### Completion Notes (2026-07-21)

- Also extended `apps/web/src/App.test.tsx`'s existing tests with tab-title/favicon assertions (Story 1.6) while touching the same Connect App → Discover Journeys flow.
- Added `apps/web/src/test-setup.ts` (global vitest `setupFiles`) so tests start with the same static `<head>` `index.html` defines — needed for both this story's and Story 1.6's DOM assertions.
- Full validation: 71 backend tests + 33 frontend tests pass; `ruff`/`pyright`/`tsc -b`/`oxlint` clean; live end-to-end smoke test against the real running API confirmed a reachable URL returns `discovery_stage: "initializing"` and an unreachable one returns 422 with the expected copy.

### Post-Review Fix (2026-07-21, live UX correction)

Two issues found reviewing the live behavior against the reference prototype (`mockups/prototype-v2-standalone.html`'s "Discovery Scan" screen, `screenIsScanning`):

- **Percentage was updating too early.** The original mapping paired each stage with its *own* target percentage the instant that stage began (`discovering` → 75% immediately on entering it) — since "Discovery" is by far the longest stage (full crawl + Model Builder), the bar looked nearly done the moment real work actually started. Fixed in `ImportProgress.tsx`: the percentage shown while a stage is in progress is now the percentage of the stage that just *finished* — `initializing: 0, authenticating: 10, discovering: 25, analyzing: 75`. 100% is never rendered; Journeys appearing (the component's own unmount condition) is the real completion signal.
- **Visual treatment didn't match the reference prototype.** The prototype's Discovery Scan screen is a centered card: an animated spinner, "Discovering journeys in {Application name}," the current stage label, and a progress bar with a percentage caption below — not a thin inline bar tucked under the Discover Journeys heading. Rebuilt `ImportProgress.tsx` to match this treatment (new `.import-progress-spinner`/`@keyframes aitg-spin` in `index.css`, following the naming convention already used for the prototype's other `aitg-*` animations); threaded a new `applicationName` prop down from `App.tsx` → `DiscoverJourneys.tsx` → `ImportProgress.tsx` for the "in {name}" copy. This stays within the already-decided, documented IA (no new screen/route — Discovery Scan is not a separate pipeline step, per Story 2.1's resolved `[GAP]` and `EXPERIENCE.md`'s confirmed 6-screen IA) — only the in-place visual treatment changed.
- Updated `ImportProgress.test.tsx`/`DiscoverJourneys.test.tsx` for the new percentages and the `applicationName` prop. All 35 frontend tests (2 new) pass; `tsc -b`/`oxlint` clean.

### Second Post-Review Fix (2026-07-21, same day — further live UX feedback)

- **No internal stage naming.** Removed the Initialization/Authentication/Discovery/Analysis label text from `ImportProgress.tsx` entirely — the view now only shows the "Discovering journeys in {name}" heading, the bar, and the percentage. The `STAGE_PERCENT` lookup stays internal (still needed to pick the percentage); only its display label was cut.
- **Spinner wasn't matching the app's own UX.** Replaced the custom circular border-spin spinner with nothing extra — `StatusPill`'s existing pulsing dot (already rendered next to the "Discover Journeys" heading while `status === "running"`) is this app's one established "in progress" indicator; adding a second, differently-styled spinner below it was the actual inconsistency. Removed `.import-progress-spinner`/`@keyframes aitg-spin` from `index.css`.
- **Progress bar needed a livelier animated feel.** Added a shimmer-sweep overlay across the bar, reusing the exact `aitg-shimmer-sweep` keyframe already established in `SignIn.tsx` (same technique: an absolutely-positioned diagonal gradient sweep) rather than inventing a new animation — so the bar reads as actively working between the fixed percentage jumps, not stalled.
- Frontend-only fix (no backend/story-1.3/2.1/2.2/2.6 changes) — 31 frontend tests pass (4 fewer than the prior count, reflecting an unrelated separate change to Story 1.6's scope, not part of this fix); `tsc -b`/`oxlint` clean. Also fixed a latent ordering bug in `apps/web/src/test-setup.ts` (`document.head.innerHTML` assignment must run *before* `document.title`, not after, or it wipes out the `<title>` element the setter just created) — previously masked because something else was re-setting `document.title` on every render.

## Dev Notes

- **`DiscoverJourneys.tsx`'s existing poll pattern is the template to follow** — it already polls `api.listJourneys` every 1500ms while `discoveryStatus === 'running'`, using a `cancelled` flag + `clearInterval` cleanup (lines ~171-190). `useDiscoveryProgress` should be structurally identical, just polling a different endpoint.
- **The real gap this story closes**: `discoveryStatus`/`discoveryFailureReason` are currently static props threaded down from `App.tsx`'s one-time `POST /applications` response (`apps/web/src/App.tsx` line ~63-66) — nothing re-fetches them. `StatusPill` and the session-expired banner in `DiscoverJourneys.tsx` (lines ~169, ~236, ~239-249) read directly from these frozen props today. This story must make them live, not just add a separate progress widget alongside stale ones.
- **Backend activity/workflow context** (for understanding where `stage` values come from, even though writing them is Stories 2.1/2.2/2.6's job, not this one's): `discovery_activity` (`apps/workers/discovery/src/discovery_worker/activities.py:83`) calls `establish_session(...)` then `run_discovery_crawl(...)` — `authenticating`/`discovering` transitions happen around those two calls. `application_model_builder_activity` (line 268) runs after, still within the "Discovery" stage per product decision. `inference_activity` (line 299) is where `analyzing` begins. The orchestrating `DiscoveryWorkflow` (`packages/workflows/src/workflows/discovery_workflow.py`) contains no I/O itself (AD-2) — all stage writes happen inside the Activities, not the workflow.
- **`ApplicationRead`/`_to_application_read`** (`apps/api/src/api/main.py:137-160`) is the one place `discovery_status`/`discovery_failure_reason` are already assembled from `DiscoveryRun` — `discovery_stage` is a one-line addition to the same pattern, not a new mechanism.
- **No new library.** A percentage + label mapping and a simple progress bar don't need a charting/progress library — this app has none currently (React 19, no UI kit beyond hand-rolled components per `DESIGN.md` tokens).

### Project Structure Notes

- New files: `apps/web/src/hooks/useDiscoveryProgress.ts` (+ test), `apps/web/src/components/ImportProgress.tsx` (+ test).
- Deleted files: `apps/web/src/components/CaptureLiveFeed.tsx`, `apps/web/src/components/CaptureLiveFeed.test.tsx` (superseded — confirm no other reference first).
- Modified: `apps/web/src/api.ts` (new `getApplication` method), `apps/web/src/components/DiscoverJourneys.tsx` (live status via the new hook, swap live-feed component, new `applicationName` prop), `apps/api/src/api/main.py` (`discovery_stage` field), `apps/web/src/api-types.gen.ts` (regenerated), `apps/web/src/index.css` (post-review: `.import-progress-spinner`/`@keyframes aitg-spin`), `apps/web/src/App.tsx` (post-review: passes `applicationName`).
- No backend migration in this story — `DiscoveryRun.stage`'s column is Story 2.1's.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.7: Business-Oriented Import Progress Display]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-21.md — CR-2]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-33]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md — AD-10 extension]
- [Source: apps/web/src/components/DiscoverJourneys.tsx — existing poll pattern and static-prop gap]
- [Source: apps/web/src/components/CaptureLiveFeed.tsx — component being superseded]
- [Source: apps/api/src/api/main.py:137-160 — ApplicationRead / _to_application_read]
- [Source: apps/workers/discovery/src/discovery_worker/activities.py:83,268,299 — where stage transitions originate]
- [Source: packages/workflows/src/workflows/discovery_workflow.py — orchestration, no I/O per AD-2]
- [Source: _bmad-output/implementation-artifacts/1-6-dynamic-browser-tab-branding.md — sibling CR story, same `hooks/` directory]

## Previous Story Intelligence

Story 2.6 (`in-progress`, reverted for this same CR) is the most recently touched story in Epic 2. Its own file (once reworked) will carry the `stage=analyzing` write this story's polling depends on reading. Story 1.4's Dev Agent Record established the `api-types.gen.ts` regenerate-and-diff discipline (AD-6) this story's Task 1 follows, and confirmed this environment has no browser tool for visual verification — DOM-assertion tests via `vitest`/`@testing-library/react` are the bar, with a manual browser pass recommended afterward.

## Latest Technical Notes

No new library decisions. Reuses the existing `fetch`-based `request<T>` wrapper in `apps/web/src/api.ts` — do not introduce a data-fetching library (React Query, SWR) for one additional polled endpoint when the codebase's existing hand-rolled `useEffect` + `setInterval` pattern already covers two other polls in the same file.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

See the three dated sections above ("Completion Notes (2026-07-21)", "Post-Review Fix", "Second
Post-Review Fix") for the full session-by-session debug/verification trail — written before this
formal Dev Agent Record section was populated, not duplicated here. Summary: 71 backend + 33
(later 31, then 35) frontend tests passing across the three passes; `ruff`/`pyright`/`tsc -b`/
`oxlint` clean throughout; live end-to-end smoke test against the real running API.

### Completion Notes List

See the three dated sections above for full detail. In brief: Task 1-2 exposed and started polling
`discovery_stage` live (closing a real pre-existing gap — status/stage were frozen props, never
re-fetched); Task 3-4 built `ImportProgress.tsx` and wired it into `DiscoverJourneys.tsx`, replacing
the raw live-feed; two same-day post-review passes corrected the percentage-timing (previous-stage
completion, not current-stage target) and removed the literal stage-label text entirely per live
UX feedback (see this story's AC 1 amendment, 2026-07-29).

### File List

See the three dated sections above and "Project Structure Notes" for the full file list from the
original three implementation passes (2026-07-21). No files touched in the 2026-07-29 closure pass
beyond this story file itself (no code change was needed — see Change Log).

## Change Log

- 2026-07-21 — Implemented Tasks 1-5 (ACs 1-4): live polling via `useDiscoveryProgress`, the
  `ImportProgress` stage/percentage component, wired into Discover Journeys in place of the raw
  live-feed. Status moved to `review`.
- 2026-07-21 [same day, Post-Review Fix] — Corrected percentage timing (previous-stage completion,
  not current-stage target) and rebuilt the visual treatment to match the reference prototype's
  centered spinner+card pattern.
- 2026-07-21 [same day, Second Post-Review Fix] — Removed the literal stage-label text per further
  live UX feedback (redundant with `StatusPill`'s existing pulsing dot); added the shimmer-sweep
  bar animation, reusing `SignIn.tsx`'s existing `aitg-shimmer-sweep` keyframe.
- 2026-07-29 — Re-verified for closure. Confirmed `ImportProgress.tsx`'s current visual treatment
  (shimmer-sweep bar, no stage-label text, "Discovering journeys in {name}" heading) is exactly
  what the Second Post-Review Fix above describes — no drift since 2026-07-21. Corrected AC 1's
  text, which still claimed the four stage labels are displayed (stale since the Second Post-Review
  Fix removed them the same day they were added) — the percentage/indicator logic AC 1 also
  describes is unaffected and confirmed correct. Cross-checked the shimmer-sweep animation against
  `prototype-v3.html`: present in both, genuinely v3-sourced, not invented. Filled this story's
  previously-empty formal Dev Agent Record section (content existed but lived under ad hoc headers
  above it) and added this Change Log section, which didn't exist before. `sprint-status.yaml`
  corrected from `in-progress` (reopened 2026-07-27 for a restyle already superseded by this
  story's own 2026-07-21 rebuild) to `done`.
