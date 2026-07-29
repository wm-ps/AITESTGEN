---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.16: Blocked Mid-Exploration — Path Persistence & Resume

*Added per `sprint-change-proposal-2026-07-29.md`. `ExplorationStep` is deliberately named to avoid collision with the existing `Journey` domain entity (an AI-inferred business journey, created later by `InferenceActivity`) — see Architecture AD-20's explicit naming note. Do not rename this entity to `JourneyStep`.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want a blocked exploration path's full route from the start of the run to be remembered,
so that supplying the missing data later resumes exactly where it left off instead of losing everything already discovered along the way.

## Acceptance Criteria

1. **Given** a block occurs after N successful steps, **when** the `BlockedTask` (Story 2.15) is written, **then** all N steps are persisted as ordered `ExplorationStep` rows referencing their already-confirmed `Page` (not duplicating it), including the exact input values used at each step, verbatim. [Source: epics.md#Story 2.16; FR-43; architecture#AD-20]
2. **Given** a user supplies the missing value, **when** resume begins, **then** the value is validated first (staleness check), a new browser session starts (no assumption the old one survived), and every already-succeeded step is replayed via its stored action/inputs — except a step that already caused a known-irreversible effect, which is instead skipped in favor of navigating directly to its resulting `Page`, to avoid creating a duplicate record. [Source: FR-43; architecture#AD-21]
3. **Given** a resumed path reaches its previously-blocked step, **when** the new value/authorization is supplied, **then** the `BlockedTask` is marked Resolved and exploration continues downstream. [Source: FR-43]
4. **Given** a single exploration path, **when** it blocks a second time later in its own continuation, **then** the same `BlockedTask`/step-list record is extended, not replaced with a new, unrelated record. [Source: FR-43, worked example Section 14.4]

## Tasks / Subtasks

- [ ] Task 1: Add the `ExplorationStep` domain entity (AC: 1)
  - [ ] Add `ExplorationStep` (`id`, `blocked_task_id` FK, `step_order: int`, `page_id` FK — references the confirmed `Page`, does not duplicate its content, `action_description`, `input_values: JSONB`, `created_at`) to `packages/domain`; `UNIQUE(blocked_task_id, step_order)`
  - [ ] Alembic migration
- [ ] Task 2: Write the full step path at block time (AC: 1)
  - [ ] Extend the Planner (Story 2.11) to maintain an in-memory ordered log of every EXECUTE decision's `(page, action, resolved_input_values)` for the current exploration path, from the start of the run
  - [ ] When a DEFER occurs (Story 2.15's `BlockedTask` creation), flush this entire log as `ExplorationStep` rows referencing the `BlockedTask`, `step_order` starting at 1 — not just the step that blocked
  - [ ] Input values (including synthetic ones from Story 2.13) are stored verbatim, not "regenerate on replay"
- [ ] Task 3: Build the resume sequence (AC: 2, 3)
  - [ ] New module in `apps/workers/discovery` (e.g. `resume.py`) implementing: (a) validate the supplied value still resolves to something real (a staleness check — the exact validation mechanism is app-specific and may need a placeholder/best-effort default at implementation time, flagged as an open question per the source document's own acknowledged gap); (b) start a fresh Playwright session (never assume the blocking session survived); (c) replay each `ExplorationStep` in `step_order`, re-executing its stored action/inputs — except a step flagged (at implementation time, via a simple heuristic or an explicit marker set when the action was originally classified, e.g. a "Create"/"Submit" verb that already succeeded) as having caused an irreversible effect, which is instead skipped in favor of navigating directly to its resulting `page_id`'s URL; (d) on reaching the previously-blocked step, supply the new value/authorization and execute it; (e) mark `BlockedTask.status="resolved"`, `resolved_at=now()`, and hand control back to the Planner to continue exploring downstream
- [ ] Task 4: Support re-blocking the same path (AC: 4)
  - [ ] If the resumed path blocks again further along, extend the *same* `BlockedTask`'s `ExplorationStep` list (append new steps, `step_order` continuing from where it left off) rather than creating a new, unrelated `BlockedTask`
- [ ] Task 5: Verify end-to-end (AC: 1-4)
  - [ ] A 7-step path that blocks at step 7 (matching the source document's worked example: Home → Login → Dashboard → Shop nav → Product List → Product Details → Add to Cart → Cart → Checkout → Payment) stores all 7 preceding steps, not just the blocking one
  - [ ] Resuming with a supplied value replays steps 1-6 exactly, then attempts step 7 with the new value
  - [ ] A step that already created a real record (e.g. a synthetic order) is skipped on replay in favor of direct navigation to its resulting page — verify no duplicate record is created
  - [ ] A path that blocks twice (per the source document's Section 14.4 worked example) extends one `BlockedTask` across both blocks, never producing two unrelated records for what's really one continuing exploration path

## Dev Notes

- **The naming distinction is load-bearing, not cosmetic.** `ExplorationStep` records a crawl-time path that may or may not ever become a `Journey` — `InferenceActivity` (Story 2.6) only creates `Journey` rows from the confirmed Application Model *after* Discovery completes, entirely independent of whether any `BlockedTask`/`ExplorationStep` records exist for this Application. Naming this entity `JourneyStep` would imply a relationship to the `Journey` entity that doesn't exist and would confuse every future engineer reading the schema. See architecture AD-20.
- **Non-idempotent replay is the single highest-risk piece of this story** — Task 3's "skip a step that already succeeded irreversibly" logic cannot be fully generalized across arbitrary target applications from architecture alone (this is an explicitly acknowledged gap in both the source design document, Section 15.4, and this repo's own architecture Deferred section). Ship a reasonable default (e.g. treat "Create"/"Submit"/"Add" verb-classified actions, per Story 2.12's verb lists, as candidates for skip-and-navigate) and flag any app-specific exception handling as a follow-up, rather than blocking this story on solving the general case.
- **Staleness validation (Task 3a) has no prescribed mechanism** — the source document names the need but not the implementation; a reasonable V1 default is re-checking the supplied value's existence/validity via whatever lookup the target application's own UI would normally use (e.g. searching for it on the relevant page) before committing to a full replay. Document whatever choice is made in Completion Notes.

### Project Structure Notes

- Adds one new domain entity (`ExplorationStep`) to `packages/domain`, and a new `resume.py` module to `apps/workers/discovery`. No new top-level directories.
- Depends on Story 2.15's `BlockedTask` (this story's `ExplorationStep` rows reference it) and Story 2.11's Planner (source of the step log at block time).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.16]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Sections 15, 15.0-15.4 of the source design document (the Checkout worked example)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-20, #AD-21]
- [Source: _bmad-output/implementation-artifacts/2-15-blocked-frontier.md — the `BlockedTask` shell this story extends]

## Previous Story Intelligence

Story 2.15 (Blocked Frontier) must exist first — this story's `ExplorationStep` table has a hard FK dependency on `BlockedTask`. Build/verify 2.15 before starting this story's Task 1.

## Latest Technical Notes

No new library decisions. Resume's "start a fresh Playwright session" reuses Story 2.2's existing `establish_session` (login heuristic + SSO storage-state reuse).

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
