# Story 3.2: Approve a Journey/Capability

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer,
I want to approve a discovered Journey/Capability,
so that it enters the Trusted Knowledge Model and downstream generation can begin.

## Acceptance Criteria

1. **Given** an undecided candidate Journey/Capability, **when** the reviewer clicks Approve, **then** only `apps/api`'s review endpoint transitions its status to `approved` — no worker or other code path may perform this transition. [Source: epics.md#Story 3.2; FR-10; FR-14; architecture#AD-7]
2. In the same request, the endpoint increments the Journey's `attempt` counter and starts an independent `GenerationWorkflow` with workflow ID `generation-{journey_id}-{attempt}` — a duplicate/double-click approval is a no-op because Temporal rejects the duplicate workflow ID. [Source: epics.md#Story 3.2; architecture#AD-1; #AD-9]
3. The row immediately drops its four action buttons (not disabled — removed) and its title mutes, reflecting its new `Approved` badge. [Source: epics.md#Story 3.2; EXPERIENCE.md#State Patterns]

## Tasks / Subtasks

- [ ] Task 1: Add `Journey.attempt` (AC: 2)
  - [ ] Add `attempt` (int, default 0) to `Journey` (Story 2.5), plus an Alembic migration
- [ ] Task 2: Build the approve endpoint — the Trusted Knowledge Model's sole writer path (AC: 1, 2)
  - [ ] Add an approve endpoint to the Review module in `apps/api`, Organization-scoped via Story 1.2's middleware
  - [ ] **Idempotency has two layers, not one — implement both.** (1) DB-level check-before-acting: the status transition and `attempt` increment must only happen if the Journey's current status is `"candidate"` (e.g. `UPDATE ... WHERE status='candidate' ... RETURNING attempt`) — a second concurrent/double-click request finds `status` already `"approved"` and returns success as a pure no-op, without re-incrementing `attempt` or touching Temporal at all. (2) Temporal-level backstop: if a race somehow lets two requests both observe `status='candidate'`, both would compute the same `attempt` value and thus the same `generation-{journey_id}-{attempt}` workflow ID, so Temporal's duplicate-workflow-ID rejection is what AD-9 is actually relying on as the final guard — but layer (1) is what prevents `attempt` from being incremented twice on an ordinary double-click, which is the far more common case
  - [ ] On a real (non-no-op) transition: set `status="approved"`, increment `attempt`, and start `GenerationWorkflow` with ID `generation-{journey_id}-{attempt}` — all in the same request (AD-1, AD-9)
  - [ ] **Capability approval, resolved here per the gap flagged in Story 3.1:** if the approved Journey's `Capability` is not already `status="approved"`, set it to `approved` too. A Capability becomes approved the first time any one of its Journeys is approved — it does not require every Journey under it to be approved (App Overview, per Story 6.1's AC, shows a Capability's *nested list of approved Journeys*, implying a mix of approved/pending Journeys can coexist under an already-approved Capability)
  - [ ] AD-7 is enforced by code organization and review discipline, not a runtime check: no worker (`apps/workers/*`) may ever write `Journey.status="approved"` or `Capability.status="approved"` — only this endpoint
- [ ] Task 3: Graduate `GenerationWorkflow` from Story 1.1's no-op shell (AC: 2)
  - [ ] **This is the exact workflow the Implementation Readiness Report flagged when it confirmed this story wasn't blocked**: "a workflow shell already exists from Story 1.1 ('a trivial no-op workflow')." This story is where that shell gets its real identity — give it the `generation-{journey_id}-{attempt}` workflow-ID convention (AD-1) so Temporal's duplicate-ID rejection actually provides the idempotency AC 2 requires
  - [ ] **`GenerationWorkflow`'s real Activities (`ScenarioGenerationActivity`, `PlaywrightGenerationActivity`) are Epic 4's job, not this story's** — per the same Readiness Report note, it's fine and expected for this story to leave the workflow body as a no-op/stub once it's dispatched with the correct ID, exactly as Story 2.1 left `DiscoveryActivity` as a stub for Story 2.2 to fill in. Mark this clearly in the workflow's code (a one-line comment is enough) so whoever implements Epic 4 doesn't mistake the stub for a finished feature, and doesn't need to guess whether the workflow-ID/idempotency contract is already correct (it is, as of this story)
- [ ] Task 4: Build the Approve action in the Review Journeys UI (AC: 3)
  - [ ] Approve icon button (`{components.icon-button}`, good-wash/good hover tint per `DESIGN.md`)
  - [ ] On success, the row immediately removes all four action buttons (not disabled) and its title mutes; badge switches to `Approved` (`{colors.good-wash}`/`{colors.good}` — this is an already-documented badge variant, unlike the status-pill gaps filled in Stories 2.3/2.4, so no design gap to resolve here)
  - [ ] Nav-rail pending count decrements, reusing Story 3.1's refetch/decrement mechanism
- [ ] Task 5: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] Approving a candidate Journey sets `status=approved`, `attempt=1`, and starts `GenerationWorkflow(id="generation-{journey_id}-1")`, observable via Temporal CLI/Web UI
  - [ ] Double-clicking Approve (or firing two concurrent requests) results in exactly one `attempt` increment and exactly one `GenerationWorkflow` execution — verify this with an actual concurrency test, not just a single-request test
  - [ ] Approving a Journey under a still-candidate Capability promotes that Capability to `approved`; approving a second Journey under an already-approved Capability doesn't error or double-transition it
  - [ ] The UI correctly removes action buttons and mutes the row on approve

## Dev Notes

- **This story closes the loop the Readiness Report explicitly flagged as non-blocking but worth a heads-up about** — read that report's note on Story 3.2 before starting Task 3, since it's the authoritative source for why the `GenerationWorkflow` stub approach here is intentional, not a shortcut.
- **AD-7's single-writer rule is the most safety-critical rule in this story.** The entire product's trust pitch depends on "only a human, through this exact endpoint, can move something into the Trusted Knowledge Model" — a worker "helpfully" auto-approving anything (even for a seemingly harmless reason, like a very obvious non-duplicate) would break that guarantee. Treat any code path that writes `status="approved"` outside this endpoint as a defect regardless of how it got there.
- **The two-layer idempotency design (Task 2) is worth getting right precisely because it's easy to build only the Temporal-level backstop and skip the DB-level check** — that would still technically satisfy "double-click is a no-op" in the common case (both requests would race to read `status='candidate'`, but only the DB-level guard reliably prevents a double-increment of `attempt` under real-world request timing). Don't treat Temporal's dedup alone as sufficient.

### Project Structure Notes

- Extends `Journey`/`Capability` (`packages/domain`, Stories 2.5/3.1), extends `GenerationWorkflow` (`packages/workflows`, Story 1.1), adds the approve endpoint to `apps/api`, and extends the Review Journeys UI (Story 3.1). No new top-level directories.
- **Depends on Epic 1, Epic 2, and Story 3.1 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.2: Approve a Journey/Capability]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-10, FR-14]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-7, #AD-9]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — icon-button, badge]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#State Patterns — review queue item resolved]
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-13.md — confirms this story's `GenerationWorkflow` reference is non-blocking, backed by Story 1.1's shell]
- [Source: _bmad-output/implementation-artifacts/1-1-repository-service-scaffold.md — the `GenerationWorkflow` shell this story graduates]
- [Source: _bmad-output/implementation-artifacts/3-1-review-queue-candidate-list-evidence-panel.md — the Capability-derivation gap this story resolves]

## Previous Story Intelligence

Epic 1, Epic 2, and Story 3.1 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once implemented, check Story 1.1's File List for `GenerationWorkflow`'s exact current shape before extending it in Task 3, and Story 3.1's File List for the exact `Journey`/`Capability` schema before Task 1/2.

## Latest Technical Notes

No new library decisions — extends the existing Temporal/FastAPI/SQLModel stack.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
