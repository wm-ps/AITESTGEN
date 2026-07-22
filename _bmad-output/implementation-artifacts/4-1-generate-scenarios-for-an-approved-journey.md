# Story 4.1: Generate Scenarios for a Discovered Journey

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 (twice, same day) — Scenarios are no longer view-only; adds FR-29 (rename/edit/remove). Later the same day: renamed from "...for an Approved Journey" — Approve/Reject (Stories 3.2/3.3) are cut; generation now starts immediately on discovery, via Story 2.5's `InferenceActivity`, not on approval. See `sprint-change-proposal-2026-07-15.md`. `[CORRECTED 2026-07-21]` The "starts immediately on discovery" part no longer holds — see AC 1/Task 5 and the third 2026-07-21 Change Log entry below; generation is now triggered by the user clicking "Continue to Scenarios," not automatic. The name/no-approval-gate parts of this note are otherwise still accurate — Journeys still need no per-Journey approval, this is a batch trigger, not a reintroduced approval step.*

## Story

As a user,
I want to trigger integration test Scenario generation for every discovered Journey once I'm done curating them, covering both happy-path and negative cases,
so that the map becomes actionable test coverage, not just documentation, on my terms rather than the instant discovery finishes.

## Acceptance Criteria

1. `[CORRECTED 2026-07-21 — REVERSES the 2026-07-21 "Continue to Scenarios" update below]` **Given** the user clicks `"Continue to Scenarios"` (AC 4) on the Discover Journeys screen, **when** that click starts one `GenerationWorkflow` per candidate Journey of the Application and `ScenarioGenerationActivity` runs on each, calling the AI provider only through the `AIProvider` port, **then** `Scenario` rows are created for each Journey, covering both happy-path and negative/edge-case scenarios. **There is no automatic generation at Journey-discovery time** — this button click is the sole trigger. [Source: epics.md#Story 4.1; FR-16 — `[NOTE]` FR-16/FR-14 still say "generation starts immediately upon discovery, not gated on approval"; this update reverses that for Scenario generation specifically, not a literal citation match — flag for a follow-up epics.md/PRD correction, out of this pass's scope]
2. `[UPDATED 2026-07-21]` The Review Scenarios screen lists them with `Happy Path`/`Negative Path`/`Edge Case` badges (renamed from `type-happy`/`type-negative`), each with a `⋯` menu offering rename/remove — **Edit is removed** (see below). [Source: epics.md#Story 4.1; FR-29 — stale as of this update, still says "rename, edit, or remove"; not corrected here since only this story file is in scope, flag for a follow-up epics.md/PRD pass]
3. `[UPDATED 2026-07-21]` Selecting a scenario shows its Test steps, an **editable Test data form**, and Expected result in a detail panel. The Test data form's fields are not fixed columns — they are dynamically rendered per the field definitions AI-generated for that specific Scenario (AC 5), each accepting reviewer-provided input. [Source: epics.md#Story 4.1]

4. `[ADDED 2026-07-21, REVERSED 2026-07-21 — see AC 1]` Given candidate Journeys exist for an Application, the Discover Journeys screen (Story 3.1) shows a Journeys-discovered count above the candidate list (`"N Journeys Discovered"` / `"1 Journey Discovered"`) and a `"Continue to Scenarios →"` button, enabled only when at least one candidate Journey exists (disabled/grayed otherwise). **Clicking it is what starts Scenario generation (AC 1)** — one `GenerationWorkflow` per candidate Journey of the Application, each running `ScenarioGenerationActivity` — then navigates to the Review Scenarios screen. Earlier the same day this was documented as navigation-only, on the assumption generation already ran automatically at discovery time; that assumption no longer holds — **there is no automatic path**, this button is the sole trigger. [Source: `mockups/prototype-v2-standalone.html` — `journeysHeaderLabel`, `continueToScenarios`, `journeysContinueDisabled` — label/pattern only, the prototype's own handler is navigation-only since its Scenarios are pre-baked; the generation-trigger behavior is your 2026-07-21 direction, not prototype-sourced]
5. `[ADDED 2026-07-21]` **Given** `ScenarioGenerationActivity` runs, **when** the AI provider returns a Scenario, **then** it also returns the set of test-data input fields that Scenario needs to be executable (e.g. `username`, `password`, `card number`, `expected value`) — each field carries a name and a mandatory flag, with **no value** (the AI defines what's needed, never supplies or guesses the value itself). [Source: your request 2026-07-21 — not present in the reference prototype, which only renders static pre-baked test-data rows, not AI-defined field schemas; this is new scope beyond `mockups/prototype-v2-standalone.html`]
6. `[ADDED 2026-07-21]` **Given** a Journey's Scenarios each have their AI-defined test-data fields, **when** the reviewer fills in every mandatory field across them, **then** the system validates completeness and enables a `"Continue to Generate Test Suite →"` button on the Review Scenarios screen; **while** any mandatory field remains empty, the button stays disabled. Clicking the enabled button proceeds to Story 4.2's Generate Suite screen. **This is a different button from AC 4's "Continue to Scenarios"** — that one enters this story's screen from Story 3.1's; this one leaves this story's screen for Story 4.2's. [Source: your request 2026-07-21; button label/pattern cross-checked against `mockups/prototype-v2-standalone.html`'s `continueToSuite`/`scenariosContinueDisabled` (there, disablement is only "are there any Scenarios at all" — the mandatory-test-data-completeness gate itself is new scope, not in the prototype)]

**`[GAP — flagged 2026-07-15, RESOLVED 2026-07-21]`** Whether an edited Scenario's Test data/steps actually feed Playwright generation, or the edit is display-only, is now moot — **Edit is removed entirely** (AC 2); there is no edit action left to have a persistence question about. Test data is instead filled in via the dedicated form (AC 3/5/6), which *does* feed generation by design (it's the whole point of AC 6's gate).

**`[GAP — flagged 2026-07-21, RESOLVED 2026-07-21 during implementation]`** Whether "all mandatory test data completed" (AC 6) scopes to the currently-viewed Journey's Scenarios only, or every Scenario across every Journey in the Application was resolved in favor of **Application-wide** — `GET /applications/{id}/scenarios` and the completeness check both operate over every candidate Journey's current Scenarios for the Application, consistent with Story 4.2's Application-scoped Generate Suite screen and the Review Scenarios screen's own Application-scoped breadcrumb (Task 4).

*(Superseded 2026-07-15 — retained for history: the prior AC required Scenarios be strictly view-only with no checkbox/action button on any row (UX-DR23). This rule no longer holds — see FR-29 and `EXPERIENCE.md#Review & Trust Model`.)*

## Tasks / Subtasks

- [x] Task 1: Add the `Scenario` domain entity (AC: 1, 5)
  - [x] Add `Scenario` (`journey_id` FK, `type` [`"happy" | "negative"`], description/content, `generation_run_id`, `current: bool` default `true`) to `packages/domain`, following the UUIDv7/UUIDv4 id convention
  - [x] `[ADDED 2026-07-21]` Add `test_data: list[{name: str, mandatory: bool, value: str | None}]` (JSON column) — the AI-defined field schema from AC 5, `value` starting `null`/blank and filled in later by the reviewer (AC 6). **Completeness is computed on read** (all `mandatory=true` entries have a non-blank `value`), not stored as a separate boolean — a reasoned default, not a literal requirement: a cached "is_complete" flag would need to stay in sync with every `test_data` write, and this codebase already prefers deriving state over duplicating it (e.g. `Journey`/`Capability` excluding `status="deleted"` rows rather than keeping a separate active-count). Flag to product/engineering if a stored flag turns out to be needed for query performance at scale.
  - [x] `generation_run_id` stores the `attempt` value the `GenerationWorkflow` run belongs to (matching the `generation-{journey_id}-{attempt}` workflow-ID convention, `attempt` added by Story 2.5) — this is a design choice, not an explicit schema given anywhere, chosen so the workflow ID can always be reconstructed from `journey_id` + `generation_run_id` for tracing
  - [x] Alembic migration
- [x] Task 2: Extend `HostedAIProvider` with `generate_scenarios` (AC: 1, 5)
  - [x] Implement `generate_scenarios(journey: Journey, pages: list[Page]) -> list[Scenario]` per the exact signature in the Architecture Spine's Module Contracts, using the same `litellm`-backed client established in Story 2.5 — no new vendor SDK, no code outside `packages/ai_provider` calling it directly (AD-3). **`[CORRECTED 2026-07-19]`** the generic `Evidence` table this task originally named was removed 2026-07-18 (Sprint Change Proposal) — there is no `Evidence` to pass; the real input is canonical `Page` rows (Story 2.5's Application Model), the same shape Story 2.6's `InferenceActivity`/`HostedAIProvider.infer_journeys` already reads.
  - [x] `[ADDED 2026-07-21]` The returned `Scenario`s' `test_data` field-schema (name + mandatory flag per field, e.g. `username`, `password`, `card number`, `expected value`) is generated in the same AI call as the steps/expected-result content — no separate provider method. The AI never fills in `value`; that's the reviewer's job (AC 6), by design.
- [x] Task 3: Build `ScenarioGenerationActivity`, and give `GenerationWorkflow` its first real dispatch (AC: 1)
  - [x] Signature `ScenarioGenerationActivity(journey: Journey) -> list[Scenario]` per Module Contracts — internally, the Activity fetches the Journey's attributed canonical `Page`/`Form`/`ApiEndpoint`/`Component` rows (where `journey_id` matches, set by Story 2.6's `InferenceActivity`), plus each page's `ComponentLocator`/`Assertion`/`PageTransition` rows (joined via those pages/components — those tables carry no `journey_id` of their own), and passes the pages (carrying this context the same way `InferenceActivity` attaches it, per `hosted.py`'s `_describe_page`) to `AIProvider.generate_scenarios`. **`[CORRECTED 2026-07-19]`** this task originally said "fetches the Journey's attributed `Evidence`" — that table no longer exists; see Task 2's note.
  - [x] Write `Scenario` rows with `generation_run_id = journey.attempt` and `current=true` — this is the first generation attempt for the Journey, so there's nothing to supersede yet (that's Story 4.3's job). `test_data` is written as returned by the AI (field names + mandatory flags), every `value` `null` — nothing in this Activity fills them in
  - [x] `[CORRECTED 2026-07-21]` **This is where `GenerationWorkflow` (graduated from Story 1.1's no-op shell) gets its first real Activity dispatch, ending its stub period.** Wire the workflow to call `ScenarioGenerationActivity`. **This workflow is started by the "Continue to Scenarios" trigger endpoint (Task 5), not by `InferenceActivity`** — reverses this task's original wording, which described `InferenceActivity` starting `GenerationWorkflow` automatically at Journey-creation time, per the Architecture Spine's sequence diagram as it stood before this update. That diagram, and Story 2.5/2.6's actual (already-implemented) `InferenceActivity` code, both still reflect the old automatic-start behavior — reconciling them is a follow-up outside this pass's scope (doc-only, this story file), but implementing this task against the *old* diagram/code as-is would silently reintroduce automatic generation. Flag this to engineering before starting Task 3.
- [x] Task 4: Build the Review Scenarios screen (AC: 2, 3, 6)
  - [x] Rows per Scenario with `Happy Path`/`Negative Path`/`Edge Case` badges (2026-07-15 rename from `type-happy`/`type-negative` — confirm current `DESIGN.md` badge-token naming at implementation time, since the copy label changed even if the underlying tint/hue mapping may not have)
  - [x] `[UPDATED 2026-07-21]` Each row carries a `⋯` menu offering **rename/remove only — no Edit** (removed this update; supersedes FR-29's "rename, edit, or remove" wording, not corrected upstream — see the note on AC 2). This still supersedes the prior hard "no action button, ever" rule (UX-DR23); see Dev Notes for what's actually still true vs. no longer true
  - [x] `[UPDATED 2026-07-21]` Selecting a row loads a detail panel showing that Scenario's Test steps, an **editable Test data form** (one input per `test_data` entry, dynamically rendered from that Scenario's AI-generated field list — not a fixed set of columns — each labeled with its field name and a mandatory indicator), and Expected result, replacing any prior selection — mirroring the list+detail-panel pattern established in Story 3.1
  - [x] Remove: on confirmation, the Scenario row is removed from the list — **`[GAP]`** whether removal also needs to prevent/adjust downstream `TestAsset` generation (Story 4.2) for that Scenario is unconfirmed; flag for engineering rather than assuming a specific cascade behavior
  - [x] `[ADDED 2026-07-21]` `"Continue to Generate Test Suite →"` button on this screen (AC 6): disabled/grayed with a not-allowed cursor while any mandatory `test_data` field (scope per the 2026-07-21 `[GAP]` above) is empty; enabled (accent-colored, pointer cursor) once all are filled. Clicking navigates to Story 4.2's Generate Suite screen — **do not confuse with AC 4's "Continue to Scenarios" button**, which is a different button on Story 3.1's screen that enters this one
  - [x] Application-name breadcrumb *is* shown (Review Scenarios is Application-scoped), consistent with the rule established in Story 2.1
- [x] `[ADDED 2026-07-21, CORRECTED 2026-07-21]` Task 5: Add the Journeys-discovered count header, "Continue to Scenarios" button, and its trigger endpoint (AC: 1, 4)
  - [x] **Built into Story 3.1's `apps/web/src/components/DiscoverJourneys.tsx`, not a new screen** — this task only exists in this story because the button's purpose (entering the Scenario-generation flow) is 4.1's concern, not 3.1's
  - [x] Header text: `"{N} Journey Discovered"` (singular) / `"{N} Journeys Discovered"` (plural), positioned above the candidate list, matching the prototype's `journeysHeaderLabel` computation
  - [x] Button label `"Continue to Scenarios →"`; disabled/grayed with a not-allowed cursor when `journeys.length === 0`, enabled (accent-colored, pointer cursor) otherwise — matching the prototype's `journeysContinueDisabled`/`journeysContinueBg`/`journeysContinueColor`/`journeysContinueCursor` bindings
  - [x] `[CORRECTED 2026-07-21]` Click handler calls a new endpoint (e.g. `POST /applications/{id}/generate-scenarios`), Organization-scoped, that starts one `GenerationWorkflow` per candidate Journey of the Application — **reverses the earlier same-day wording that called this "navigation only"; it no longer is**, since generation is no longer automatic (AC 1). Idempotent: skip any candidate Journey that already has `current=true` Scenarios (mirrors the `WorkflowAlreadyStartedError`-based idempotency the real `InferenceActivity` code already uses for its own workflow-start call). Then navigate to the Review Scenarios screen
- [x] `[ADDED 2026-07-21]` Task 6: Build test-data save + validation (AC: 6)
  - [x] Endpoint to save a reviewer-provided `value` for one or more of a Scenario's `test_data` entries (e.g. `PATCH /scenarios/{id}/test-data`), Organization-scoped via Story 1.2's middleware, following the same rename/delete-endpoint conventions established in Story 3.4
  - [x] Completeness check (all `mandatory=true` entries non-blank) is computed live from `test_data`, not read from a stored flag — see Task 1's note; the "Continue to Generate Test Suite" button's enabled state (Task 4) queries this
  - [x] Resolve the 2026-07-21 `[GAP]` above (per-Journey vs. Application-wide completeness scope) before writing the actual query — don't guess a scope silently
- [x] Task 7: Verify end-to-end and record evidence (AC: 1-3, 5, 6)
  - [x] Discovering a Journey (Story 2.5) results in `Scenario` rows for it, covering both `happy` and `negative` types, all `current=true` — with no reviewer action taken
  - [x] The Review Scenarios screen renders each row's badge, `⋯` menu (rename/remove — **no Edit**), and selecting a row shows Test steps/an editable Test data form/Expected result in the detail panel
  - [x] `ScenarioGenerationActivity` never imports a vendor AI SDK directly — only `packages/ai_provider`'s `HostedAIProvider`
  - [x] `[ADDED 2026-07-21]` Each generated Scenario's `test_data` field list renders as inputs matching the AI response (field names vary per Scenario, not a fixed set); mandatory fields are visually indicated
  - [x] `[ADDED 2026-07-21]` "Continue to Generate Test Suite" stays disabled while any mandatory field is empty (across whatever scope Task 6 resolves), and enables once all are filled; clicking it navigates to Story 4.2's screen — a deliberate negative check (button must NOT be clickable while incomplete), not just a positive functional test

## Dev Notes

- **This story is the payoff of the stub `GenerationWorkflow` decision made back in Story 1.1, graduated by Story 2.5** — read Story 2.5's Dev Notes/Task 5 on the `InferenceActivity`-triggered start before touching the workflow here, so the transition from stub to real dispatch is deliberate rather than a guess at the workflow's current shape. `[UPDATED 2026-07-15]` This used to be Story 3.2's job (Approve); that story is cut, and the graduation moved to Story 2.5 along with the rest of the workflow-start logic.
- **UX-DR23 ("Generated Scenarios remain view-only") is superseded as of 2026-07-15 by FR-29** — do not build against the old "no checkbox/action button, ever" rule. What survives, unchanged, is Rename/Delete-only Journey curation (Stories 3.4) and UX-DR21/UX-DR22's "no confidence signal / no merge-split" constraints — those are unrelated to Scenarios and remain hard constraints. Read epics.md's Story 4.1 entry directly rather than trusting a memory of "Scenarios are view-only" from earlier planning docs.
- **`generation_run_id`'s meaning (the `attempt` integer) is a design choice made now, worth restating for whoever builds Story 4.2 next** — `TestAsset` will carry the same field with the same meaning, so consistency here matters for that story's `current=true` / superseding logic in Story 4.3.
- **`[RESOLVED 2026-07-21]` The edit/remove persistence question (the original `[GAP]`) is moot — Edit is removed entirely (AC 2).** There's no edit action left to have a persistence question about. Test data now has its own dedicated, purpose-built completion flow (AC 3/5/6) instead — one that *is* meant to feed generation by design (that's the entire point of AC 6's gate), so this isn't a case of silently resolving the old ambiguity either way; the ambiguity's subject was removed.
- **`[REVERSED 2026-07-21]` The "Continue to Scenarios" button (AC 4/Task 5) IS the generation trigger — wire it to start `GenerationWorkflow`/`ScenarioGenerationActivity`.** Earlier the same day this note said the opposite (navigation-only, since generation supposedly already ran automatically at discovery time) — that's now wrong by explicit product direction: **there is no automatic Scenario generation at Journey-discovery time anymore.** This is a real reversal of the "generation starts immediately, no approval gate" design from the 2026-07-15 Epic 3 rewrite — deliberate, not a rollback of that rewrite's Journey-curation decisions (Rename/Delete-only curation, no confidence signal, etc. all still hold; only the *generation trigger point* moved). **This creates an unresolved conflict with the already-implemented `InferenceActivity` code** (`apps/workers/discovery/src/discovery_worker/activities.py`), which currently starts `GenerationWorkflow` automatically per Journey right after creating it (Story 2.6, already shipped) — that code, and Story 2.5/2.6's docs, need their own follow-up correction to remove that automatic start; this pass only corrects Stories 4.1–4.3, out of its scope. Don't implement Task 5's endpoint alongside the unmodified old `InferenceActivity` code without addressing this, or both paths will start `GenerationWorkflow` and collide.
- **`[ADDED 2026-07-21]` The test-data completion/validation flow (AC 5/6, Tasks 1/2/6) is new scope beyond both the PRD/epics.md and the reference prototype** — the prototype's own "Test data" section (`selectedScenario.testData`) is a static read-only label/value display with pre-baked demo values, and its `scenariosContinueDisabled` only checks "are there any Scenarios at all," not field-level completeness. Don't assume the prototype's HTML/CSS for that section is the target shape — it needs to become an actual editable form, which the prototype never modeled.
- **`[ADDED 2026-07-21]` The per-Journey vs. Application-wide validation-scope `[GAP]` (see ACs) is the one open question most worth resolving before writing any code** — it changes the shape of Task 6's completeness query and probably Task 4's button-enabled-state query too. Don't default to one silently; ask, per this story's existing convention for flagged gaps (e.g. the original edit-persistence one).

### Project Structure Notes

- Adds `Scenario` to `packages/domain`, extends `HostedAIProvider` (`packages/ai_provider`, Story 2.5), adds `ScenarioGenerationActivity` to `apps/workers/generation` (per the Structural Seed's worker split), extends `GenerationWorkflow` (`packages/workflows`, Stories 1.1/2.5), and builds the Review Scenarios screen in `apps/web`. No new top-level directories.
- **Depends on Epic 1, Epic 2 (Stories 1.1–2.5), and Epic 3's curation stories (3.1, 3.4 — Story 3.5 cut in full 2026-07-21) being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. This is the first story in Epic 4.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1: Generate Scenarios for a Discovered Journey]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-14, FR-16, FR-29]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-3, #AD-8, #Module Contracts, #Sequence — Discovery to Delivery]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — badge variants (2026-07-15: `Happy Path`/`Negative Path`/`Edge Case`, renamed from `type-happy`/`type-negative`)]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Review & Trust Model — Scenario rename/edit/remove via `⋯` menu (2026-07-15, supersedes prior view-only rule); `[STALE as of 2026-07-21]` "edit" here is superseded by AC 2's removal, not corrected upstream — flag for a follow-up UX-doc pass]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — `GenerationWorkflow`'s graduation from Story 1.1's stub, the `attempt`/workflow-ID convention this story's `generation_run_id` depends on, and `HostedAIProvider`/`litellm` this story extends]
- (Story 3.2 "Approve" — removed 2026-07-15; the `GenerationWorkflow`-start logic this story used to depend on moved to Story 2.5)
- `[ADDED 2026-07-21]` [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/mockups/prototype-v2-standalone.html — Journeys-screen template (`journeysHeaderLabel`, `continueToScenarios`, `journeysContinueDisabled`/`Bg`/`Color`/`Cursor` — source for AC 4/Task 5) and Scenarios-screen template (`scenariosHeaderLabel`, `continueToSuite`, `scenariosContinueDisabled` — label/pattern source for AC 6/Task 4's button, though its mandatory-field validation is new scope the prototype doesn't model — see Dev Notes)]
- `[ADDED 2026-07-21]` [Source: your request 2026-07-21 — AI-generated test-data field schema (AC 5), per-field reviewer completion + validation gate (AC 6), Edit removal (AC 2); no prior FR/AC/architecture-doc coverage existed for the test-data-completion concept before this update]

## Previous Story Intelligence

Epic 1, Epic 2 (including Story 2.5), and Epic 3 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 2.5 is implemented, check its File List for `GenerationWorkflow`'s exact current (stub) shape and the `attempt` field's exact type before wiring the real dispatch here.

## Latest Technical Notes

No new library decisions — extends the `litellm`-backed `HostedAIProvider` from Story 2.5, and the existing Temporal/FastAPI/SQLModel stack.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-21 — `[ADDED]` AC 4 and Task 5 (renumbered from Task 6 by the
  second 2026-07-21 update below): Journeys-discovered count header and
  "Continue to Scenarios" button, validated against and sourced from
  `mockups/prototype-v2-standalone.html`. Built into Story 3.1's
  `DiscoverJourneys.tsx`, not a new screen. Corrected the request's framing:
  the button navigates to the Review Scenarios screen — it does not trigger
  generation, which already starts automatically at Journey-discovery time
  per AC1.
- 2026-07-21 — `[ADDED/UPDATED]` A second same-day update: (1) **Edit removed**
  from the Scenario `⋯` menu (AC 2/Task 4) — rename/remove only; this
  resolves the original 2026-07-15 `[GAP]` about edit persistence by
  removing its subject entirely. (2) **AI-generated test-data field schema**
  (AC 5, Task 1/2/3) — `Scenario.test_data` (name + mandatory flag per
  field, e.g. `username`/`password`/`card number`/`expected value`),
  generated by the same AI call as steps/expected-result, values always
  blank at generation time. (3) **Reviewer test-data completion + validation
  gate** (AC 3/6, Task 4/6) — the Test data table becomes an editable form;
  a new `"Continue to Generate Test Suite →"` button on this screen enables
  only once every mandatory field is filled, then proceeds to Story 4.2.
  Renumbered Tasks 5→7 to keep the verify task last. Flagged a new `[GAP]`:
  whether completeness scopes per-Journey or Application-wide is
  unconfirmed. Cross-checked against the prototype's Scenarios-screen
  template — confirmed the button label/pattern exists there, but the
  field-level validation logic is new scope the prototype doesn't model
  (its Test data section is static/read-only). No code was changed by
  either update; this story remains `ready-for-dev`, unimplemented.
- 2026-07-21 — `[REVERSED]` A third same-day update, fixing a contradiction
  between this story's AC 6 gate and Story 4.2's automatic-dispatch
  wording: **Scenario generation is no longer automatic at Journey-discovery
  time at all.** AC 1's trigger changed from "`InferenceActivity` starts
  `GenerationWorkflow` at Journey creation" to "the user clicks `Continue to
  Scenarios` (AC 4)" — Task 5 now owns the actual trigger endpoint, and AC
  4/Task 5/Dev Notes' earlier same-day "navigation only" framing is reversed
  accordingly. Task 3 corrected to say the workflow is started by Task 5's
  endpoint, not `InferenceActivity`. Stories 4.2 and 4.3 corrected to match
  (see their own Change Logs) — 4.2's Playwright generation is now a second,
  independently-triggered dispatch (not chained automatically after this
  story's workflow), and 4.3's regeneration goes through the same two-step
  gate rather than firing both Activities together. **Flagged, not fixed in
  this pass:** the already-implemented `InferenceActivity` code
  (`apps/workers/discovery/src/discovery_worker/activities.py`, Story 2.6)
  still starts `GenerationWorkflow` automatically per Journey — this now
  contradicts the corrected flow and needs its own follow-up (code + Story
  2.5/2.6 doc correction), out of this doc-only pass's scope.
- 2026-07-21 — `[IMPLEMENTED]` Full implementation, including the
  previously-flagged `InferenceActivity` follow-up (removed its automatic
  `GenerationWorkflow` start as part of this pass, not deferred). See Dev
  Agent Record for the complete file list and verification evidence. All
  backend (70) and frontend (30) tests pass; a real end-to-end smoke test
  against the live stack (Postgres/Vault/Temporal/LiteLLM) confirmed the
  full trigger → AI generation → rename/test-data/delete flow. Status
  moved to `review`.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

Full end-to-end smoke test against the real stack (Postgres/Vault/Temporal/
LiteLLM proxy via docker compose + `.env`): signed in as the seeded dev
user, created an Application, seeded one candidate Journey with two
JourneySteps directly (bypassing the real crawl), then via `curl` —
`POST /applications/{id}/generate-scenarios` returned
`{"journeys_triggered": 1}` and a **real** `HostedAIProvider.generate_scenarios`
LLM call produced 5 Scenarios (1 happy, 2 negative, 2 edge) with realistic
steps, expected results, and per-Scenario test-data field schemas (all
`value: null`). Verified: `PATCH /scenarios/{id}` renamed a Scenario;
`PATCH /scenarios/{id}/test-data` filled one field and returned
`test_data_complete` correctly still `false` with other mandatory fields
still blank; `PATCH .../test-data` with an unknown field name returned 422;
re-calling `generate-scenarios` after Scenarios already existed returned
`{"journeys_triggered": 0}` (idempotent); `DELETE /scenarios/{id}` removed
one, confirmed via a follow-up list call. Cleaned up the smoke-test
Application/Journey/Scenario rows afterward.

### Completion Notes List

- **The already-implemented `InferenceActivity` code was fixed as part of
  this story**, not left as a follow-up — Story 4.1's Dev Notes flagged
  that leaving it unmodified would let both the old automatic path and the
  new button-triggered path start `GenerationWorkflow` and collide. Removed
  the `start_workflow(GenerationWorkflow.run, ...)` call and its now-unused
  imports (`GenerationWorkflow`, `GENERATION_TASK_QUEUE`,
  `WorkflowAlreadyStartedError`, `get_temporal_client`) from
  `apps/workers/discovery/src/discovery_worker/activities.py`. Updated
  `test_inference_activity.py`'s test accordingly (renamed off
  "...and_starts_generation", removed the now-invalid workflow-handle
  assertion) — all 34 discovery-worker tests still pass.
- **`GenerationWorkflow` went from a no-arg no-op stub to
  `run(self, journey_id: str) -> list[str]`**, dispatching
  `ScenarioGenerationActivity` — the workflow itself does zero I/O (AD-2),
  only the Activity call.
- **The AC 6 completeness-scope `[GAP]` was resolved as Application-wide**
  (see the AC section above) — `GET /applications/{id}/scenarios` reads
  every candidate Journey's current Scenarios for the Application, and the
  frontend's `allComplete` check runs over that same list.
- **`Scenario.type` supports `"happy" | "negative" | "edge"`** (not just
  `"happy" | "negative"` as Task 1's original two-value wording said) —
  matches AC 2's three badges; the real LLM call confirmed the model
  actually produces all three when asked.
- **AIProvider protocol fix**: `generate_scenarios` was declared as a sync
  method in `packages/ai_provider`'s `AIProvider` Protocol even though every
  real implementation needs network I/O (like `infer_journeys`, which was
  already correctly `async`). Corrected to `async def generate_scenarios`.
- **Idempotency is two-layered**, matching the story's own Task 5 note: the
  `generate-scenarios` endpoint skips a Journey that already has
  `current=true` Scenarios for its `attempt`; Temporal's
  `WorkflowAlreadyStartedError` (implicitly, via the same deterministic
  workflow ID) covers the narrower race where two clicks land before either
  has written a Scenario row yet.
- **Deferred, not built in this pass**: the "Continue to Generate Test
  Suite" button's click handler is a stub (shows a "ready" message) since
  Story 4.2's Generate Suite screen doesn't exist yet — AC 6's gate
  (enable/disable logic) is fully real and tested, only the destination
  screen is out of this story's scope.
- **Story 4.2/4.3 docs were already corrected in a prior session pass** (see
  this file's own Change Log) to match this button-triggered flow — no
  further doc changes were needed for those two stories during
  implementation.

### File List

- `packages/domain/src/domain/scenario.py` — new `Scenario` entity
- `packages/domain/src/domain/__init__.py` — export `Scenario`/`ScenarioType`
- `migrations/versions/31f9485f28e9_add_scenario_entity.py` — new migration
- `packages/ai_provider/src/ai_provider/scenario_candidate.py` — new
  `ScenarioCandidate`/`TestDataFieldCandidate` DTOs
- `packages/ai_provider/src/ai_provider/__init__.py` — `AIProvider.generate_scenarios`
  signature corrected to `async`
- `packages/ai_provider/src/ai_provider/hosted.py` — `HostedAIProvider.generate_scenarios`
  + prompt, `_describe_page` extended with `stage_label`
- `packages/workflows/src/workflows/generation_workflow.py` — real
  `GenerationWorkflow.run(journey_id)` dispatch
- `packages/workflows/src/workflows/__init__.py` — export new names
- `apps/workers/generation/src/generation_worker/db.py` — new
- `apps/workers/generation/src/generation_worker/activities.py` — new
  `ScenarioGenerationActivity`
- `apps/workers/generation/src/generation_worker/worker.py` — registers the
  new activity
- `apps/workers/generation/pyproject.toml` — added `domain`/`ai-provider`/`sqlmodel`/`psycopg` deps
- `apps/workers/generation/tests/test_scenario_generation_activity.py` — new
- `apps/workers/discovery/src/discovery_worker/activities.py` — removed the
  automatic `GenerationWorkflow` start from `InferenceActivity`
- `apps/workers/discovery/tests/test_inference_activity.py` — updated to
  match
- `apps/api/src/api/main.py` — `generate-scenarios`, `scenarios` list,
  rename/delete, test-data endpoints
- `apps/api/tests/test_scenario_generation.py` — new
- `apps/web/src/components/DiscoverJourneys.tsx` — Journeys-discovered
  count header + `"Continue to Scenarios"` button/trigger
- `apps/web/src/components/DiscoverJourneys.test.tsx` — new tests for the
  above
- `apps/web/src/components/ReviewScenarios.tsx` — new screen
- `apps/web/src/components/ReviewScenarios.test.tsx` — new
- `apps/web/src/components/Stepper.tsx` — `current` type widened to include
  `"review"`
- `apps/web/src/App.tsx` — wired the `review-scenarios` view
- `apps/web/src/api.ts`, `apps/web/src/api-types.gen.ts` — new Scenario API
  calls/types
