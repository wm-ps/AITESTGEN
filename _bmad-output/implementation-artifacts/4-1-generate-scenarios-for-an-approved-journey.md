# Story 4.1: Generate Scenarios for a Discovered Journey

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 (twice, same day) — Scenarios are no longer view-only; adds FR-29 (rename/edit/remove). Later the same day: renamed from "...for an Approved Journey" — Approve/Reject (Stories 3.2/3.3) are cut; generation now starts immediately on discovery, via Story 2.5's `InferenceActivity`, not on approval. See `sprint-change-proposal-2026-07-15.md`.*

## Story

As a user,
I want a discovered Journey to automatically get integration test Scenarios covering both happy-path and negative cases,
so that the map becomes actionable test coverage, not just documentation.

## Acceptance Criteria

1. **Given** a Journey for which `InferenceActivity` started a `GenerationWorkflow` at creation (Story 2.5, Task 5), **when** `ScenarioGenerationActivity` runs, calling the AI provider only through the `AIProvider` port, **then** `Scenario` rows are created for the Journey, covering both happy-path and negative/edge-case scenarios. [Source: epics.md#Story 4.1; FR-16]
2. The Review Scenarios screen lists them with `Happy Path`/`Negative Path`/`Edge Case` badges (renamed from `type-happy`/`type-negative`), each with a `⋯` menu offering rename/edit/remove. [Source: epics.md#Story 4.1; FR-29]
3. Selecting a scenario shows its Test steps, a Test data table, and Expected result in a detail panel. [Source: epics.md#Story 4.1]

**`[GAP — flagged 2026-07-15]`** Whether an edited Scenario's Test data/steps actually feed Playwright generation, or the edit is display-only, is unconfirmed — flag for engineering before implementing the edit action's persistence behavior. [Source: epics.md#Story 4.1]

*(Superseded 2026-07-15 — retained for history: the prior AC required Scenarios be strictly view-only with no checkbox/action button on any row (UX-DR23). This rule no longer holds — see FR-29 and `EXPERIENCE.md#Review & Trust Model`.)*

## Tasks / Subtasks

- [ ] Task 1: Add the `Scenario` domain entity (AC: 1)
  - [ ] Add `Scenario` (`journey_id` FK, `type` [`"happy" | "negative"`], description/content, `generation_run_id`, `current: bool` default `true`) to `packages/domain`, following the UUIDv7/UUIDv4 id convention
  - [ ] `generation_run_id` stores the `attempt` value the `GenerationWorkflow` run belongs to (matching the `generation-{journey_id}-{attempt}` workflow-ID convention, `attempt` added by Story 2.5) — this is a design choice, not an explicit schema given anywhere, chosen so the workflow ID can always be reconstructed from `journey_id` + `generation_run_id` for tracing
  - [ ] Alembic migration
- [ ] Task 2: Extend `HostedAIProvider` with `generate_scenarios` (AC: 1)
  - [ ] Implement `generate_scenarios(journey: Journey, pages: list[Page]) -> list[Scenario]` per the exact signature in the Architecture Spine's Module Contracts, using the same `litellm`-backed client established in Story 2.5 — no new vendor SDK, no code outside `packages/ai_provider` calling it directly (AD-3). **`[CORRECTED 2026-07-19]`** the generic `Evidence` table this task originally named was removed 2026-07-18 (Sprint Change Proposal) — there is no `Evidence` to pass; the real input is canonical `Page` rows (Story 2.5's Application Model), the same shape Story 2.6's `InferenceActivity`/`HostedAIProvider.infer_journeys` already reads.
- [ ] Task 3: Build `ScenarioGenerationActivity`, and give `GenerationWorkflow` its first real dispatch (AC: 1)
  - [ ] Signature `ScenarioGenerationActivity(journey: Journey) -> list[Scenario]` per Module Contracts — internally, the Activity fetches the Journey's attributed canonical `Page`/`Form`/`ApiEndpoint`/`Component` rows (where `journey_id` matches, set by Story 2.6's `InferenceActivity`), plus each page's `ComponentLocator`/`Assertion`/`PageTransition` rows (joined via those pages/components — those tables carry no `journey_id` of their own), and passes the pages (carrying this context the same way `InferenceActivity` attaches it, per `hosted.py`'s `_describe_page`) to `AIProvider.generate_scenarios`. **`[CORRECTED 2026-07-19]`** this task originally said "fetches the Journey's attributed `Evidence`" — that table no longer exists; see Task 2's note.
  - [ ] Write `Scenario` rows with `generation_run_id = journey.attempt` and `current=true` — this is the first generation attempt for the Journey, so there's nothing to supersede yet (that's Story 4.3's job)
  - [ ] **This is where `GenerationWorkflow` (graduated from Story 1.1's no-op shell by Story 2.5's `InferenceActivity`) gets its first real Activity dispatch, ending its stub period.** Wire the workflow to call `ScenarioGenerationActivity` — per the Architecture Spine's sequence diagram, this is dispatched immediately once `InferenceActivity` starts the workflow for a newly-created candidate, with no approval step in between
- [ ] Task 4: Build the Review Scenarios screen (AC: 2, 3)
  - [ ] Rows per Scenario with `Happy Path`/`Negative Path`/`Edge Case` badges (2026-07-15 rename from `type-happy`/`type-negative` — confirm current `DESIGN.md` badge-token naming at implementation time, since the copy label changed even if the underlying tint/hue mapping may not have)
  - [ ] Each row carries a `⋯` menu offering rename/edit/remove (FR-29) — this supersedes the prior hard "no action button, ever" rule (UX-DR23); see Dev Notes for what's actually still true vs. no longer true
  - [ ] Selecting a row loads a detail panel showing that Scenario's Test steps, a Test data table, and Expected result, replacing any prior selection — mirroring the list+detail-panel pattern established in Story 3.1
  - [ ] Remove: on confirmation, the Scenario row is removed from the list — **`[GAP]`** whether removal also needs to prevent/adjust downstream `TestAsset` generation (Story 4.2) for that Scenario is unconfirmed; flag for engineering rather than assuming a specific cascade behavior
  - [ ] Edit: per the `[GAP]` above AC's persistence-behavior flag, build the edit UI to capture the change and save it, but do not assume it silently reruns `PlaywrightGenerationActivity` — that linkage is exactly the unconfirmed part
  - [ ] Application-name breadcrumb *is* shown (Review Scenarios is Application-scoped), consistent with the rule established in Story 2.1
- [ ] Task 5: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] Discovering a Journey (Story 2.5) results in `Scenario` rows for it, covering both `happy` and `negative` types, all `current=true` — with no reviewer action taken
  - [ ] The Review Scenarios screen renders each row's badge, `⋯` menu (rename/edit/remove), and selecting a row shows Test steps/Test data table/Expected result in the detail panel
  - [ ] `ScenarioGenerationActivity` never imports a vendor AI SDK directly — only `packages/ai_provider`'s `HostedAIProvider`

## Dev Notes

- **This story is the payoff of the stub `GenerationWorkflow` decision made back in Story 1.1, graduated by Story 2.5** — read Story 2.5's Dev Notes/Task 5 on the `InferenceActivity`-triggered start before touching the workflow here, so the transition from stub to real dispatch is deliberate rather than a guess at the workflow's current shape. `[UPDATED 2026-07-15]` This used to be Story 3.2's job (Approve); that story is cut, and the graduation moved to Story 2.5 along with the rest of the workflow-start logic.
- **UX-DR23 ("Generated Scenarios remain view-only") is superseded as of 2026-07-15 by FR-29** — do not build against the old "no checkbox/action button, ever" rule. What survives, unchanged, is Rename/Delete-only Journey curation (Stories 3.4) and UX-DR21/UX-DR22's "no confidence signal / no merge-split" constraints — those are unrelated to Scenarios and remain hard constraints. Read epics.md's Story 4.1 entry directly rather than trusting a memory of "Scenarios are view-only" from earlier planning docs.
- **`generation_run_id`'s meaning (the `attempt` integer) is a design choice made now, worth restating for whoever builds Story 4.2 next** — `TestAsset` will carry the same field with the same meaning, so consistency here matters for that story's `current=true` / superseding logic in Story 4.3.
- **The edit/remove persistence question (the `[GAP]` above) is worth surfacing to engineering leadership before, not during, implementation** — if edits turn out to feed generation, `ScenarioGenerationActivity`/`PlaywrightGenerationActivity`'s current "generate once per approval" flow may need a re-trigger path; if edits are display-only, none of that applies. Don't guess; ask. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

### Project Structure Notes

- Adds `Scenario` to `packages/domain`, extends `HostedAIProvider` (`packages/ai_provider`, Story 2.5), adds `ScenarioGenerationActivity` to `apps/workers/generation` (per the Structural Seed's worker split), extends `GenerationWorkflow` (`packages/workflows`, Stories 1.1/2.5), and builds the Review Scenarios screen in `apps/web`. No new top-level directories.
- **Depends on Epic 1, Epic 2 (Stories 1.1–2.5), and Epic 3's curation stories (3.1, 3.4, 3.5) being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. This is the first story in Epic 4.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1: Generate Scenarios for a Discovered Journey]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-14, FR-16, FR-29]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-3, #AD-8, #Module Contracts, #Sequence — Discovery to Delivery]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — badge variants (2026-07-15: `Happy Path`/`Negative Path`/`Edge Case`, renamed from `type-happy`/`type-negative`)]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Review & Trust Model — Scenario rename/edit/remove via `⋯` menu (2026-07-15, supersedes prior view-only rule)]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — `GenerationWorkflow`'s graduation from Story 1.1's stub, the `attempt`/workflow-ID convention this story's `generation_run_id` depends on, and `HostedAIProvider`/`litellm` this story extends]
- (Story 3.2 "Approve" — removed 2026-07-15; the `GenerationWorkflow`-start logic this story used to depend on moved to Story 2.5)

## Previous Story Intelligence

Epic 1, Epic 2 (including Story 2.5), and Epic 3 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 2.5 is implemented, check its File List for `GenerationWorkflow`'s exact current (stub) shape and the `attempt` field's exact type before wiring the real dispatch here.

## Latest Technical Notes

No new library decisions — extends the `litellm`-backed `HostedAIProvider` from Story 2.5, and the existing Temporal/FastAPI/SQLModel stack.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
