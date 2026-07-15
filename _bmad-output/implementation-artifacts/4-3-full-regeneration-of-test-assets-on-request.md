# Story 4.3: Full Regeneration of Test Assets on Request

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to trigger a full regeneration of a Journey's Scenarios and Test Assets,
so that I get fresh coverage after the Journey or my understanding of it has changed.

## Acceptance Criteria

1. **Given** an approved Journey with existing, `current=true` Scenarios and Test Assets, **when** the user triggers regeneration, **then** a new `GenerationWorkflow` attempt runs `ScenarioGenerationActivity` and `PlaywrightGenerationActivity` from scratch — never as an incremental diff/patch. [Source: epics.md#Story 4.3; FR-18]
2. The new attempt's `Scenario`/`TestAsset` rows are written with `current=true`, while the prior attempt's rows flip to `current=false` (soft-superseded, retained for audit, never deleted). [Source: epics.md#Story 4.3; architecture#AD-8]
3. The regeneration Activity is idempotent under Temporal's at-least-once retry — a retried attempt does not produce duplicate current rows. [Source: epics.md#Story 4.3; architecture#AD-9]

## Tasks / Subtasks

- [ ] Task 1: Build the regenerate-trigger endpoint (AC: 1)
  - [ ] Add an endpoint to `apps/api`, Organization-scoped, allowed only for a Journey with `status="approved"` (a candidate/rejected/deleted Journey has nothing to regenerate)
  - [ ] **This is not a status transition** — unlike Story 3.2's approve endpoint, the Journey stays `approved`; there is no Capability-promotion logic to run again. Extract the shared "increment attempt atomically + start `GenerationWorkflow(id=generation-{journey_id}-{attempt})`" logic from Story 3.2's approve endpoint into something both endpoints call, rather than duplicating it
  - [ ] Use a single atomic `UPDATE Journey SET attempt = attempt + 1 ... RETURNING attempt` so two near-simultaneous regenerate clicks each get a distinct `attempt` value (and thus a distinct, non-colliding workflow ID) rather than both computing the same next value from a stale read
- [ ] Task 2: Extend `ScenarioGenerationActivity` and `PlaywrightGenerationActivity` for full regeneration with atomic supersede (AC: 1, 2, 3)
  - [ ] Both Activities generate fresh output "from scratch" on every attempt — **never** read, diff, or patch the prior attempt's `Scenario`/`TestAsset` content. There is no manual-editing path for Scenarios (consistent with UX-DR23, Story 4.1) and no incremental-regeneration path anywhere in this system; FR-18 is explicit that this is full regeneration only
  - [ ] **The new-rows-current / old-rows-superseded flip must happen atomically, in the same transaction as the new rows' creation** — write the new attempt's `Scenario`/`TestAsset` rows as `current=true` and flip the immediately-prior `current=true` rows for the same `journey_id` to `current=false` in one commit. Doing this as two separate steps (write new, *then* supersede old — or the reverse) would create a window where either zero or two `current=true` sets exist simultaneously, which would corrupt whatever the Journey Explorer / coverage analytics (Epic 6) reads in that window
  - [ ] **AD-9 idempotency, concretely for this story:** before writing, each Activity checks whether rows already exist for the exact `(journey_id, generation_run_id)` pair it's about to write. If Temporal retries the same Activity execution (worker crash, transient failure) within the same attempt, the retry finds its own prior work already done and returns without re-writing or re-superseding — this is the specific mechanism that satisfies AC 3, distinct from (and more central to this story than) Task 1's endpoint-level double-click protection
- [ ] Task 3: Build the "Regenerate" trigger control in the UI (AC: 1)
  - [ ] **Neither the epics document, the UX spine's Component Patterns, nor its Key Flows describe a specific screen placement for a regenerate control — this is a real gap in the source documents, not an oversight in this story's research.** Resolved here: place it as a secondary action on the Generated Tests screen (Story 4.2), since that's the concrete artifact being regenerated and where a user would naturally be looking at what currently exists before deciding to refresh it
  - [ ] Use the exact confirmation copy `EXPERIENCE.md`'s Voice and Tone table gives as a calibration example for this specific action: **"Regenerates from scratch — not a diff/patch."** — this is a literal citation, not a filled gap, since the source document uses this exact scenario as its own Do example
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] Triggering regeneration on an approved Journey with existing coverage creates a new `attempt`, a new `GenerationWorkflow` execution, and new `Scenario`/`TestAsset` rows with `current=true`
  - [ ] The prior attempt's `Scenario`/`TestAsset` rows flip to `current=false` in the same transaction as the new rows' creation — verify there is no queryable moment with zero or duplicate `current=true` rows for the Journey
  - [ ] Simulating an Activity retry (e.g. forcing a worker restart mid-Activity in a test) for the same `generation_run_id` does not produce duplicate `current=true` rows
  - [ ] Superseded rows are retained in the database (soft-superseded), never deleted

## Dev Notes

- **The missing UI-placement spec (Task 3) is worth flagging to the user/product as a real gap, not just resolving silently** — it's the kind of thing worth a quick confirmation once a working prototype exists, since "Generated Tests screen" was a reasoned default, not a documented requirement.
- **Distinguish the two idempotency concerns in this story clearly**: Task 1's atomic `attempt` increment prevents two *distinct* user clicks from colliding (each real click should legitimately produce a new attempt — that's the feature); Task 2's AD-9 check-before-acting prevents a single *Temporal-level retry* of the same attempt from duplicating its own effects. Conflating these two into one mechanism would likely under-protect one of them.
- **This story is the payoff of every `generation_run_id`/`current` design decision made in Stories 4.1 and 4.2** — if those stories' `current` flag or `generation_run_id` semantics were implemented inconsistently, this is where it would surface as a real bug (e.g., superseding the wrong rows, or two "current" Test Assets existing at once). Read both stories' Dev Notes before writing Task 2's transaction logic.

### Project Structure Notes

- Extends `apps/api` (new regenerate endpoint, sharing logic with Story 3.2's approve endpoint), and `ScenarioGenerationActivity`/`PlaywrightGenerationActivity` (`apps/workers/generation`, Stories 4.1/4.2). Adds a UI control to the Generated Tests screen (Story 4.2). No new entities, no new top-level directories. This is the last story in Epic 4.
- **Depends on Epic 1, Epic 2, Epic 3, and Stories 4.1–4.2 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3: Full Regeneration of Test Assets on Request]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-18]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8, #AD-9]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Voice and Tone — "Regenerates from scratch — not a diff/patch."]
- [Source: _bmad-output/implementation-artifacts/3-2-approve-a-journey-capability.md — the atomic-increment/workflow-start pattern this story's endpoint reuses]
- [Source: _bmad-output/implementation-artifacts/4-1-generate-scenarios-for-an-approved-journey.md; 4-2-generate-playwright-test-assets-from-scenarios.md — `generation_run_id`/`current` semantics this story's supersede logic depends on]

## Previous Story Intelligence

Epics 1-3 and Stories 4.1–4.2 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Stories 3.2, 4.1, and 4.2 are implemented, check their File Lists for the exact shape of the approve endpoint, `Scenario`, and `TestAsset` before building this story's shared logic and supersede transaction.

## Latest Technical Notes

No new library decisions — extends the existing Temporal/FastAPI/SQLModel stack and the `litellm`-backed `HostedAIProvider`.

## Project Context Reference

No `project-context.md` exists yet in this repository. Epic 4 is now fully spec'd — a strong point to run `bmad-generate-project-context` once Epics 1-4 are implemented, before starting Epic 5.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
