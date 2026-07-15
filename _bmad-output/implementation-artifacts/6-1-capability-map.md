# Story 6.1: Capability Map

Status: backlog

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**`[DEFERRED POST-V1 — 2026-07-15]`** No supporting screen exists for the App Overview / Capability Map view in the current reference prototype's IA. Do not schedule this story for dev-story. Retained below verbatim as a record of original intent — historical spec, not a build target. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

## Story

As a QA Director or Engineering Leader,
I want a business-language map of an Application's approved Capabilities,
so that I can show what the application actually does without anyone having had to document it by hand.

## Acceptance Criteria

1. **Given** an Application with approved Capabilities, **when** the user opens App Overview, **then** every approved Capability appears as a card showing its name, a journey-count pill, a one-line description, and a nested list of its approved Journeys with a status dot and test-count in monospace. [Source: epics.md#Story 6.1; FR-22]
2. Rejected or deleted candidates never appear in this view. [Source: epics.md#Story 6.1; FR-22]

## Tasks / Subtasks

- [ ] Task 1: Build the Capability Map read endpoint (AC: 1, 2)
  - [ ] `GET` endpoint returning `Capability` rows with `status="approved"` for an Application, Organization-scoped via Story 1.2's middleware — each with its `name`, `description` (already present on `Capability` since Story 2.5), a count of its `status="approved"` Journeys (this is also the journey-count pill's number — the pill and the nested list must show the same count, not two different queries that could drift), and the nested Journeys themselves (`name`, test-count)
  - [ ] **Test-count per Journey must read `current=true` `TestAsset` rows only** (joined through the Journey's `Scenario`s) — a naive count of all historical `TestAsset` rows would over-count after any Story 4.3 regeneration, since superseded rows are retained (soft-superseded, AD-8) rather than deleted
  - [ ] This is a pure read query — no new domain writes anywhere in this story
- [ ] Task 2: Build the App Overview screen's Capability Map (AC: 1, 2)
  - [ ] 3-up card grid per `DESIGN.md`'s Layout & Spacing ("the App Overview capability grid... run[s] 3-up")
  - [ ] Each `Capability` card: name, journey-count pill, one-line description, and a nested list of approved Journeys — each nested row showing a small green status dot and a test-count rendered in `{typography.mono-inline}`
  - [ ] **Clicking a nested Journey name is explicitly not a defined interaction in V1** (`EXPERIENCE.md`'s Component Patterns: "App Overview is a presentation surface for showing an Engineering Leader, not a second review entry point") — don't wire up a click handler expecting navigation to Journey Explorer (Story 6.2) or anywhere else; this is a real, easy-to-add-by-instinct interaction that the UX spine explicitly rules out
  - [ ] Application-name breadcrumb *is* shown (App Overview is Application-scoped), consistent with the established rule
- [ ] Task 3: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] An Application with a mix of approved/rejected/still-candidate Capabilities and Journeys shows only approved Capabilities, each listing only its approved Journeys — rejected/deleted/candidate items never appear anywhere on this screen
  - [ ] Test-count updates correctly after a Story 4.3 regeneration (reflects only the new `current=true` set, not the superseded prior attempt)
  - [ ] Clicking a nested Journey name has no effect (a deliberate negative check, not just a positive functional test)

## Dev Notes

- **This is the first purely read/analytics story in the backlog** — everything it displays was already modeled by Epics 2-4 (`Capability`, `Journey`, `Scenario`, `TestAsset`). No new entities, no new writes, no workflow involvement.
- **The `current=true`-only test-count rule is the one place this story could silently produce a wrong number** — if the query joins to all `TestAsset` rows for a Journey's Scenarios without the `current=true` filter, a regenerated Journey would show an inflated count including superseded assets. Get this filter right in Task 1's query, not as an afterthought in the UI layer.
- **The "no click on nested Journey name" rule is worth taking seriously precisely because it's an obvious, natural-feeling interaction to add** — the UX spine calls this out by name as something App Overview deliberately doesn't do, distinguishing it from Journey Explorer (Story 6.2), which exists specifically to be the click-through detail view.

### Project Structure Notes

- Adds a read endpoint to `apps/api`'s Analytics module and builds the App Overview screen in `apps/web` for the first time. No new entities, no new top-level directories. This is the first story in Epic 6.
- **Depends on Epic 1-5 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. In particular, this story needs Epic 3's Capability-approval-promotion logic (Story 3.2) and Epic 4's `current` flag semantics (Stories 4.1-4.3) to be correctly built first.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 6.1: Capability Map]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-22]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8 — current flag semantics; #Components — API Service (Analytics module, read-only, no write path into packages/domain)]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — Capability cards; #Layout & Spacing — 3-up grid]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Component Patterns — Capability card, no click-through]
- [Source: _bmad-output/implementation-artifacts/3-2-approve-a-journey-capability.md — Capability-approval-promotion logic this story's filter depends on]
- [Source: _bmad-output/implementation-artifacts/4-3-full-regeneration-of-test-assets-on-request.md — `current` flag semantics this story's test-count depends on]

## Previous Story Intelligence

Epics 1-5 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Stories 3.2 and 4.1-4.3 are implemented, check their File Lists for the exact `Capability`/`Journey`/`Scenario`/`TestAsset` schemas before writing this story's read query.

## Latest Technical Notes

No new library decisions — this story is a read query and a display screen on the existing FastAPI/SQLModel/React stack.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
