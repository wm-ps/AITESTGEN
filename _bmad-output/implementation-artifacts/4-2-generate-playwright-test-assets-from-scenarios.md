# Story 4.2: Generate Playwright Test Assets via a Named Test Suite

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 — reframed from a standalone "Generated Tests" code-review screen into "Generate Suite," the pipeline's 4th step. Underlying `TestAsset` generation is unchanged; only the screen framing changes. See `sprint-change-proposal-2026-07-15.md`.*

## Story

As a user,
I want each generated Scenario converted into an executable Playwright test as part of a named, generated Test Suite,
so that I have real, runnable regression coverage for the Journey.

## Acceptance Criteria

1. `[CORRECTED 2026-07-21]` **Given** an Application whose Scenarios all have their mandatory test data completed and validated (Story 4.1 AC 5/6 — the `"Continue to Generate Test Suite →"` button is enabled), **when** the user submits the Generate Suite screen (AC 2), **then** `PlaywrightGenerationActivity` runs per Scenario, and a `TestAsset` row is created for each, carrying the generated Playwright code, a `generation_run_id`, and `current=true`. **This is not an automatic continuation of Story 4.1's workflow** — it's a second, independently-triggered dispatch; there is no path that generates Test Assets without this explicit trigger. [Source: epics.md#Story 4.2; FR-17; architecture#AD-8]
2. The Generate Suite screen lets the user name the suite and confirm a target environment before generating, showing a summary (journey count, scenario count) alongside the generate action. [Source: epics.md#Story 4.2]

**`[NOTE FOR PM/ENG — 2026-07-15]`** The Generate Suite screen also shows an "Execution" choice (`Run immediately`/`Schedule for later`/`Save without running`) — this is a confirmed UI placeholder only; do not build execution/scheduling behavior against it (see the architecture Deferred section). [Source: epics.md#Story 4.2]

**`[GAP — flagged 2026-07-15]`** The screen the user sees immediately after clicking "Generate Test Suite" (i.e., whether the prior code-viewer + `<details>` disclosure pattern, and the per-row `generated` badge, survive) was not reachable during UX review. Retained below as last-confirmed spec pending re-verification. [Source: epics.md#Story 4.2]

- Each Test Asset row carries a `generated` badge, following the same tinted-wash-plus-saturated-text pattern as every other badge variant, rendered inside a code-viewer component with a `<details>` disclosure — the first/most-relevant block open by default, all others closed, opening one never closes another. [Source: DESIGN.md#Components — code-viewer, badge; EXPERIENCE.md#Component Patterns]

## Tasks / Subtasks

- [ ] Task 1: Add the `TestAsset` domain entity (AC: 1)
  - [ ] Add `TestAsset` (`scenario_id` FK — one `TestAsset` compiles from one `Scenario`, per the ERD; the generated Playwright code as text; `generation_run_id`; `current: bool` default `true`) to `packages/domain`, following the UUIDv7/UUIDv4 id convention
  - [ ] `generation_run_id` follows the exact same convention established in Story 4.1's `Scenario.generation_run_id` (the `attempt` integer matching the `generation-{journey_id}-{attempt}` workflow) — consistency here is what makes Story 4.3's superseding logic (comparing `Scenario`/`TestAsset` pairs by `generation_run_id`) work correctly
  - [ ] Alembic migration
- [ ] Task 2: Extend `HostedAIProvider` with `generate_playwright` (AC: 1)
  - [ ] Implement `generate_playwright(scenario: Scenario) -> TestAssetCode` per the exact Module Contracts signature, using the same `litellm`-backed client from Stories 2.5/4.1 — no code outside `packages/ai_provider` calling a vendor SDK directly (AD-3)
- [ ] `[CORRECTED 2026-07-21]` Task 3: Build `PlaywrightGenerationActivity`, dispatched once per Scenario, via a **second, independently-triggered workflow dispatch** (AC: 1)
  - [ ] Signature `PlaywrightGenerationActivity(scenario: Scenario) -> TestAsset` per Module Contracts — note this takes **one** Scenario, not a list
  - [ ] **`GenerationWorkflow` needs a fan-out here that didn't exist in Story 4.1**: `ScenarioGenerationActivity` (4.1) returns a *list* of Scenarios (happy-path + negative), but `PlaywrightGenerationActivity` operates on one Scenario at a time. Dispatch one Activity call per Scenario, fanned out concurrently (still orchestration-only, AD-2, since the workflow only coordinates multiple Activity dispatches, not I/O itself)
  - [ ] **`[CORRECTED 2026-07-21]` This is a separate workflow execution from Story 4.1's, started when the Generate Suite screen is submitted (AC 1/Task 4) — not "within the same bounded workflow execution" as 4.1's `ScenarioGenerationActivity` dispatch, and not fired automatically right after it.** By the time this triggers, the Application's `Scenario` rows (with completed `test_data`) are already durable in Postgres from Story 4.1's now-finished workflow run — this dispatch only needs to read them, so no shared in-memory workflow state or Temporal signal is needed between the two phases. Reads every `current=true` Scenario across the Application's candidate Journeys (matching the Generate Suite screen's journey-count/scenario-count summary, AC 2), fanning out one `PlaywrightGenerationActivity` call per Scenario found
  - [ ] Write `TestAsset` rows with `generation_run_id = journey.attempt` (same value used for this attempt's Scenarios) and `current=true`
- [ ] Task 4: Build the Generate Suite screen (AC: 2)
  - [ ] Form fields: suite name, target environment (confirm/select), and a summary showing journey count and scenario count alongside the "Generate Test Suite" action
  - [ ] Include the "Execution" choice (`Run immediately`/`Schedule for later`/`Save without running`) as a **UI placeholder only** — per the `[NOTE FOR PM/ENG]` above, do not wire any execution/scheduling behavior behind these options; render them as inert radio controls with no backend effect
  - [ ] `[CORRECTED 2026-07-21]` Submitting triggers `PlaywrightGenerationActivity` (Task 3) for the Application's current Scenarios — this button (reached only once Story 4.1 AC 6's `"Continue to Generate Test Suite"` is enabled) is the **only** path that starts Test Asset generation; there is no automatic path
  - [ ] Application-name breadcrumb *is* shown (Generate Suite is Application-scoped), consistent with the established rule
- [ ] Task 4a: Build the post-generation Test Asset display — **`[GAP]` retained as last-confirmed spec, not confirmed present in the current reference prototype** (AC: per the `[GAP]` note above)
  - [ ] One `code-viewer` + native `<details>`/`<summary>` block per Test Asset, with light syntax tinting per `DESIGN.md` (keywords in `{colors.signal}`, strings in `{colors.good}`, comments in `{colors.ink-muted}`)
  - [ ] Closed by default for every block except the first/most-relevant — neither the PRD, architecture, nor UX spine defines exactly which one counts as "most-relevant" when a Journey has multiple Scenarios/Test Assets; a reasonable default is the first Scenario in list order (typically the first happy-path one), flagged here as an implementer's call, not a literal citation
  - [ ] Opening one disclosure must never close another — these are independent `<details>` elements, not an accordion group
  - [ ] Each row carries a `generated` badge (`{colors.good-wash}`/`{colors.good}` — an already-documented variant)
  - [ ] **Unlike Story 4.1's Review Scenarios screen, this display's `<details>` disclosure toggle is expected and correct** — this was never a view-only screen to begin with; no rule to over-apply here
- [ ] Task 5: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Each Scenario for a discovered Journey (Story 4.1) gets exactly one corresponding `TestAsset` row, `current=true`, sharing the same `generation_run_id`
  - [ ] The Generate Suite form captures suite name/target environment and shows the correct journey/scenario count summary before generating
  - [ ] The Execution radio options render but trigger no execution/scheduling behavior on selection or submit
  - [ ] If Task 4a's post-generation display is built, it shows one code block open by default, the rest closed, and opening a second block leaves the first open too
  - [ ] `PlaywrightGenerationActivity` never imports a vendor AI SDK directly

## Dev Notes

- **Read Story 4.1's Dev Notes on `generation_run_id`'s meaning before starting Task 1** — this story's `TestAsset` field must match that convention exactly, since Story 4.3's regeneration/superseding logic depends on `Scenario` and `TestAsset` from the same attempt carrying the same value.
- **The fan-out from one `ScenarioGenerationActivity` result to N `PlaywrightGenerationActivity` calls is new to this workflow** — Story 4.1 only ever dispatched a single Activity. Get the Temporal pattern right here (e.g. `asyncio.gather` over multiple Activity futures within the workflow, still orchestration-only). `[UPDATED 2026-07-15]` The `CIDeliveryActivity` dispatch this was originally compared against belonged to Epic 5 (CI/CD Delivery), now removed — no story builds that fan-out.
- **2026-07-15 reframing: "Generated Tests" (standalone code-review screen) is now "Generate Suite" (pipeline step 4)** — the underlying `TestAsset`/`PlaywrightGenerationActivity` generation logic (Tasks 1-3) is unchanged; only the screen this story builds is different (a name/target-environment/summary form, not a code-viewer landing screen). Story 4.1's Review Scenarios note about UX-DR23 being superseded is unrelated to this story — don't conflate the two.
- **The Execution placeholder (Run immediately/Schedule for later/Save without running) is explicitly not a real feature** — treat it exactly like Story 1.4's SSO/MFA placeholder in spirit (a named, deliberately inert UI element), except here there is no unresolved product question to eventually resolve; it is confirmed placeholder-only per the user and the architecture Deferred section, and building real behavior behind it would introduce an architecture commitment (live test execution) nobody has actually decided on.
- **`[CORRECTED 2026-07-21]` Playwright generation is no longer chained automatically after Story 4.1's Scenario generation in one workflow execution — it's a second, independently-triggered dispatch, gated on Story 4.1 AC 6's test-data completion.** This reverses this story's original Task 3 wording ("within the same bounded workflow execution"), which predated 4.1's test-data-completion gate and assumed generation was fully automatic end-to-end (true before 2026-07-21, no longer true). No Temporal signal or long-lived wait is needed to bridge the gap between the two triggers — Story 4.1's `Scenario` rows (including reviewer-completed `test_data`) are already durable in Postgres by the time this story's trigger fires, so this workflow only needs to read them fresh, not share state with 4.1's already-finished workflow run. This mirrors how Story 4.3 already triggers a fresh `GenerationWorkflow` attempt on request — no new Temporal pattern introduced here.
- **`[FLAGGED 2026-07-21]` This correction assumes Story 4.1's "Continue to Scenarios" trigger and this story's "Generate Suite" trigger are genuinely separate, user-paced steps** — if a future implementation finds it easier to keep them in one workflow with a signal-based wait instead, that's a valid alternative, but should be a deliberate choice, not a silent reversion to automatic chaining.

### Project Structure Notes

- Adds `TestAsset` to `packages/domain`, extends `HostedAIProvider` (`packages/ai_provider`), extends `GenerationWorkflow` and adds `PlaywrightGenerationActivity` to `apps/workers/generation`, and builds the Generate Suite screen in `apps/web`. No new top-level directories.
- **Depends on Epic 1, Epic 2, Epic 3, and Story 4.1 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2: Generate Playwright Test Assets via a Named Test Suite]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-17]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-2, #AD-3, #AD-8, #Module Contracts, #Deferred — test-suite execution mechanism placeholder]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — code-viewer, badge]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Component Patterns — Code disclosure]
- [Source: _bmad-output/implementation-artifacts/4-1-generate-scenarios-for-an-approved-journey.md — `generation_run_id` convention and `GenerationWorkflow`'s current shape this story extends (Story 4.1 itself was renamed "...for a Discovered Journey" 2026-07-15; filename retained for continuity)]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md]

## Previous Story Intelligence

Epics 1-3 and Story 4.1 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 4.1 is implemented, check its File List for `GenerationWorkflow`'s exact structure and `Scenario`'s exact schema before adding the `PlaywrightGenerationActivity` fan-out.

## Latest Technical Notes

No new library decisions — extends the `litellm`-backed `HostedAIProvider` and the existing Temporal/FastAPI/SQLModel stack. Verify current Playwright Python code-generation conventions (e.g. current recommended locator/assertion style) at implementation time if the AI-generated code needs to target a specific Playwright API surface.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-21 — `[CORRECTED]` AC 1, Task 3, Task 4, and Dev Notes: Playwright
  generation is no longer an automatic continuation of Story 4.1's
  Scenario-generation workflow. Story 4.1 added a test-data completion
  gate (AC 6) that this story's original Task 3 wording contradicted
  ("dispatched... within the same bounded workflow execution," implying
  automatic, immediate chaining with no gate). Corrected: `TestAsset`
  generation is a second, independently-triggered workflow dispatch,
  started only when the Generate Suite screen is submitted — reading the
  Application's already-durable, test-data-complete `Scenario` rows fresh
  from Postgres, no Temporal signal or shared workflow state needed. No
  other part of this story changed; it remains `ready-for-dev`,
  unimplemented.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
