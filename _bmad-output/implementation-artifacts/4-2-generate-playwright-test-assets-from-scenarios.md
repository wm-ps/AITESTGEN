# Story 4.2: Generate Playwright Test Assets via a Named Test Suite

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 — reframed from a standalone "Generated Tests" code-review screen into "Generate Suite," the pipeline's 4th step. Underlying `TestAsset` generation is unchanged; only the screen framing changes. See `sprint-change-proposal-2026-07-15.md`.*

*`[REARCHITECTED 2026-07-23]` Clarified by explicit request: a **test case** is one `Scenario`; a **test suite** is a collection of related test cases. The end goal is multiple Test Suites per Application — **one per Journey** — not one flat batch of Test Assets. This adds a real `TestSuite` domain entity (`journey_id` FK, auto-named from the Journey) and makes `SuiteGenerationWorkflow` Journey-scoped again, mirroring `GenerationWorkflow` exactly. See Task 1/3 and the Change Log for the full rationale — this also *removes* the one flagged assumption from the prior same-day pass (the content-derived workflow-ID digest), since `journey.attempt` already covers that job once generation is Journey-scoped.*

## Story

As a user,
I want each Journey's generated Scenarios converted into an executable Playwright test suite — one named suite per Journey —
so that I have real, runnable regression coverage organized the same way I already think about my Journeys.

## Acceptance Criteria

1. `[CORRECTED 2026-07-21, REARCHITECTED 2026-07-23]` **Given** a candidate Journey with `current=true` Scenarios whose mandatory test data is completed and validated (Story 4.1 AC 5/6 — the `"Continue to Generate Test Suite →"` button is enabled), **when** the user submits the Generate Suite screen (AC 2), **then** one `SuiteGenerationWorkflow` runs per candidate Journey that has `current=true` Scenarios, creating one `TestSuite` row for that Journey (name auto-derived from the Journey's own name, `generation_run_id = journey.attempt`, `current=true`) and dispatching `PlaywrightGenerationActivity` once per Scenario — each producing a `TestAsset` row linked to both its Scenario (`scenario_id`) and its Journey's `TestSuite` (`test_suite_id`), carrying the generated Playwright code and `current=true` (`generation_run_id` is derived via `test_suite_id` → `TestSuite.generation_run_id`, not stored again on `TestAsset` — see Task 1). **This is not an automatic continuation of Story 4.1's workflow** — it's a second, independently-triggered dispatch; there is no path that generates Test Assets without this explicit trigger. For each `test_data` field on the Scenario being converted: if the reviewer already provided a `value`, use it; if it's still blank, compute a sensible default and use — and store — that instead. [Source: epics.md#Story 4.2; FR-17; architecture#AD-8]
2. `[UPDATED 2026-07-23]` The Generate Suite screen lets the user confirm a target environment before generating, showing a summary of how many Test Suites will be created (one per candidate Journey with current Scenarios) and the total Scenario count across them, alongside the generate action. **Suite names are not manually entered** — each Test Suite is automatically named after its own Journey. [Source: epics.md#Story 4.2]

**`[NOTE FOR PM/ENG — 2026-07-15]`** The Generate Suite screen also shows an "Execution" choice (`Run immediately`/`Schedule for later`/`Save without running`) — this is a confirmed UI placeholder only; do not build execution/scheduling behavior against it (see the architecture Deferred section). [Source: epics.md#Story 4.2]

**`[GAP — flagged 2026-07-15, RESOLVED 2026-07-23]`** The screen the user sees immediately after clicking "Generate Test Suite" was not reachable during the original 2026-07-15 UX review. **Now confirmed** (both by direct prototype-file inspection and by your own click-through of it, see Task 4a): it is **not** the code-viewer-plus-`<details>`-disclosure pattern described in the bullet directly below (that bullet is superseded, retained only as historical last-guess spec) — the real flow is a results screen with a "Test details" link revealing a per-`TestSuite` breakdown, each test case showing a type badge and a "Code" button that opens a shared code-viewer modal. [Source: epics.md#Story 4.2; your 2026-07-23 prototype click-through]

- `[SUPERSEDED 2026-07-23 — see Task 4a]` Each Test Asset row carries a `generated` badge, following the same tinted-wash-plus-saturated-text pattern as every other badge variant, rendered inside a code-viewer component with a `<details>` disclosure — the first/most-relevant block open by default, all others closed, opening one never closes another. [Source: DESIGN.md#Components — code-viewer, badge; EXPERIENCE.md#Component Patterns]

## Tasks / Subtasks

- [ ] `[REARCHITECTED 2026-07-23]` Task 1: Add the `TestSuite` and `TestAsset` domain entities (AC: 1)
  - [ ] Add `TestSuite` (`journey_id` FK — one `TestSuite` per Journey per attempt, mirroring `Scenario`'s own `journey_id` convention; `name: str`, auto-derived from the Journey's own name at creation time, e.g. `f"{journey.name} Test Suite"`; `generation_run_id: int` — the same `journey.attempt` value already established for `Scenario`; `current: bool` default `true`) to `packages/domain`, following the UUIDv7/UUIDv4 id convention. **New scope beyond epics.md/PRD/ERD** — this entity didn't exist before this pass's clarification that Test Suites are a real, per-Journey concept, not just a screen label.
  - [ ] A `UNIQUE(journey_id, generation_run_id)` constraint on `TestSuite` — this is what makes Task 3's `EnsureTestSuiteActivity` insert-or-fetch idempotent under a real concurrent race (two `PlaywrightGenerationActivity` calls for the same Journey both trying to create "their" `TestSuite` at once), not just idempotent in the common case
  - [ ] Add `TestAsset` (`scenario_id` FK — one `TestAsset` compiles from one `Scenario`, per the ERD; `test_suite_id` FK — every `TestAsset` belongs to exactly one `TestSuite`, its Scenario's Journey's suite for this attempt; the generated Playwright code as text; `current: bool` default `true`) — **no `generation_run_id` field on `TestAsset` itself**, see below
  - [ ] `[DECIDED 2026-07-23]` **`generation_run_id` lives on `TestSuite` only (`= journey.attempt`), not duplicated onto `TestAsset`.** `TestAsset.generation_run_id` is always derivable via `test_suite_id` → `TestSuite.generation_run_id`, and always correct — unlike `Scenario`, which genuinely needs its own stored `generation_run_id` because `Journey.attempt` is a *mutable* counter that keeps incrementing on every later regeneration (so reading `journey.attempt` today would give the wrong answer for a Scenario generated under an earlier attempt), `TestSuite` rows are themselves immutable once created — one new row per attempt, never updated in place — so `TestSuite.generation_run_id` for a given `TestAsset`'s `test_suite_id` never goes stale. Storing a second, redundant copy on `TestAsset` would only add a second source of truth that could drift out of sync with its own `test_suite_id`, for zero benefit — this follows the same "derive over duplicate" principle Story 4.1's own Dev Notes already established for `test_data` completeness (a cached flag would need to stay in sync with every write; deriving avoids that entirely). Every place that previously read/wrote `TestAsset.generation_run_id` now joins through `test_suite_id` instead — see Task 3's write path and Story 4.3's supersede logic.
  - [ ] Alembic migration (both entities; one migration or two — implementer's call)
- [ ] Task 2: Extend `HostedAIProvider` with `generate_playwright` (AC: 1)
  - [ ] Implement `generate_playwright(scenario: Scenario) -> TestAssetCode` per the exact Module Contracts signature, using the same `litellm`-backed client from Stories 2.5/4.1 — no code outside `packages/ai_provider` calling a vendor SDK directly (AD-3)
- [ ] `[REARCHITECTED 2026-07-23]` Task 3: Build `PlaywrightGenerationActivity` and a new, **Journey-scoped** `SuiteGenerationWorkflow` to dispatch it (AC: 1)
  - [ ] `SuiteGenerationWorkflow.run(self, journey_id: str) -> list[str]` — mirrors `GenerationWorkflow.run(journey_id)`'s exact shape (AD-2: zero I/O, only Activity dispatch). **This still does not extend `GenerationWorkflow`** — Temporal only permits one `@workflow.run` method per class, and `GenerationWorkflow`'s is already `ScenarioGenerationActivity`-shaped; a second, distinct workflow type is still needed even though both are now Journey-scoped, since each dispatches a different Activity for a different purpose.
  - [ ] First calls a small **`EnsureTestSuiteActivity(journey_id) -> test_suite_id`** — idempotent insert-or-fetch of this Journey's `current=true` `TestSuite` for its current `attempt` (on a unique-constraint conflict, re-query and use the row the concurrent call created — the same collision-handling pattern Story 4.1 already uses for `Journey`/`Capability` creation). This runs once per workflow execution, **before** the fan-out below, not once per Scenario — so N concurrent `PlaywrightGenerationActivity` calls for the same Journey never race to create duplicate `TestSuite` rows.
  - [ ] Signature `PlaywrightGenerationActivity(scenario_id: str, test_suite_id: str) -> TestAsset` per Module Contracts (extended with `test_suite_id`, new this pass) — note this takes **one** Scenario and the already-resolved `test_suite_id`, not a list, and does not create or look up the `TestSuite` itself
  - [ ] Reads every `current=true` Scenario for this one Journey — fans out one `PlaywrightGenerationActivity` call per Scenario found, concurrently (e.g. `asyncio.gather` over multiple `workflow.execute_activity` futures, still orchestration-only per AD-2)
  - [ ] `[CORRECTED 2026-07-21]` This is a separate workflow execution from Story 4.1's `GenerationWorkflow`, started when the Generate Suite screen is submitted (AC 1/Task 4) — not "within the same bounded workflow execution" as 4.1's `ScenarioGenerationActivity` dispatch, and not fired automatically right after it. By the time this triggers, the Journey's `Scenario` rows (with completed `test_data`) are already durable in Postgres — this dispatch only needs to read them, so no shared in-memory workflow state or Temporal signal is needed between the two phases.
  - [ ] Write `TestAsset` rows with `test_suite_id` = the id resolved by `EnsureTestSuiteActivity` above and `current=true`. **No `generation_run_id` written here** — it isn't a field on `TestAsset` (Task 1's decision); it's always available via `test_suite_id` → `TestSuite.generation_run_id` if a query needs it. **No separate `Journey` lookup needed here either** — `EnsureTestSuiteActivity` is the one place that touches `Journey`, once per workflow execution.
  - [ ] `[CORRECTED 2026-07-23]` **Idempotency, mirroring Story 4.1 Task 5's endpoint exactly, now that this is Journey-scoped again:** the Generate Suite submission endpoint starts one `SuiteGenerationWorkflow` per candidate Journey of the Application that (a) has `current=true` Scenarios and (b) does not already have a `current=true` `TestSuite` for this attempt — skip Journeys that already have one (mirrors Story 4.1 Task 5's `{"journeys_triggered": 0}` idempotency exactly, just applied here to Test Suites). `PlaywrightGenerationActivity` itself also checks before calling `AIProvider.generate_playwright` — skip as a no-op if a `current=true` TestAsset already exists for this `scenario_id` — a narrower defense against Temporal's at-least-once retry of an in-flight Activity call within the same dispatch, not a substitute for the endpoint-level skip.
  - [ ] `[CORRECTED 2026-07-23]` **Workflow-ID convention: `suite-{journey_id}-{attempt}`** — directly mirrors `generation-{journey_id}-{attempt}` (Stories 2.5/4.1), using `journey.attempt`, which already exists and is already exactly the right per-suite counter. No digest, no new `Application`-level field, no assumption needed. Two near-simultaneous submissions for the same Journey/attempt collide via Temporal's `WorkflowAlreadyStartedError`; a Story 4.3-regenerated Journey's new attempt naturally gets a fresh, non-colliding ID, exactly like `GenerationWorkflow` already does.
  - [ ] **Failure handling for the fan-out:** one Scenario's `PlaywrightGenerationActivity` failing (after exhausting its own retry policy, below) must not fail the whole Journey's dispatch. Gather the per-Scenario Activity futures with failures captured rather than propagated (e.g. `asyncio.gather(..., return_exceptions=True)`), log each failure, and let every other Scenario's `TestAsset` still get written; the workflow returns the list of successfully-created `TestAsset` ids and completes successfully even when some Scenarios failed. Matches this codebase's established fault-isolation convention for batch capture (`discovery_worker`'s per-item persist: one bad row is caught, logged, and rolled back without aborting the rest of the batch).
  - [ ] **Per-Activity retry policy/timeout:** `start_to_close_timeout=timedelta(minutes=5)`, `retry_policy=RetryPolicy(maximum_attempts=3)` — copied directly from `GenerationWorkflow`'s own already-implemented convention for `ScenarioGenerationActivity` ("generous for LLM latency, matching `InferenceActivity`'s own generous timeout in `DiscoveryWorkflow`"), applied per-Scenario Activity call here too.
  - [ ] **Default test-data values, part of this same single flow — no second trigger, no new entry point:** immediately before calling `AIProvider.generate_playwright(scenario)`, resolve each of the Scenario's `test_data` fields — if `value` is already set (reviewer-provided), use it as-is; if `value is None`, compute a sensible default and use it. Persist the resolved defaults back onto `Scenario.test_data` (a plain write to the existing JSON column — no schema change). Defaults come from a small, deterministic, **non-AI** generator matching common field-name patterns — e.g. `username`/`email`-like names → a placeholder email, `password`-like names → a placeholder password, `card number`-like names → a placeholder card number, anything unrecognized → a generic fallback value (e.g. `"Test value"`) — mirroring `discovery_worker/crawler.py`'s `_generic_value`, and consistent with Story 4.1 AC 5's "the AI never fills in `value`" rule. No change to Story 4.1's `ScenarioGenerationActivity`, AI prompt, `PATCH /scenarios/{id}/test-data` endpoint, or Review Scenarios screen.
- [ ] `[ADDED 2026-07-23]` Task 3a: Confirm test-case-level LLM call granularity — one call per Scenario, never batched per Test Suite (AC: 1)
  - [ ] **LLM calls are dispatched at the test-case (`Scenario`) level, within the scope of a test suite (`SuiteGenerationWorkflow`/`TestSuite`), not at the suite level itself.** `PlaywrightGenerationActivity` calls `AIProvider.generate_playwright(scenario)` exactly **once per Scenario** — Task 2's signature already takes a single `Scenario` in and returns a single `TestAssetCode` out, never a list either direction. The number of LLM calls made while generating one Journey's Test Suite therefore equals that Journey's **test-case count**, not `1` (one bundled call for the whole suite) and not the Application's total test-suite count.
  - [ ] This mirrors the exact dispatch-granularity principle already established for the Journeys flow: Story 4.1's `"Continue to Scenarios"` trigger starts **one `GenerationWorkflow` per candidate Journey** — dispatch count equals the number of Journeys, never one bundled workflow for the whole Application. Story 4.2 applies the identical principle one level down: dispatch count (and LLM call count) equals the number of Scenarios within a Journey's Test Suite, never one bundled call for the whole Suite.
  - [ ] **Do not batch multiple Scenarios into a single `generate_playwright` call** (e.g., passing a list of Scenarios and getting back a list of `TestAssetCode` in one round-trip) — that would be the anti-pattern this task exists to rule out explicitly, even though Task 2/3's signatures already imply it. Each `PlaywrightGenerationActivity` execution is scoped to exactly one Scenario, fanned out concurrently by `SuiteGenerationWorkflow` (Task 3) — this task makes that an explicit, verified constraint rather than an implicit consequence of two other tasks' signatures.
  - [ ] Verify: generating a Test Suite for a Journey with N Scenarios makes exactly N calls to `AIProvider.generate_playwright` — one per Scenario — regardless of how many Test Suites (Journeys) are generated in the same Generate Suite submission.
- [ ] `[REARCHITECTED 2026-07-23]` Task 4: Build the Generate Suite screen (AC: 2)
  - [ ] Form fields: target environment (confirm/select) and a summary showing how many Test Suites will be created (one per candidate Journey with current Scenarios) and the total Scenario count across them, alongside the "Generate Test Suite" action. **No suite-name field** — each `TestSuite` is auto-named from its own Journey (Task 1/AC 2); there is nothing for the user to type here.
  - [ ] Include the "Execution" choice (`Run immediately`/`Schedule for later`/`Save without running`) as a **UI placeholder only** — per the `[NOTE FOR PM/ENG]` above, do not wire any execution/scheduling behavior behind these options; render them as inert radio controls with no backend effect
  - [ ] `[CORRECTED 2026-07-23]` Submitting triggers **one `SuiteGenerationWorkflow` per candidate Journey** that has `current=true` Scenarios (Task 3) — mirrors Story 4.1 Task 5's own "one `GenerationWorkflow` per candidate Journey" pattern exactly. This button (reached only once Story 4.1 AC 6's `"Continue to Generate Test Suite"` is enabled) is the **only** path that starts Test Asset generation; there is no automatic path, and no second/alternate path
  - [ ] Application-name breadcrumb *is* shown (Generate Suite is Application-scoped), consistent with the established rule
- [ ] `[CONFIRMED 2026-07-23]` Task 4a: Build the post-generation Test Suite/Test Case display (AC: per the `[GAP]` note above, now resolved)
  - [ ] **Resolved — confirmed against the reference prototype (`mockups/prototype-v2-standalone.html`) both by direct file inspection and by your own live click-through of it.** The prior `<details>`-disclosure spec (below the `[GAP]` note above) does **not** match the real prototype and is superseded by this Task. The actual, confirmed flow: submitting Generate Suite navigates to a results screen; a "Test details" link/action reveals the per-suite breakdown (the prototype implements this as an in-place expand via its own `suiteResultDetailsOpen` toggle — `<sc-if value="{{suiteResultDetailsOpen}}">` — rather than a hard second-page navigation, though either is an acceptable implementation of "a link reveals the details"). That breakdown lists **each `TestSuite`** (`group.fileName` = the Journey/suite name, `group.countLabel`), and under each, **its test cases** — one row per Scenario/`TestAsset` — showing a type badge (`Happy Path`/`Negative Path`/`Edge Case`, matching Story 4.1's own Scenario badge convention) and a **"Code" button** (`tc.onViewCode`) that opens **one shared code modal** (`codeModalCode`, a `<pre>` block) showing that specific test case's generated Playwright code.
  - [ ] No `<details>`/`<summary>` disclosure list, no "first block open by default" question, no per-row `generated` badge — none of these exist in the confirmed prototype flow; the earlier `<details>`-based bullets (superseded, left below only for history — see the `[GAP]` note's original text above) came from `DESIGN.md`/`EXPERIENCE.md`'s **generic** code-viewer component docs, not this specific screen.
  - [ ] Build: a results screen showing the suite-level summary (name — or names, since there are now N `TestSuite`s per this pass's rearchitecture, so likely one entry per suite, or a combined summary — implementer's call given the prototype only modeled a single suite's summary shape; total test-case count, journey count, est. runtime), a "Test details" action that reveals the grouped breakdown, one group per `TestSuite` with its test cases listed underneath (type badge + "Code" button each), and a single shared code-viewer modal that renders whichever test case's "Code" button was last clicked.
  - [ ] `[FLAGGED]` **Given this pass now produces N separate `TestSuite`s (one per Journey) instead of the prototype's single implied suite, the top-level summary's exact shape for "N suites at once" is a real, unconfirmed extension beyond the prototype** — a reasonable default is one summary card per `TestSuite` (each showing its own Journey name, test-case count, est. runtime), each independently expandable to its own "Test details" breakdown; flag to design for confirmation rather than assuming silently, since the prototype never had to model more than one suite at a time.
- [ ] `[REARCHITECTED 2026-07-23]` Task 5: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Triggering Generate Suite for an Application with N candidate Journeys (each with `current=true` Scenarios) creates exactly N `TestSuite` rows — one per Journey, each named after its own Journey, `current=true`
  - [ ] Each Scenario gets exactly one corresponding `TestAsset` row, linked to both its Scenario and its Journey's `TestSuite`, `current=true` — verify its effective `generation_run_id` (via `test_suite_id` → `TestSuite.generation_run_id`) matches its Scenario's own `generation_run_id`
  - [ ] For a Scenario with some `test_data` fields filled in and some blank: the generated `TestAsset` uses the reviewer's values where present and a field-name-appropriate default where blank (e.g. an email-like field gets a placeholder email); the resolved defaults are persisted back onto `Scenario.test_data`
  - [ ] The Generate Suite form shows the correct suite count (= journey count) and total scenario count summary before generating — no suite-name input to verify, naming is automatic
  - [ ] The Execution radio options render but trigger no execution/scheduling behavior on selection or submit
  - [ ] `[CONFIRMED 2026-07-23]` The post-generation results screen's "Test details" link/action reveals the per-`TestSuite` breakdown; each test case row shows its type badge and a "Code" button; clicking "Code" on different rows always shows that row's own code in the shared modal, and closing the modal doesn't affect any other row's state
  - [ ] A Scenario whose `PlaywrightGenerationActivity` call fails does not prevent every other Scenario's `TestAsset` from being written, for that same Journey's dispatch — verify a simulated single-Scenario failure still leaves the rest of that Journey's `TestAsset` rows created, `current=true`
  - [ ] Re-submitting Generate Suite for Journeys whose Scenarios haven't changed at all creates zero duplicate `TestSuite`/`TestAsset` rows and starts no new `SuiteGenerationWorkflow` for those Journeys (endpoint-level skip). A newly-discovered Journey, or a Story 4.3-regenerated Journey's fresh attempt, still gets its own new `TestSuite`/`TestAsset`s correctly on the next submission. Two genuinely concurrent submissions for the same Journey/attempt collide via `SuiteGenerationWorkflow`'s `suite-{journey_id}-{attempt}` workflow ID and Temporal's `WorkflowAlreadyStartedError`.
  - [ ] `PlaywrightGenerationActivity` never imports a vendor AI SDK directly

## Dev Notes

- **Read Story 4.1's Dev Notes on `generation_run_id`'s meaning before starting Task 1** — this story's `TestSuite` field must match that convention exactly (`= journey.attempt`), since Story 4.3's regeneration/superseding logic depends on `Scenario` and `TestSuite` from the same attempt carrying the same value. `[CONFIRMED 2026-07-23]` Now that `TestSuite` exists and is Journey-scoped, this is simply `journey.attempt` again, matching `Scenario`'s own convention with no divergence.
- `[DECIDED 2026-07-23]` **`TestAsset` does not get its own `generation_run_id` field — it's derived via `test_suite_id` → `TestSuite.generation_run_id`.** This is a deliberate asymmetry with `Scenario` (which *does* store its own copy), not an inconsistency: `Scenario`'s parent, `Journey`, has a *mutable* `attempt` counter that keeps changing across regenerations, so a `Scenario` must freeze the attempt value at its own creation time or a later read would give the wrong answer. `TestAsset`'s parent, `TestSuite`, is itself already a frozen, one-row-per-attempt entity (never updated in place) — so deriving through it is always safe, and storing a second copy on `TestAsset` would just be redundant state with no upside. Matches this codebase's already-established "derive over duplicate" convention (Story 4.1's own Dev Notes make the identical argument for `test_data` completeness).
- `[REARCHITECTED 2026-07-23]` **Why this pass makes `SuiteGenerationWorkflow` Journey-scoped again, reversing an earlier same-day pass's Application-wide design:** clarified by explicit request that a "test suite" is a real, per-Journey collection of test cases (Scenarios) — the end goal is generating as many Test Suites as there are Journeys, not one flat batch. This is closer to the *original* intent than the Application-wide model this file briefly carried: the Story's own title and user-story text ("...so that I have real, runnable regression coverage **for the Journey**") already implied per-Journey suites. Making `SuiteGenerationWorkflow.run(journey_id)` mirror `GenerationWorkflow.run(journey_id)` exactly also **removes** the one flagged assumption from the reverted design (the `suite-{application_id}-{digest}` workflow-ID convention) — `journey.attempt` already exists and already does that job, with zero new schema or hashing needed. The Generate Suite screen/endpoint remains Application-scoped in the sense that **one submission still fans out over every qualifying candidate Journey of the Application** (mirrors Story 4.1 Task 5's own "one `GenerationWorkflow` per candidate Journey" pattern) — only the *workflow type itself* moved from Application-scoped back to Journey-scoped.
- **Failure-handling policy and per-Activity retry/timeout convention (Task 3) are copied directly from `GenerationWorkflow`'s already-implemented `ScenarioGenerationActivity` dispatch** (`start_to_close_timeout=timedelta(minutes=5)`, `RetryPolicy(maximum_attempts=3)`) and from this codebase's established discovery-worker fault-isolation pattern (one bad item is logged and skipped, not fatal to the batch) — no new convention invented, both reused for consistency.
- **2026-07-15 reframing: "Generated Tests" (standalone code-review screen) is now "Generate Suite" (pipeline step 4)** — the underlying `TestAsset`/`PlaywrightGenerationActivity` generation logic (Tasks 1-3) is unchanged in spirit; only the screen this story builds is different (a target-environment/summary form, not a code-viewer landing screen). Story 4.1's Review Scenarios note about UX-DR23 being superseded is unrelated to this story — don't conflate the two.
- **The Execution placeholder (Run immediately/Schedule for later/Save without running) is explicitly not a real feature** — treat it exactly like Story 1.4's SSO/MFA placeholder in spirit (a named, deliberately inert UI element), except here there is no unresolved product question to eventually resolve; it is confirmed placeholder-only per the user and the architecture Deferred section, and building real behavior behind it would introduce an architecture commitment (live test execution) nobody has actually decided on.
- **`[CORRECTED 2026-07-21]` Playwright generation is no longer chained automatically after Story 4.1's Scenario generation in one workflow execution — it's a second, independently-triggered dispatch, gated on Story 4.1 AC 6's test-data completion.** This reverses this story's original Task 3 wording ("within the same bounded workflow execution"), which predated 4.1's test-data-completion gate and assumed generation was fully automatic end-to-end (true before 2026-07-21, no longer true). No Temporal signal or long-lived wait is needed to bridge the gap between the two triggers — Story 4.1's `Scenario` rows (including reviewer-completed `test_data`) are already durable in Postgres by the time this story's trigger fires, so this workflow only needs to read them fresh, not share state with 4.1's already-finished workflow run.
- **`[FLAGGED 2026-07-21]` This correction assumes Story 4.1's "Continue to Scenarios" trigger and this story's "Generate Suite" trigger are genuinely separate, user-paced steps** — if a future implementation finds it easier to keep them in one workflow with a signal-based wait instead, that's a valid alternative, but should be a deliberate choice, not a silent reversion to automatic chaining.
- `[SIMPLIFIED 2026-07-23]` **This story has exactly one trigger, unchanged — Story 4.1 AC 6's "Continue to Generate Test Suite" button.** An earlier same-day pass briefly added a second, ungated entry point plus a separate default-fill task to let generation proceed without complete test data; per explicit follow-up direction, that whole second-entry-point design was reverted in favor of a single-flow behavior: `PlaywrightGenerationActivity` itself just resolves each field (reviewer value if present, computed default if blank) at generation time, folded directly into Task 3. No new screen, no new route, no "which path" product decision.
- **Why the default-fill logic still matters even with Story 4.1's gate unchanged and still enforcing completeness:** that gate only checks `mandatory=true` `test_data` entries (Story 4.1 Task 6) — a Scenario can still reach `PlaywrightGenerationActivity` with blank *optional* fields, which previously had no defined handling. This default-fill also serves as simple defense-in-depth for any edge case where a mandatory field is unexpectedly still blank, rather than that Activity failing or generating broken Playwright code against a `None` value.
- `[FLAGGED — known limitation, still applies]` **A default-filled `test_data` value is indistinguishable from a reviewer-provided one once written** — `Scenario.test_data` has no "was this defaulted or reviewed" marker, and Story 4.1's (frozen, not touched this pass) schema/screen have no way to show that distinction. Not fixed here; a future pass willing to touch Story 4.1 could add a per-field `"defaulted": true` marker for display.

### Project Structure Notes

- `[REARCHITECTED 2026-07-23]` Adds `TestSuite` and `TestAsset` to `packages/domain`, extends `HostedAIProvider` (`packages/ai_provider`), adds a new `SuiteGenerationWorkflow` (`packages/workflows`, alongside Story 4.1's `GenerationWorkflow` — not an extension of it, see Task 3) and `PlaywrightGenerationActivity`/`EnsureTestSuiteActivity` (`apps/workers/generation`), and builds the Generate Suite screen in `apps/web`. No new top-level directories.
- **Depends on Epic 1, Epic 2, Epic 3, and Story 4.1 being actually implemented**, not just created — Story 4.1 is now implemented (`review`); Epics 1-3 remain `ready-for-dev`/in-progress as of this pass.
- **Story 4.1's files remain untouched** — its `Scenario` domain entity/schema, `ScenarioGenerationActivity`, `AIProvider.generate_scenarios`, `PATCH /scenarios/{id}/test-data` endpoint, and Review Scenarios screen/gate are read but not modified. The default-fill logic is entirely inside `PlaywrightGenerationActivity` (Task 3), not a separate code path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2: Generate Playwright Test Assets via a Named Test Suite]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-17]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-2, #AD-3, #AD-8, #Module Contracts, #Deferred — test-suite execution mechanism placeholder]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — code-viewer, badge]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Component Patterns — Code disclosure]
- [Source: _bmad-output/implementation-artifacts/4-1-generate-scenarios-for-an-approved-journey.md — `generation_run_id` convention and `GenerationWorkflow`'s now-implemented shape (`run(journey_id) -> list[str]`, `packages/workflows/src/workflows/generation_workflow.py`) this story's `SuiteGenerationWorkflow` now mirrors (Journey-scoped, same workflow-ID pattern), still as a distinct workflow type — not an extension of it (Story 4.1 itself was renamed "...for a Discovered Journey" 2026-07-15; filename retained for continuity). Untouched this pass.]
- [Source: _bmad-output/implementation-artifacts/4-3-full-regeneration-of-test-assets-on-request.md — confirms `attempt` is strictly per-Journey (`Journey.attempt`); this pass's `TestSuite`/`SuiteGenerationWorkflow` redesign now matches that convention directly instead of working around it]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/mockups/prototype-v2-standalone.html — `suiteResult`/`group`/`tc.onViewCode`/`codeModalCode` bindings, re-checked 2026-07-23 for Task 4a; confirms no `<details>`/`<summary>` element exists in this file, and its per-Journey `group` structure now maps directly onto real `TestSuite` rows]
- [Source: `apps/workers/discovery/src/discovery_worker/crawler.py` — `_generic_value(input_type, name, field_id)`, the already-implemented non-AI, field-name-pattern-matched placeholder-value convention Task 3's default-value resolution follows]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md]

## Previous Story Intelligence

Story 4.1 is now implemented (`review`) — see its File List for `GenerationWorkflow`'s exact structure (`packages/workflows/src/workflows/generation_workflow.py`) and `Scenario`'s exact schema before building the new `SuiteGenerationWorkflow`/`PlaywrightGenerationActivity`/`EnsureTestSuiteActivity` (Task 3); Story 4.3 (also `ready-for-dev`, unimplemented) confirms `attempt` is strictly per-Journey — this pass's `TestSuite` design now matches that directly.

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
- 2026-07-23 — `[CORRECTED/RESOLVED/FLAGGED]` Pre-dev-agent gap review against
  the now-implemented Story 4.1. Six items resolved or explicitly flagged,
  modeling `TestAsset` generation as one flat, Application-wide dispatch (no
  `TestSuite` concept yet): critical `generation_run_id` bug fixed; a new
  Application-scoped `SuiteGenerationWorkflow` decided (vs. extending
  `GenerationWorkflow`, which Temporal's one-`@workflow.run`-per-class rule
  ruled out); a content-derived digest workflow-ID convention introduced
  (flagged assumption, since no Application-level attempt counter existed);
  idempotency, failure-handling, and retry policy specified; Task 4a's
  `<details>`-vs-prototype mismatch discovered and flagged. **Superseded by
  the 2026-07-23 rearchitecture entry below** — the Application-wide framing
  and the digest workflow-ID are both gone as of that pass.
- 2026-07-23 — `[CORRECTED]` A same-day follow-up: re-triggering Generate
  Suite after new Scenarios exist must succeed and cover only what's new,
  never be blocked outright (Story 4.3 depends on this for regenerated
  Journeys). Fixed a scoping bug in the digest design (was computed over the
  full Application Scenario set; corrected to the not-yet-covered delta).
  **Also superseded by the rearchitecture below** — this fix targeted the
  now-removed Application-wide delta model specifically.
- 2026-07-23 — `[ADDED, then REVERTED]` Two same-day follow-ups added, then
  fully reverted, a second "ungated" Generate Suite entry point (AC 3, Task
  3a, Task 4b) that let generation proceed without complete test data via a
  separate trigger. Reverted per explicit direction back to one trigger,
  with default-value resolution folded directly into
  `PlaywrightGenerationActivity` (Task 3) — this part of the design
  survived and is reflected in the current Task 3/Dev Notes above.
- 2026-07-23 — `[REARCHITECTED]` Clarified by explicit request: a test case
  is one `Scenario`; a test suite is a collection of related test cases; the
  end goal is one Test Suite **per Journey**, not one flat Application-wide
  batch. This is a real change from every prior same-day pass above, which
  modeled `TestAsset` generation as Application-scoped with no `TestSuite`
  concept. Added: a real `TestSuite` domain entity (`journey_id` FK, name
  auto-derived from the Journey — confirmed by explicit answer, not a
  manual naming field as AC 2 previously said). Reverted:
  `SuiteGenerationWorkflow` back to Journey-scoped
  (`run(journey_id) -> list[str]`, mirroring `GenerationWorkflow` exactly)
  and its workflow-ID convention back to `suite-{journey_id}-{attempt}`
  (mirroring `generation-{journey_id}-{attempt}`) — this **removes** the
  digest-based workflow-ID, which was only ever needed because the dispatch
  had been modeled as Application-wide with no natural per-suite counter;
  `journey.attempt` already covers that job once generation is Journey-scoped
  again, consistent with Story 4.3's confirmation that `attempt` is strictly
  per-Journey. Added `EnsureTestSuiteActivity` (idempotent insert-or-fetch,
  once per workflow execution, before the per-Scenario fan-out) to avoid a
  race where concurrent `PlaywrightGenerationActivity` calls for the same
  Journey would otherwise both try to create "their" `TestSuite`. The
  Generate Suite screen/endpoint stays Application-scoped in the sense that
  one submission still fans out over every qualifying candidate Journey
  (mirroring Story 4.1 Task 5's "one `GenerationWorkflow` per candidate
  Journey" pattern) — only the workflow type itself reverted to
  Journey-scoped. Failure-handling, retry policy, and the single-flow
  default-value-fill logic from prior same-day passes are unaffected by this
  rearchitecture and carried forward unchanged. Story 4.1 was not touched.
  Story 4.3 needs a matching follow-up to align its wording with the
  `TestSuite` entity and Journey-scoped `SuiteGenerationWorkflow` — not yet
  done as of this entry.
- 2026-07-23 — `[RESOLVED]` Task 4a's long-standing `[GAP]` (2026-07-15) is
  now confirmed, not just best-effort: you clicked through the reference
  prototype directly and confirmed the flow independently of this file's own
  earlier inspection of the same prototype's markup. Submitting Generate
  Suite navigates to a results screen; a "Test details" link reveals a
  per-`TestSuite` breakdown (matches this pass's `TestSuite` entity exactly),
  each test case showing a type badge and a "Code" button opening a shared
  code-viewer modal — not the `<details>`-disclosure-per-row pattern this
  story originally specified. Task 4a, the `[GAP]` note, and Task 5's
  matching verify bullet updated to state this as confirmed; the old
  `<details>` spec is retained only as superseded history. One thing still
  flagged, not silently assumed: since this pass now produces N `TestSuite`s
  (one per Journey) instead of the prototype's single implied suite, exactly
  how the top-level summary should present N suites at once is a real,
  unconfirmed extension beyond what the prototype modeled.
- 2026-07-23 — `[CONFIRMED/DECIDED]` Pre-implementation confirmation pass,
  prompted by explicit request to verify nothing was lost across the
  Application-scoped → Journey-scoped rearchitecture: (1) **Confirmed** —
  `PlaywrightGenerationActivity`'s per-Scenario idempotency check (skip
  generating, and skip the AI call, if a `current=true` TestAsset already
  exists for this `scenario_id`) survived the rewrite intact (Task 3). (2)
  **Confirmed** — the failure-isolation policy (`asyncio.gather(...,
  return_exceptions=True)`, one Scenario's failure doesn't fail the Journey's
  whole dispatch) and the retry policy/timeout
  (`start_to_close_timeout=timedelta(minutes=5)`,
  `RetryPolicy(maximum_attempts=3)`, copied from `GenerationWorkflow`'s
  `ScenarioGenerationActivity`) both survived intact (Task 3). (3)
  **Decided**: `TestAsset` does not get its own `generation_run_id` field —
  it's derived via `test_suite_id` → `TestSuite.generation_run_id`, never
  duplicated. Reasoning: unlike `Scenario` (which must freeze its own copy
  since `Journey.attempt` is mutable and keeps changing), `TestSuite` is
  itself already a frozen, one-row-per-attempt entity, so deriving through it
  is always safe — storing a second copy would just be redundant state with
  a drift risk, for no benefit. Matches this codebase's established "derive
  over duplicate" convention (Story 4.1's own reasoning for `test_data`
  completeness). Task 1/3/5 and Story 4.3's Task 2 updated to remove every
  `TestAsset.generation_run_id` reference, replaced with the `test_suite_id`
  derivation. (4) **Confirmed already done** — checked Story 4.3's live
  spec (not just its own Change Log history) and its AC 1/Task 2/Task 4/Dev
  Notes were already fully aligned to the Journey-scoped `SuiteGenerationWorkflow`/`TestSuite`
  model as of the prior same-day pass; no further edit was needed there
  beyond this entry's `generation_run_id` fix. (5) **Flagged, not
  actioned**: the request described this story as currently having "dual
  gated/ungated entry points with default values" — that is **not** what
  this file currently specifies. A prior same-day pass (see the
  `[SIMPLIFIED]` entry above) fully reverted the two-entry-point design back
  to a single trigger, per an explicit instruction earlier the same day.
  Nothing was changed on this point pending clarification — see the reply
  accompanying this pass for the direct question.
- 2026-07-23 — `[ADDED]` New Task 3a, by explicit request: makes explicit,
  first-class, and verified that LLM call count during Test Suite
  generation equals the number of test cases (`Scenario`s) in that Journey,
  never the number of test suites — one `AIProvider.generate_playwright`
  call per Scenario, dispatched within the scope of a per-Journey
  `SuiteGenerationWorkflow`/`TestSuite`, never batched across Scenarios into
  one call. This was already the implicit behavior of Task 2's
  single-Scenario-in/single-`TestAssetCode`-out signature and Task 3's
  one-`PlaywrightGenerationActivity`-per-Scenario fan-out; this task states
  it as an explicit design constraint (with a rule against batching) and
  adds a dedicated verify step, mirroring the same dispatch-granularity
  principle already established in the Journeys flow (Story 4.1: one
  `GenerationWorkflow` dispatch per Journey, not one bundled call for the
  Application). No behavior change — a clarifying, verified restatement of
  what Tasks 2/3 already specified.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
