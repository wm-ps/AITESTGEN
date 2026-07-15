# Story 3.3: Reject a Journey/Capability

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a reviewer,
I want to reject a discovered Journey/Capability — including a duplicate flagged by the platform,
so that redundant or invalid candidates never enter the Trusted Knowledge Model.

## Acceptance Criteria

1. **Given** an undecided candidate Journey/Capability, including one carrying a `Dupe` badge, **when** the reviewer clicks Reject, **then** its status transitions to `rejected` via the same single review-endpoint writer path, and it is excluded from the Trusted Knowledge Model. [Source: epics.md#Story 3.3; FR-11; architecture#AD-7]
2. No merge or split action is offered anywhere in this flow — rejecting or editing (FR-28) are both valid resolutions for a duplicate, but a duplicate is never resolved by combining it with another Journey. [Source: epics.md#Story 3.3; UX-DR22]

## Tasks / Subtasks

- [ ] Task 1: Build the reject endpoint (AC: 1)
  - [ ] Add a reject endpoint to the same Review module in `apps/api` as Story 3.2's approve endpoint (AD-7's single-writer path), Organization-scoped
  - [ ] Same check-before-acting pattern as approve: only transition if current `status="candidate"` (e.g. `UPDATE ... WHERE status='candidate'`) — a duplicate/stale click is a no-op rather than an error
  - [ ] **This is deliberately simpler than Story 3.2's approve endpoint** — there is no `attempt` counter, no `GenerationWorkflow` to start, and no Capability-promotion side effect. Reject is a pure status write; resist the temptation to mirror approve's structure more heavily than the actual requirement needs
  - [ ] A rejected Journey never affects its Capability's approval state either way — Capability only ever gets promoted to `approved` by Story 3.2's logic (first approved Journey); there is nothing to "revert" here if every Journey under a Capability ends up rejected, it simply never gets promoted
  - [ ] Applies to Journey rows only, consistent with Story 3.1/3.2's resolution that Capability isn't independently reviewed via its own queue row — a user rejects Journeys, not Capabilities directly
- [ ] Task 2: Build the Reject action in the Review Journeys UI (AC: 1, 2)
  - [ ] Reject icon button (`{components.icon-button}`, danger-wash/danger hover tint per `DESIGN.md`)
  - [ ] Works identically for a `Dupe`-badged row as for any other undecided row — **no merge/split affordance is ever offered next to Reject, for a duplicate or otherwise.** This is one of the two hard, repeatedly-reaffirmed product constraints in this system (`EXPERIENCE.md`'s Inspiration & Anti-patterns section names this exact temptation explicitly: the approved brief originally described a reviewer who "merges duplicates," and that capability was deliberately cut for V1 — a duplicate is resolved by rejecting or editing it (FR-28), never by combining it into the Journey it overlaps)
  - [ ] On success: row removes all four action buttons, title mutes, badge switches to `Rejected` (`{colors.danger-wash}`/`{colors.danger}` — an already-documented badge variant)
  - [ ] Nav-rail pending count decrements, reusing Story 3.1's mechanism
- [ ] Task 3: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Rejecting a candidate Journey (including a `Dupe`-badged one) sets `status=rejected`, excluding it from any Trusted Knowledge Model read path (Analytics, Scenario Generation)
  - [ ] A duplicate/stale reject click is a no-op, not an error
  - [ ] The UI never renders a merge/combine control anywhere on a `Dupe`-badged row — a deliberate negative check worth including in review, not just a positive functional test

## Dev Notes

- **This story is intentionally the simplest of the four review actions** — no workflow, no counters, no derived side effects on Capability. If an implementation of this story ends up structurally as complex as Story 3.2's approve endpoint, that's a sign of over-building, not thoroughness.
- **The "no merge" constraint is worth taking as seriously as it's stated in the source docs** — it isn't a minor UI detail, it's a deliberate, named product cut from the original brief, explicitly called out as a "recurring temptation" to resist. The `Dupe` badge exists specifically so a reviewer recognizes *which* Journey to compare against before rejecting the redundant one — not as an invitation to combine them.
- **Reuses Story 3.2's single-writer endpoint pattern and DB-level idempotency guard** — read that story's Dev Notes for the reasoning before implementing this one, rather than re-deriving the same design independently.

### Project Structure Notes

- Adds a reject endpoint alongside Story 3.2's approve endpoint in `apps/api`'s Review module, and extends the Review Journeys UI (Story 3.1). No new entities, no new top-level directories.
- **Depends on Epic 1, Epic 2, and Stories 3.1–3.2 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3: Reject a Journey/Capability]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-11; §4.4 FR-13 [NON-GOAL for MVP]]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-7]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — icon-button, badge]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Review & Trust Model; #Inspiration & Anti-patterns — "Rejected — merge/split Journey actions"]
- [Source: _bmad-output/implementation-artifacts/3-2-approve-a-journey-capability.md — the single-writer endpoint pattern and idempotency guard this story reuses]

## Previous Story Intelligence

Epic 1, Epic 2, and Stories 3.1–3.2 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 3.2 is implemented, check its File List for the exact shape of the Review module's approve endpoint before adding reject alongside it — they should share structure (same Organization-scoping, same check-before-acting pattern) without literally duplicating code where a shared helper makes sense.

## Latest Technical Notes

No new library decisions — this story only extends `apps/api`'s existing Review module and the Review Journeys UI.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
