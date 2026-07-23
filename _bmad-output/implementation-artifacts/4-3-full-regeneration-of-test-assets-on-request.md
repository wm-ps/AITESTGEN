# Story 4.3: Full Regeneration of Test Assets on Request

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to trigger a full regeneration of a Journey's Scenarios and Test Assets,
so that I get fresh coverage after the Journey or my understanding of it has changed.

## Acceptance Criteria

1. `[CORRECTED 2026-07-21, ALIGNED 2026-07-23, SIMPLIFIED 2026-07-23, ALIGNED AGAIN 2026-07-23]` **Given** a discovered (non-deleted) Journey with existing, `current=true` Scenarios, `TestSuite`, and Test Assets, **when** the user triggers regeneration, **then** a new `GenerationWorkflow` attempt runs `ScenarioGenerationActivity` from scratch — never as an incremental diff/patch — producing fresh `Scenario` rows with their AI-defined test-data fields blank again (Story 4.1 AC 5). **`PlaywrightGenerationActivity` does not run in the same step, and regeneration itself does not start it.** The regenerated Journey's fresh Scenarios simply wait for the next Generate Suite submission, which starts Story 4.2's own **Journey-scoped** `SuiteGenerationWorkflow` for this Journey (mirroring `GenerationWorkflow`'s own `run(journey_id)` shape) — creating this Journey's next `TestSuite` (new attempt, `current=true`, superseding the prior one) and its `TestAsset`s. Regeneration does not bypass Story 4.1's gate; whatever test data the reviewer has (re-)completed by then is used as-is, and Story 4.2's own field-level default-fill applies to a regenerated Journey's Scenarios exactly the same as any other Scenario — no special case. [Source: epics.md#Story 4.3; FR-18]
2. The new attempt's `Scenario`/`TestAsset` rows are written with `current=true`, while the prior attempt's rows flip to `current=false` (soft-superseded, retained for audit, never deleted). [Source: epics.md#Story 4.3; architecture#AD-8]
3. The regeneration Activity is idempotent under Temporal's at-least-once retry — a retried attempt does not produce duplicate current rows. [Source: epics.md#Story 4.3; architecture#AD-9]

## Tasks / Subtasks

- [ ] Task 1: Build the regenerate-trigger endpoint (AC: 1)
  - [ ] Add an endpoint to `apps/api`, Organization-scoped, allowed only for a non-`deleted` Journey (`status="candidate"` — `[UPDATED 2026-07-15]` there's no more `approved` status; a `deleted` Journey has nothing worth regenerating)
  - [ ] **This is not a status transition** — the Journey stays `candidate`; there is no Capability-promotion logic to run (Capability has no `approved` state either, see Story 2.5). `[UPDATED 2026-07-15, CORRECTED 2026-07-21]` The "increment attempt atomically + start `GenerationWorkflow(id=generation-{journey_id}-{attempt})`" logic is no longer shared with a sibling approve endpoint — Story 3.2 (Approve) is cut. **The *first* generation attempt no longer starts inside `InferenceActivity` either** — as of Story 4.1's 2026-07-21 correction, it starts via that story's Task 5 "Continue to Scenarios" endpoint in `apps/api`, same as this story's regenerate endpoint. This endpoint and Story 4.1's Task 5 endpoint are now siblings in `apps/api` (first attempt vs. Nth attempt), not one `apps/api`-endpoint-vs-one-worker-Activity split as this note previously said — implement following the same atomic-increment pattern Story 4.1's Task 5 establishes for consistency, rather than inventing a second convention
  - [ ] Use a single atomic `UPDATE Journey SET attempt = attempt + 1 ... RETURNING attempt` so two near-simultaneous regenerate clicks each get a distinct `attempt` value (and thus a distinct, non-colliding workflow ID) rather than both computing the same next value from a stale read
- [ ] Task 2: Extend `ScenarioGenerationActivity` and `PlaywrightGenerationActivity` for full regeneration with atomic supersede (AC: 1, 2, 3)
  - [ ] `[CORRECTED 2026-07-21, ALIGNED 2026-07-23 twice]` Both Activities generate fresh output "from scratch" for their attempt — **never** read, diff, or patch the prior attempt's `Scenario`/`TestSuite`/`TestAsset` content — but they are **not fired together by the regenerate trigger**, and are not even fired by the *same kind* of trigger. `ScenarioGenerationActivity` runs when regeneration is triggered (Task 1), via `GenerationWorkflow`. `PlaywrightGenerationActivity` has **no trigger of its own tied to the regenerate action** — it runs later, via Story 4.2's own **Journey-scoped** `SuiteGenerationWorkflow` (mirrors `GenerationWorkflow`'s `run(journey_id)` shape exactly), started when the Generate Suite screen is next submitted (which fans out one `SuiteGenerationWorkflow` per candidate Journey with current Scenarios) — using the reviewer's test data where completed, and Story 4.2's own per-field default-fill for anything still blank. There is no manual-editing path for Scenarios (consistent with UX-DR23, Story 4.1) and no incremental-regeneration path anywhere in this system; FR-18 is explicit that this is full regeneration only — "full regeneration only" describes the *content* (never a diff/patch), not the *timing* (the two Activities were never required to fire in the same instant, and don't share a trigger mechanism at all)
  - [ ] `[CORRECTED 2026-07-21, ALIGNED 2026-07-23]` **The new-rows-current / old-rows-superseded flip must happen atomically, in the same transaction as the new rows' creation — but this now happens across three entities, at two different times, not one bundled step.** When `ScenarioGenerationActivity` runs (at regenerate-trigger time): write the new attempt's `Scenario` rows as `current=true` and flip the immediately-prior `current=true` `Scenario` rows for the same `journey_id` to `current=false`, in one commit. Later, when Story 4.2's `SuiteGenerationWorkflow` runs for this Journey (at Generate-Suite-submission time, once test data is re-completed): its `EnsureTestSuiteActivity` writes the new attempt's `TestSuite` row as `current=true` and flips the prior `current=true` `TestSuite` for the same `journey_id` to `current=false`, in one commit — then each `PlaywrightGenerationActivity` call writes its `TestAsset` (linked to that new `TestSuite`) as `current=true`, with the prior attempt's corresponding `TestAsset` flipped to `current=false` in the same write. `[DECIDED 2026-07-23, Story 4.2 Task 1]` `TestAsset` has no `generation_run_id` field of its own (derived via `test_suite_id` → `TestSuite.generation_run_id` instead) — so "the prior attempt's `TestAsset`" is identified simply as **every `TestAsset` whose `test_suite_id` is the just-superseded old `TestSuite`'s id**, not by matching a `generation_run_id` value. This is actually simpler than matching on a value: the old `TestSuite`'s id is already known the instant `EnsureTestSuiteActivity` supersedes it. Doing any of these halves as two separate steps (write new, *then* supersede old — or the reverse) would create a window where either zero or two `current=true` rows exist simultaneously for that entity, which would corrupt whatever the Journey Explorer / coverage analytics (Epic 6) reads in that window
  - [ ] `[UPDATED 2026-07-23 twice]` **AD-9 idempotency, concretely for this story:** before writing, each Activity checks whether its own row already exists — three different shapes now, one per entity. `ScenarioGenerationActivity` checks the exact `(journey_id, generation_run_id)` pair it's about to write. `EnsureTestSuiteActivity` (Story 4.2) does an idempotent insert-or-fetch of the `TestSuite` for `(journey_id, generation_run_id)`, backed by a unique constraint — on a conflict (concurrent race), it re-queries and uses the row the other call created. `PlaywrightGenerationActivity` checks whether the `scenario_id` it was given already has a `current=true` TestAsset. If Temporal retries the same Activity execution (worker crash, transient failure) within the same attempt/dispatch, any of these retries finds its own prior work already done and returns without re-writing or re-superseding — this is the specific mechanism that satisfies AC 3, distinct from (and more central to this story than) Task 1's endpoint-level double-click protection for `ScenarioGenerationActivity`, or Story 4.2's own endpoint-level per-Journey skip for `SuiteGenerationWorkflow`. This check is already naturally per-Activity, so the AC 1 correction (independently-triggered mechanisms instead of one bundled step) doesn't change how this works, only when each half runs
- [ ] Task 3: Build the "Regenerate" trigger control in the UI (AC: 1)
  - [ ] **Neither the epics document, the UX spine's Component Patterns, nor its Key Flows describe a specific screen placement for a regenerate control — this is a real gap in the source documents, not an oversight in this story's research.** Resolved here: place it as a secondary action on the Generate Suite screen (Story 4.2 — `[UPDATED 2026-07-15]` renamed from "Generated Tests," the standalone code-review screen this note originally cited), since that's the concrete artifact being regenerated and where a user would naturally be looking at what currently exists before deciding to refresh it.
  - [ ] Use the exact confirmation copy `EXPERIENCE.md`'s Voice and Tone table gives as a calibration example for this specific action: **"Regenerates from scratch — not a diff/patch."** — this is a literal citation, not a filled gap, since the source document uses this exact scenario as its own Do example
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] `[CORRECTED 2026-07-21]` Triggering regeneration on a discovered Journey with existing coverage creates a new `attempt`, a new `GenerationWorkflow` execution, and new `Scenario` rows with `current=true` (blank `test_data` again) — **`TestAsset` rows are not created yet at this point**
  - [ ] The prior attempt's `Scenario` rows flip to `current=false` in the same transaction as the new Scenario rows' creation — verify there is no queryable moment with zero or duplicate `current=true` Scenario rows for the Journey
  - [ ] `[ALIGNED 2026-07-23 twice]` Verify that the next Generate Suite submission (Story 4.1 AC 6's button, the one existing trigger — fanning out one `SuiteGenerationWorkflow` per candidate Journey) starts a fresh `SuiteGenerationWorkflow` for this regenerated Journey, which creates a new `TestSuite` row (`current=true`, flipping the prior attempt's `TestSuite` for this Journey to `current=false`) and new `TestAsset` rows for each of the Journey's Scenarios (`current=true`, flipping the prior attempt's `TestAsset` rows to `current=false`) — whether the reviewer fully re-completed the new attempt's test data or left some fields blank (Story 4.2's own per-field default-fill covers those). Verify both supersedes (`TestSuite` and `TestAsset`) are each atomic with their own rows' creation.
  - [ ] Simulating an Activity retry (e.g. forcing a worker restart mid-Activity in a test) for the same `generation_run_id`/`scenario_id` does not produce duplicate `current=true` rows, for either Activity
  - [ ] Superseded rows are retained in the database (soft-superseded), never deleted

## Dev Notes

- **The missing UI-placement spec (Task 3) is worth flagging to the user/product as a real gap, not just resolving silently** — it's the kind of thing worth a quick confirmation once a working prototype exists, since "Generate Suite screen" was a reasoned default, not a documented requirement.
- **Distinguish the two idempotency concerns in this story clearly**: Task 1's atomic `attempt` increment prevents two *distinct* user clicks from colliding (each real click should legitimately produce a new attempt — that's the feature); Task 2's AD-9 check-before-acting prevents a single *Temporal-level retry* of the same attempt from duplicating its own effects. Conflating these two into one mechanism would likely under-protect one of them.
- **This story is the payoff of every `generation_run_id`/`current` design decision made in Stories 4.1 and 4.2** — if those stories' `current` flag or `generation_run_id` semantics were implemented inconsistently, this is where it would surface as a real bug (e.g., superseding the wrong rows, or two "current" Test Assets existing at once). Read both stories' Dev Notes before writing Task 2's transaction logic.
- **`[ADDED 2026-07-21]` Regeneration goes through the same two-step, test-data-completion-gated flow as first-time generation — it doesn't get a shortcut.** A regenerated Journey's Scenarios start with blank `test_data` again (Story 4.1 AC 5), and `PlaywrightGenerationActivity` for the new attempt waits for the reviewer to re-complete and validate them (Story 4.1 AC 6) exactly like the first attempt did. Don't build this story's regeneration path as "both Activities together, automatically" — that was true before Story 4.1's 2026-07-21 test-data-gate correction, and this story's original AC 1/Task 2 wording (now corrected) reflected that older assumption.
- **`[CORRECTED 2026-07-21]` Task 1's "first attempt starts inside `InferenceActivity`" framing is now stale** — Story 4.1's 2026-07-21 correction moved the first attempt's trigger to an `apps/api` endpoint (its Task 5, fired by "Continue to Scenarios"), matching this story's own regenerate endpoint far more closely than the old framing suggested. Reuse Story 4.1's Task 5 endpoint's atomic-increment pattern here rather than treating that story's trigger as a worker-side concern.
- `[ALIGNED 2026-07-23, SIMPLIFIED 2026-07-23]` **The note directly above (2026-07-21, "doesn't get a shortcut") still describes the real trigger, Story 4.1 AC 6's button — Story 4.2 added no second trigger.** `PlaywrightGenerationActivity` itself resolves any still-blank `test_data` field with a computed default rather than assuming every field is already filled in — a per-field fallback inside the one existing flow, not a second path around the gate. A regenerated Journey's fresh Scenarios are not a special case: they go through the same single trigger and the same per-field resolution (reviewer value if present, default if not) as any other Scenario. "Both Activities together, automatically" still remains wrong regardless. See Story 4.2's own Dev Notes for the full detail — not re-litigated here, this story only needed its wording aligned to match.
- `[ALIGNED 2026-07-23 twice]` **`PlaywrightGenerationActivity`'s own signature (Story 4.2 Task 3) still doesn't take a Journey argument directly** — just `scenario_id` and `test_suite_id`. But Journey-scoping hasn't disappeared from the story: it now lives one level up, in `SuiteGenerationWorkflow.run(journey_id)` and in `TestSuite.journey_id` itself (Story 4.2's `TestSuite` entity, added after an earlier same-day pass had modeled this as a flat, Application-wide dispatch with no Journey concept at the workflow level at all). This story's own supersede logic (Task 2) for `TestSuite`/`TestAsset` rows works correctly either way: the Scenario being converted already carries its own `journey_id` field, and `TestSuite.journey_id` now carries it explicitly too — both identify which prior `TestSuite`/`TestAsset` (belonging to the same Journey's previous-attempt Scenario) needs to flip `current=false`. Nothing about this story's supersede transaction needed to change in substance; only Task 2's AC 1 framing and idempotency-check wording did, twice now, as Story 4.2's own model moved from Journey-scoped → Application-wide → Journey-scoped-with-`TestSuite` again.
- `[DECIDED 2026-07-23, Story 4.2 Task 1]` **`TestAsset.generation_run_id` doesn't exist as a stored field** — only `TestSuite.generation_run_id` does, and `TestAsset` derives it via `test_suite_id`. This story's Task 2 supersede logic was written to not depend on it either way (identifying the prior `TestAsset` set via the old `test_suite_id`, not via a `generation_run_id` value match) — see Task 2's matching note.

### Project Structure Notes

- Extends `apps/api` (new, standalone regenerate endpoint — `[UPDATED 2026-07-15]` no sibling approve endpoint exists to share code with; Story 3.2 is cut), and `ScenarioGenerationActivity`/`PlaywrightGenerationActivity` (`apps/workers/generation`, Stories 4.1/4.2). Adds a UI control to the Generate Suite screen (Story 4.2). No new entities, no new top-level directories. This is the last story in Epic 4.
- **Depends on Epic 1, Epic 2 (Story 2.5), Epic 3's curation stories (3.1, 3.4 — Story 3.5 cut in full 2026-07-21), and Stories 4.1–4.2 being actually implemented**, not just created — Story 4.1 is now implemented (`review`); Story 4.2 and Epics 1-3 remain `ready-for-dev`/in-progress as of this pass.
- `[ALIGNED 2026-07-23 twice]` This story's own file is untouched in scope otherwise — Story 4.2's `TestSuite` entity, its now-Journey-scoped `SuiteGenerationWorkflow`/`EnsureTestSuiteActivity`, and its per-field default-fill are all Story 4.2-owned; this story only had its AC 1/Task 2/Task 4/Dev Notes wording aligned to match, no new code surface added here.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3: Full Regeneration of Test Assets on Request]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-18]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-8, #AD-9]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Voice and Tone — "Regenerates from scratch — not a diff/patch."]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — historical context only; the atomic-increment/workflow-start pattern this story's endpoint mirrors, `[STALE as of 2026-07-21]` no longer lives inside `InferenceActivity` — see Story 4.1's Task 5 instead]
- (Story 3.2 "Approve" — removed 2026-07-15; previously the sibling endpoint this story's logic was extracted alongside)
- [Source: _bmad-output/implementation-artifacts/4-1-generate-scenarios-for-an-approved-journey.md; 4-2-generate-playwright-test-assets-from-scenarios.md — `generation_run_id`/`current` semantics this story's supersede logic depends on, and (2026-07-21) the two-step generation-trigger pattern (Task 5's "Continue to Scenarios" endpoint / Generate Suite submission) this story's endpoint now mirrors. `[ALIGNED 2026-07-23 twice]` Story 4.2's `TestSuite` entity and its Journey-scoped `SuiteGenerationWorkflow`/`EnsureTestSuiteActivity`/per-field default-fill (all in its Task 1/3) are what this story's AC 1/Task 2/Task 4 wording was aligned to — read those tasks before touching this story's Task 2 transaction logic.]

## Previous Story Intelligence

Epic 1, Epic 2 (Story 2.5), Epic 3, and Stories 4.1–4.2 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 2.5, 4.1, and 4.2 are implemented, check their File Lists for the exact shape of `Journey.attempt`, `Scenario`, and `TestAsset` before building this story's endpoint and supersede transaction.

## Latest Technical Notes

No new library decisions — extends the existing Temporal/FastAPI/SQLModel stack and the `litellm`-backed `HostedAIProvider`.

## Project Context Reference

No `project-context.md` exists yet in this repository. Epic 4 is now fully spec'd (the last in-scope epic — Epics 5-7 were removed in full 2026-07-15, see `sprint-change-proposal-2026-07-15.md`) — a strong point to run `bmad-generate-project-context` once Epics 1-4 are implemented.

## Change Log

- 2026-07-21 — `[CORRECTED]` AC 1, Task 1, Task 2, Task 4, Dev Notes, and
  References: regeneration no longer fires `ScenarioGenerationActivity` and
  `PlaywrightGenerationActivity` together in one step. Story 4.1 added a
  test-data completion gate (2026-07-21) that a bundled "both from scratch"
  regeneration would bypass. Corrected: regeneration triggers a fresh
  `ScenarioGenerationActivity` attempt only (new blank `test_data`);
  `PlaywrightGenerationActivity` for that attempt runs later, once the
  reviewer re-completes test data and the `"Continue to Generate Test
  Suite"` gate is satisfied again — same flow as first-time generation, no
  shortcut. Also corrected a now-stale reference to the first attempt
  starting inside `InferenceActivity` (Story 4.1's 2026-07-21 correction
  moved that to an `apps/api` endpoint, which this story's endpoint now
  more directly mirrors). No other part of this story changed; it remains
  `ready-for-dev`, unimplemented.
- 2026-07-23 — `[ALIGNED]` Story 4.2 added a second, ungated Generate Suite
  entry point (its AC 3/Task 4b) plus a delta-based, Application-wide
  `SuiteGenerationWorkflow` dispatch (its Task 3) — this story's AC 1, Task
  2, Task 4, and Dev Notes described `PlaywrightGenerationActivity` in
  purely Journey-scoped, single-attempt terms that no longer match. Aligned
  (no behavior change to this story's own supersede/idempotency logic): a
  regenerated Journey's fresh Scenarios have no per-Journey Playwright
  trigger of their own — they simply become new members of Story 4.2's
  existing Application-wide delta (Scenarios lacking a `current=true`
  TestAsset), picked up the next time Generate Suite is submitted via either
  of 4.2's two entry points. Task 2's idempotency-check bullet corrected to
  match `PlaywrightGenerationActivity`'s actual signature (`scenario_id`
  only, no `journey_id`, per Story 4.2 Task 3) — the two Activities' checks
  are shaped differently, not identical as previously implied. This story's
  own `TestAsset` supersede-transaction logic (Task 2) is unaffected — it
  already worked via the Scenario's own `journey_id` field, not a separate
  Journey lookup, which remains correct under Story 4.2's model. Story 4.1
  was not touched or referenced as needing changes, per explicit instruction.
  Remains `ready-for-dev`, unimplemented.
- 2026-07-23 — `[SIMPLIFIED]` Story 4.2's two-entry-point design (its AC 3,
  Task 3a, Task 4b from the pass directly above) was reverted per explicit
  follow-up direction, back to Story 4.2's original single trigger (Story
  4.1 AC 6's button) with default-value resolution folded directly into its
  `PlaywrightGenerationActivity` (Task 3) instead of a separate ungated path.
  This story's AC 1, Task 2, Task 3, Task 4, and Dev Notes updated to drop
  every "gated path vs. ungated path" reference accordingly — a regenerated
  Journey's fresh Scenarios go through the same one trigger and the same
  per-field resolution (reviewer value if present, computed default if not)
  as any other Scenario, no special case. No change to this story's own
  supersede/idempotency transaction logic — only wording. Story 4.1 was not
  touched. Remains `ready-for-dev`, unimplemented.
- 2026-07-23 — `[ALIGNED]` Story 4.2 was rearchitected again, by explicit
  clarification: a "test suite" is a real, per-Journey collection of test
  cases (Scenarios) — the end goal is one Test Suite per Journey, not one
  flat Application-wide batch. Story 4.2 added a real `TestSuite` domain
  entity and reverted `SuiteGenerationWorkflow` to Journey-scoped
  (`run(journey_id)`, mirroring `GenerationWorkflow` exactly, with a new
  `EnsureTestSuiteActivity` idempotent insert-or-fetch step). This story's
  AC 1, Task 2 (all three bullets), Task 4's verify bullet, and Dev Notes
  updated to match: regeneration's supersede transaction now covers three
  entities (`Scenario`, `TestSuite`, `TestAsset`) instead of two, each with
  its own idempotency check (`(journey_id, generation_run_id)` for
  `ScenarioGenerationActivity`; unique-constraint insert-or-fetch for
  `EnsureTestSuiteActivity`; `scenario_id`-has-a-current-TestAsset for
  `PlaywrightGenerationActivity`). No change to this story's own
  regenerate-trigger endpoint or its atomic-`attempt`-increment logic (Task
  1) — those were never Application-wide and needed no realignment. Story
  4.1 was not touched. Remains `ready-for-dev`, unimplemented.
- 2026-07-23 — `[DECIDED]` Story 4.2 decided `TestAsset` does not get its own
  `generation_run_id` field — it's derived via `test_suite_id` →
  `TestSuite.generation_run_id` instead (see Story 4.2's own Change Log for
  the full reasoning). Task 2's supersede-transaction bullet updated to
  state explicitly how "the prior attempt's `TestAsset`" is identified
  without that field: via the just-superseded old `TestSuite`'s id, not a
  `generation_run_id` value match — actually simpler than the original
  wording implied. No behavior change to this story's own transaction logic,
  only a precise statement of a mechanism that was previously left implicit.
  Also confirmed (not a new finding, just verified on request): this
  story's own live AC 1/Task 2/Task 4/Dev Notes were already fully aligned
  to Story 4.2's Journey-scoped `SuiteGenerationWorkflow`/`TestSuite` model
  as of the prior same-day pass — only this entry's `generation_run_id` point
  needed a further fix. Story 4.1 was not touched. Remains `ready-for-dev`,
  unimplemented.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
