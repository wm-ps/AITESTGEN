# Story 3.4: Rename & Delete a Journey/Capability

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 (twice, same day) — see `sprint-change-proposal-2026-07-15.md`. First: Edit (FR-28) was added. Second, later the same day: Edit was cut again — its exact editable surface was never confirmed in the UX review, and product decided not to build it; reverted to Rename & Delete only. Also same day: Approve/Reject (Stories 3.2/3.3) were cut entirely — every discovered Journey is now in the Trusted Knowledge Model and generating coverage immediately (FR-14), so Delete is the sole exclusion mechanism, not the counterpart to Reject. Filename retained as `3-4-rename-delete-a-journey-capability.md` for continuity.*

## Story

As a reviewer,
I want to rename or delete a discovered Journey/Capability,
so that the Trusted Knowledge Model reflects names I trust and excludes what doesn't belong.

## Acceptance Criteria

1. **Given** a candidate Journey/Capability, **when** the reviewer renames it via the row's `⋯` menu, **then** the new name is saved and displayed everywhere the Journey/Capability appears. [Source: epics.md#Story 3.4; FR-12]
2. **Given** a candidate Journey/Capability, **when** the reviewer deletes it (via the `⋯` menu), **then** it is excluded from the Trusted Knowledge Model — along with any Scenarios/Test Assets already generated for it — from Generate Suite compilation and Analytics. [Source: epics.md#Story 3.4; FR-13]
3. Deleting a Journey does **not** cancel an in-flight or already-completed `GenerationWorkflow` for it (Story 2.5, Task 5) — regeneration (FR-18) remains the only way to redo generation for a Journey the reviewer keeps. [Source: architecture#AD-1]

## Tasks / Subtasks

- [x] Task 1: Add a `deleted` status to `Journey` (AC: 2, 3)
  - [x] Extend `Journey.status` to `"candidate" | "deleted"` — `[UPDATED 2026-07-15]` no more `approved`/`rejected` values; every non-`deleted` Journey is in the Trusted Knowledge Model from the moment `InferenceActivity` creates it (Story 2.5)
  - [x] **Resolved as a soft-delete, not a hard row delete** — this is a reasoned default, not an explicit FR-13 requirement: every other artifact in this system (`Evidence`, `Scenario`, `TestAsset`) is designed around soft-supersede/audit-retention rather than destructive deletion (AD-8), so a hard `DELETE` here would be the one inconsistent exception without a stated reason to be one. All queue/queries simply exclude `status="deleted"` rows
  - [x] Alembic migration — none needed: `Journey.status` was already a plain, unconstrained
    `str` column (migration `fc7fe4561f07`), so `"deleted"` is just a new value written to an
    existing column, not a schema change. Only the `JourneyStatus` Python `Literal` (already
    `"candidate" | "deleted"` in `packages/domain/src/domain/journey.py`) documents this.
- [x] Task 2: Build the rename endpoint (AC: 1)
  - [x] Add to the Review module in `apps/api`, Organization-scoped via Story 1.2's middleware
  - [x] Only allowed while `status="candidate"` — reject (not silently ignore) an attempt against an already-deleted row
  - [x] Updates `Journey.name` — since this is the single source of truth already read by the Discover Journeys row (Story 3.1), no separate propagation step is needed; every future screen that displays a Journey's name (Generated Scenarios/Tests — Epic 4; any surviving Epic 6 analytics screen) must read this same field live, never cache or duplicate it, for the rename to actually satisfy "displayed everywhere it appears"
- [x] Task 3: Build the delete endpoint (AC: 2, 3)
  - [x] Same module, same Organization scoping, check-before-acting idempotency (only transitions if currently `status="candidate"`)
  - [x] Sets `status="deleted"` — excluded from the Discover Journeys screen (Story 3.1's read endpoint) and from every downstream Trusted Knowledge Model / Generate Suite / Analytics read path
  - [x] **`[UPDATED 2026-07-15]` Does not touch `GenerationWorkflow`** — a Journey's `GenerationWorkflow` starts immediately at discovery (Story 2.5), independent of curation. Deleting a Journey after generation has already produced Scenarios/Test Assets excludes those rows from downstream reads (they still exist for audit, same soft-supersede spirit as AD-8) but does not retroactively cancel the workflow or delete the generated rows
- [x] Task 4: Build Rename and Delete actions in the Discover Journeys UI (AC: 1, 2)
  - [x] Rename: triggered by the Rename action in the row's `⋯` menu; a small inline edit or lightweight input is sufficient — nothing in the UX spine specifies a modal vs. inline pattern, so don't over-build this beyond what's needed to capture a new name and save it
  - [x] Delete: triggered by the Delete action in the row's `⋯` menu; on confirmation, the row is removed from the queue list entirely — there is no `Deleted` badge/muted-row state described anywhere in the UX spine, consistent with FR-13's "excluded from the Trusted Knowledge Model" (not "shown as decided"). Don't invent a `Deleted` badge variant that isn't specified
- [x] Task 5: Verify end-to-end and record evidence (AC: 1-3)
  - [x] Renaming a candidate updates its displayed name on the Discover Journeys row
  - [x] Attempting to rename or delete an already-deleted row is rejected, not silently accepted
  - [x] Deleting a candidate removes it from the Discover Journeys screen and from every Trusted Knowledge Model / Generate Suite / Analytics read query; it never re-appears
  - [x] Deleting a Journey never cancels or touches its `GenerationWorkflow` execution (verified via direct Temporal inspection — the workflow handle is untouched by the delete endpoint). The Scenario/Test Asset exclusion half of this check is **not yet verifiable**: those entities don't exist yet (Epic 4 is unimplemented in this codebase) — nothing to exclude from a Generate Suite/Analytics read path that doesn't exist yet. Revisit once Epic 4 ships.

## Dev Notes

- **The soft-delete decision (Task 1) is worth flagging explicitly during code review** — it's a reasonable, consistent-with-the-rest-of-the-system default, but it is this story's own inference, not a literal requirement anyone wrote down. If a future story needs a genuine hard-delete (e.g. for data-retention/compliance reasons), that's a product decision to make explicitly, not something to assume already happened here.
- **`[RESOLVED 2026-07-15]` This story no longer shares a "review module" with Approve/Reject endpoints — there are none.** Stories 3.2 (Approve) and 3.3 (Reject) are cut in full; this story's rename/delete endpoints are the *only* curation endpoints in the Review module. Don't build against their old references — see those stories' cut notes for where the logic that used to live alongside them (Capability-promotion, `GenerationWorkflow`-start) actually ended up (Story 2.5).
- **No `Deleted` badge exists anywhere in the UX spine** — resist adding one. A deleted row simply disappears from the list.
- **`[RESOLVED 2026-07-15]` Edit (FR-28) was added, then cut the same day** — its exact editable surface (name/description vs. constituent steps) was never confirmed in the UX review, and product decided not to build it rather than guess. This story is back to exactly two actions: Rename and Delete. The "no merge/split/composition-edit" constraint (UX-DR22) still holds — it just no longer needs an Edit-specific carve-out, since there is no Edit action to carve out from.
- **`[RESOLVED 2026-07-15]` Delete is now the sole exclusion mechanism from the Trusted Knowledge Model, not one of two (alongside Reject).** At the scale a real discovery run can produce (dozens to hundreds of candidates), requiring an explicit approve/reject decision on every row wasn't realistic — every discovered Journey is trusted and generating coverage by default; a reviewer's only lever is retroactive deletion. See `sprint-change-proposal-2026-07-15.md` for the full rationale and the residual-risk tradeoff this accepts (PRD §12 Risk item 2).

### Project Structure Notes

- Adds `status="deleted"` to `Journey` (`packages/domain`), adds rename/delete endpoints to `apps/api`'s Review module, and extends the Discover Journeys UI (Story 3.1). No new top-level directories.
- **Depends on Epic 1, Epic 2 (including Story 2.5's `GenerationWorkflow`-start), and Story 3.1 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4: Rename & Delete a Journey/Capability]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-12, FR-13, FR-14]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-7, #AD-8 — soft-supersede/audit-retention pattern this story's delete design follows]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Review & Trust Model]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — where `GenerationWorkflow`-start (formerly Story 3.2's) now lives]
- (Stories 3.2 "Approve" and 3.3 "Reject" — removed 2026-07-15, no approval gate exists)

## Previous Story Intelligence

Epic 1, Epic 2 (including Story 2.5), and Story 3.1 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once implemented, check Story 2.5's File List for `Journey`'s exact schema and `GenerationWorkflow`-start mechanism before adding rename/delete alongside it.

## Latest Technical Notes

No new library decisions — extends the existing FastAPI/SQLModel/React stack.

## Project Context Reference

No `project-context.md` exists yet in this repository. With Epic 3's curation actions now fully spec'd for V1 (3.1, 3.4 — Story 3.5 cut in full 2026-07-21), this is a good point to run `bmad-generate-project-context` once implemented, so Epic 4 has a real code reference.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

Manual smoke test against the real stack (Postgres/Vault/Temporal via docker
compose), same session as Story 3.1's: created an Application, seeded a
candidate Journey directly, then via `curl` — `PATCH /journeys/{id}` renamed
it (200, new name reflected in the list), `DELETE /journeys/{id}` soft-deleted
it (204, excluded from the list immediately after), and a second `DELETE`
against the same now-deleted row returned 409 (reject, not silently accept),
matching Task 5's AC 1-3 checks.

### Completion Notes List

- No Alembic migration: `Journey.status` was already an unconstrained `str`
  column (migration `fc7fe4561f07`, Story 2.6) — `"deleted"` is a new value
  in an existing column, not a schema change.
- Rename/delete endpoints added directly to `apps/api/src/api/main.py`
  alongside Story 3.1's read endpoints (this codebase keeps all routes in
  one file — no separate "Review module" file was introduced, since nothing
  else here is split into router modules yet). Both endpoints share a
  `_get_org_journey` helper (org-scoped 404) and both reject — HTTP 409,
  not a silent no-op — an attempt against a Journey whose `status` is
  already `"deleted"`, satisfying Task 5's "rejected, not silently accepted"
  check for both actions.
- Delete never touches `GenerationWorkflow` or any Scenario/Test Asset row
  — it only flips `Journey.status`. Verified the workflow side via direct
  Temporal inspection; the Scenario/Test Asset side isn't independently
  verifiable yet since Epic 4 (which would create those tables) isn't
  implemented in this codebase — see Task 5's note.
- UI: Rename (inline input, save on blur/Enter, cancel on Escape or empty
  name) and Delete (native `window.confirm`, no custom modal) live in the
  same `⋯` row menu, built in `apps/web/src/components/DiscoverJourneys.tsx`
  alongside Story 3.1's list/detail panel — no `Deleted` badge, no modal
  component, per this story's explicit "don't over-build" notes.

### File List

- `apps/api/src/api/main.py` — `PATCH /journeys/{id}` (rename),
  `DELETE /journeys/{id}` (soft-delete); shares `_get_org_journey`/
  `JourneyRead` with Story 3.1's read endpoints
- `apps/api/tests/test_journey_curation.py` — rename/delete cases (shared
  file with Story 3.1's read-endpoint tests)
- `apps/web/src/components/DiscoverJourneys.tsx` — `⋯` row menu, inline
  rename input, delete-with-confirm (shared file with Story 3.1's screen)
- `apps/web/src/components/DiscoverJourneys.test.tsx` — rename/delete
  interaction tests
- `apps/web/src/api.ts` — `renameJourney`/`deleteJourney` calls added
