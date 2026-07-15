# Story 3.4: Rename, Edit & Delete a Journey/Capability

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 — adds Edit (FR-28), previously out of scope; see `sprint-change-proposal-2026-07-15.md`. Filename retained as `3-4-rename-delete-a-journey-capability.md` for continuity; this story's title and scope are now "Rename, Edit & Delete."*

## Story

As a reviewer,
I want to rename, edit, or delete a discovered Journey/Capability,
so that the Trusted Knowledge Model reflects names and content I trust.

## Acceptance Criteria

1. **Given** an undecided candidate Journey/Capability, **when** the reviewer renames it via the row's `⋯` menu, **then** the new name is saved and displayed everywhere the Journey/Capability appears. [Source: epics.md#Story 3.4; FR-12]
2. **Given** an undecided candidate Journey/Capability, **when** the reviewer chooses Edit from the `⋯` menu, **then** they can modify it and the change is saved. [Source: epics.md#Story 3.4; FR-28]
3. **Given** an undecided candidate Journey/Capability, **when** the reviewer deletes it (via the `⋯` menu), **then** it is removed from the review queue and never enters the Trusted Knowledge Model. [Source: epics.md#Story 3.4; FR-13]

**`[GAP]`** The exact editable surface for AC 2 (name/description only, vs. constituent steps) is unconfirmed — do not build against an assumed field set without a follow-up UX pass. [Source: epics.md#Story 3.4]

## Tasks / Subtasks

- [ ] Task 1: Add a `deleted` status to `Journey` (AC: 3)
  - [ ] Extend `Journey.status` to include `"deleted"` alongside `candidate | approved | rejected`
  - [ ] **Resolved as a soft-delete, not a hard row delete** — this is a reasoned default, not an explicit FR-13 requirement: every other artifact in this system (`Evidence`, `Scenario`, `TestAsset`) is designed around soft-supersede/audit-retention rather than destructive deletion (AD-8), so a hard `DELETE` here would be the one inconsistent exception without a stated reason to be one. All queue/queries simply exclude `status="deleted"` rows
  - [ ] Alembic migration
- [ ] Task 2: Build the rename endpoint (AC: 1)
  - [ ] Add to the same Review module (`apps/api`) as Stories 3.2/3.3's approve/reject endpoints, Organization-scoped
  - [ ] Only allowed while `status="candidate"` — consistent with the established rule that all five review actions (Approve, Reject, Rename, Edit, Delete) are undecided-row-only; a decided row has already dropped these actions entirely in the UI (Stories 3.2/3.3), so the endpoint should reject (not silently ignore) an attempt against a non-candidate row
  - [ ] Updates `Journey.name` — since this is the single source of truth already read by the Discover Journeys row (Story 3.1), no separate propagation step is needed; every future screen that displays a Journey's name (Generated Scenarios/Tests — Epic 4; any surviving Epic 6 analytics screen) must read this same field live, never cache or duplicate it, for the rename to actually satisfy "displayed everywhere it appears"
- [ ] Task 3: Build the delete endpoint (AC: 3)
  - [ ] Same module, same Organization scoping, same check-before-acting idempotency pattern as Stories 3.2/3.3 (only transitions if currently `status="candidate"`)
  - [ ] Sets `status="deleted"` — excluded from the review queue (Story 3.1's read endpoint) and from every downstream Trusted Knowledge Model / Analytics read path, alongside `rejected`
- [ ] Task 3a: Build the edit endpoint (AC: 2) `[ADDED 2026-07-15, FR-28]`
  - [ ] Same module, same Organization scoping, same check-before-acting idempotency pattern as Rename/Delete (only while `status="candidate"`)
  - [ ] **`[GAP]` the editable field set is unconfirmed** — until a follow-up UX pass resolves this, build against the smallest defensible surface (name/description, mirroring what Rename already touches) rather than guessing at a constituent-steps editor; do not build UI or persistence for editing a Journey's composing pages/actions/API calls without an explicit design for it
  - [ ] Whatever fields are edited, the change is saved and reflected everywhere the Journey/Capability is displayed, consistent with Task 2's rename-propagation approach
- [ ] Task 4: Build Rename, Edit, and Delete actions in the Discover Journeys UI (AC: 1-3)
  - [ ] Rename: triggered by the Rename action in the row's `⋯` menu; a small inline edit or lightweight input is sufficient — nothing in the UX spine specifies a modal vs. inline pattern, so don't over-build this beyond what's needed to capture a new name and save it
  - [ ] Edit: triggered by the Edit action in the row's `⋯` menu; per the `[GAP]` above, scope the editing surface to the smallest defensible field set pending a follow-up UX pass
  - [ ] Delete: triggered by the Delete action in the row's `⋯` menu; on confirmation, the row is removed from the queue list entirely — unlike approve/reject, there is no `Deleted` badge/muted-row state described anywhere in the UX spine, consistent with FR-13's "removed from the review queue" (not "shown as decided"). Don't invent a `Deleted` badge variant that isn't specified
  - [ ] Pending-count indicator (Story 3.1) decrements on delete (the item leaves the undecided set); rename and edit don't change the count
- [ ] Task 5: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] Renaming an undecided candidate updates its displayed name on the Discover Journeys row
  - [ ] Editing an undecided candidate saves the change within the confirmed field scope and reflects it everywhere the Journey/Capability is displayed
  - [ ] Attempting to rename, edit, or delete a decided (approved/rejected) or already-deleted row is rejected, not silently accepted
  - [ ] Deleting an undecided candidate removes it from the queue and from a Trusted Knowledge Model read query; it never re-appears

## Dev Notes

- **The soft-delete decision (Task 1) is worth flagging explicitly during code review** — it's a reasonable, consistent-with-the-rest-of-the-system default, but it is this story's own inference, not a literal requirement anyone wrote down. If a future story needs a genuine hard-delete (e.g. for data-retention/compliance reasons), that's a product decision to make explicitly, not something to assume already happened here.
- **Rename, Edit, and Delete follow the exact same undecided-row-only and single-writer-path discipline as Approve/Reject** (Stories 3.2/3.3) — this story doesn't introduce a new pattern, it applies the same one to the remaining three of the now-five actions. Read those stories' Dev Notes for the idempotency reasoning rather than re-deriving it here.
- **No `Deleted` badge exists anywhere in the UX spine** — resist adding one. A deleted row simply disappears from the list; this is a deliberate difference from approve/reject's mute-and-badge treatment, not an oversight to "fix" by adding parity.
- **2026-07-15 scope change (FR-28):** Edit is newly added to this story per `epics.md`, superseding the prior "four-action-only" framing (Approve/Reject/Rename/Delete) — the constraint that survives is "no merge/split/composition-edit of a Journey's constituent pages/actions/API calls" (UX-DR22, Story 3.3), not "no edit at all." The exact editable surface for the new Edit action is unconfirmed (`[GAP]`, Task 3a) — treat this as scoped-down-by-default until a follow-up UX pass resolves it. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

### Project Structure Notes

- Adds `status="deleted"` to `Journey` (`packages/domain`), adds rename/edit/delete endpoints alongside Stories 3.2/3.3's in `apps/api`'s Review module, and extends the Discover Journeys UI (Story 3.1). No new top-level directories.
- **Depends on Epic 1, Epic 2, and Stories 3.1–3.3 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4: Rename, Edit & Delete a Journey/Capability]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-12, FR-13, FR-28]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8 — soft-supersede/audit-retention pattern this story's delete design follows]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Review & Trust Model — the expanded action set (2026-07-15)]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md]
- [Source: _bmad-output/implementation-artifacts/3-2-approve-a-journey-capability.md; 3-3-reject-a-journey-capability.md — the single-writer/idempotency pattern this story reuses]

## Previous Story Intelligence

Epic 1, Epic 2, and Stories 3.1–3.3 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Stories 3.2/3.3 are implemented, check their File Lists for the exact Review module structure before adding rename/delete alongside them.

## Latest Technical Notes

No new library decisions — extends the existing FastAPI/SQLModel/React stack.

## Project Context Reference

No `project-context.md` exists yet in this repository. With all four review actions now spec'd (3.2–3.4), this is a good point to run `bmad-generate-project-context` once implemented, so Story 3.5 and Epic 4 have a real code reference.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
