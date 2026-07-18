---
baseline_commit: acaa283a69798961a099674e00c02ecddaf9fd15
---

# Story 2.5: Application Model Builder

*Renumbered 2026-07-18, was Story 2.6 — the initial draft numbered this story (Application Model Builder) AFTER the AI Inference story (2.5) that depends on its output, backwards from the actual pipeline order (Discovery → Model Builder → Inference). Corrected: this story is now 2.5, and AI Inference is renumbered to 2.6. Rewritten the same day, second pass: the generic `Evidence` table concept is removed — Story 2.2 now writes directly into typed tables (`Page`/`Form`/`Action`/`ApiEndpoint`/`PageTransition`), so this story's job shifts from "transform Evidence into structure" to "merge duplicate typed captures into canonical, reusable rows and derive Component/ComponentLocator/Assertion from them." See `sprint-change-proposal-2026-07-18.md`.*

Status: review <!-- implemented and verified 2026-07-18 (this session) — see Change Log -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to merge duplicate captures into one reusable, canonical Application Model,
so that journey inference and test generation work from reliable, deduplicated structure — and re-discovering an Application I've already mapped doesn't produce a pile of duplicates.

## Acceptance Criteria

1. **Given** typed rows captured by Story 2.2 (`Page`/`Form`/`Action`/`ApiEndpoint`/`PageTransition`, `merged_into_id = null`), **when** `ApplicationModelBuilderActivity` runs after `DiscoveryActivity` completes and before `InferenceActivity` starts, **then** rows representing the same logical page/form/API — whether captured in this run or an earlier Discovery Run against the same Application — are resolved to one canonical row per Application: every duplicate's `merged_into_id` is set to point at the canonical row, and the canonical row itself keeps `merged_into_id = null`. [Source: epics.md#Story 2.5; FR-30; architecture#AD-1, #AD-8, #AD-14]
2. `Component` and `ComponentLocator` rows are derived (never raw-captured) by grouping canonical `Action` rows on the same canonical `Page` by label/selector shape — each `Component` carrying a preferred locator plus one or more alternative/fallback locators, and its target page where applicable. [Source: FR-30; architecture#AD-8]
3. `Assertion` rows are derived from canonical `PageTransition`/`ApiEndpoint` outcomes attached to a canonical `Page`. [Source: FR-30]
4. Only `ApplicationModelBuilderActivity` ever sets an existing row's `merged_into_id`, and only it writes `Component`/`ComponentLocator`/`Assertion` rows — `DiscoveryActivity` never resolves duplicates or writes these three, and `InferenceActivity` only ever reads canonical rows. [Source: architecture#AD-14]
5. The Application Model's page-grouping concept reuses the existing `Capability` entity — no new `Module` entity is introduced. [Source: `sprint-change-proposal-2026-07-18.md` — resolved 2026-07-18]

**Out of Scope:** Changing `InferenceActivity`'s input source, and re-wiring `DiscoveryWorkflow` to dispatch `InferenceActivity` after this story's Activity — that is Story 2.6's job (already updated for this rework). This story only needs to insert its own Activity dispatch between `DiscoveryActivity` and wherever `InferenceActivity` is (re-)wired in. Also out of scope: capturing real selector data during crawl (that's Story 2.2's job, flagged in its own Dev Notes as new scope needed for this story's `ComponentLocator` derivation to have real fidelity) — if that capture isn't in place yet, derive locators from whatever's available (label-based) rather than blocking on it.

## Tasks / Subtasks

- [x] Task 1: Add the derived-only domain entities (AC: 2, 3)
  - [x] `packages/domain/src/domain/component.py` — `Component`: `id`/`external_id`, `application_id` FK, `page_id` FK (to canonical `Page`), `form_id` nullable FK (to canonical `Form` — set only for field-type Components; null for button/link-type Components), `journey_id` nullable FK (left `None` here; `InferenceActivity`, Story 2.6, is the sole future writer), `name`, `type` (str — e.g. `button`/`link`/`input`/`select`/`grid` — for field-type Components, mirrors the source `FormField.input_type`), `action` (str — e.g. `click`/`submit`/`fill`), `target_page_id` nullable FK to `page.id` (only meaningful for buttons/links that navigate; null for form fields), `created_at`. **No `discovery_run_id`** — `Component` is purely Application-scoped, derived from potentially many runs' `Action`/`FormField` rows, same reasoning as `Capability` having no `discovery_run_id` either. **Every automatable element gets a `Component`, not only clickable ones** — see Task 3
  - [x] `packages/domain/src/domain/component_locator.py` — `ComponentLocator`: `id`/`external_id`, `component_id` FK, `kind` (`"preferred" | "fallback"`), `strategy` (str — e.g. `role`/`testid`/`css`/`xpath`/`label`), `value` (str — the actual locator, e.g. `getByRole('button', { name: 'Save' })` or `getByLabel('Email')`), `priority` (int, fallback ordering) — one mechanism for every locator, whether the `Component` is a button or a form field
  - [x] `packages/domain/src/domain/assertion.py` — `Assertion`: `id`/`external_id`, `application_id` FK, `page_id` FK (to canonical `Page`), `component_id` nullable FK (set when the assertion targets a specific element, e.g. "success message visible"; null for a page/API-level outcome), `journey_id` nullable FK, `kind` (str — e.g. `state_transition`/`status_code`/`element_visible`), `expected_value` (JSONB), `created_at`. **No `discovery_run_id`** — same reasoning as `Component`
  - [x] Add `FormField.component_id` (nullable FK to `component.id`) — set once Task 3 derives that field's `Component`, so generation can join a field's validation rules (`ValidationRule`, via `FormField`) with its locator (`ComponentLocator`, via `Component`) in one step
  - [x] Export all three new entities from `packages/domain/src/domain/__init__.py`
  - [x] Confirm `merged_into_id` (nullable, self-referencing FK) exists on `Page`, `Form`, `ApiEndpoint` per Story 2.2's schema — **not** on `Action`/`PageTransition`, which don't have it. If Story 2.2's migration didn't already add these columns, add them here as a follow-up migration; verify against Story 2.2's actual `packages/domain` state before assuming which migration owns them
  - [x] One Alembic migration for `Component`/`ComponentLocator`/`Assertion`, `FormField.component_id` (and `merged_into_id` columns, if not already present from Story 2.2)
- [x] Task 2: Build `ApplicationModelBuilderActivity`'s merge logic (AC: 1)
  - [x] New module `apps/workers/discovery/src/discovery_worker/model_builder.py` (sibling to `crawler.py`/`identity_key.py`) — keeps the merge/derivation logic out of the already-large `activities.py`, which just calls into it
  - [x] Register `@activity.defn(name="ApplicationModelBuilderActivity")` in `apps/workers/discovery/src/discovery_worker/activities.py`, alongside `discovery_activity`/`inference_activity`
  - [x] Signature: `ApplicationModelBuilderActivity(discovery_run_id: str) -> ApplicationModelBuilderOutput` (new dataclass in `packages/workflows`, mirroring `DiscoveryActivityOutput`'s placement)
  - [x] **Page merge (AC 1):** normalize each un-merged `Page`'s captured URL into a `url_template` (a segment that's purely numeric or a UUID becomes `{id}`) — this is a sound, non-binding default, same framing as Story 2.2's traversal algorithm. Query **all** `Page` rows for this Application (not just this run's) grouped by `url_template`; within each group, the oldest row (by `discovery_run_id`'s creation order, or simplest: lowest `id` under UUIDv7's time-ordering) is canonical, all others get `merged_into_id` set to it — including this run's own new rows if they duplicate an already-canonical row from a prior run
  - [x] **Form/ApiEndpoint merge:** same pattern — group `Form` rows by (canonical `page_id`, `action_url`, `method`); group `ApiEndpoint` rows by (`method`, normalized `path` template); resolve to one canonical row per group, same-Application only (never merge across Applications)
  - [x] **This activity must be idempotent under Temporal's at-least-once retry (AD-9):** re-running the merge against the same discovery run should not toggle an already-resolved row's `merged_into_id` back and forth, or create duplicate `Component` rows — always resolve by querying current state, never by assuming this is the first time
- [x] Task 3: Derive `Component`/`ComponentLocator`/`Assertion` for **every automatable element** (AC: 2, 3)
  - [x] **Button/link Components:** group canonical `Action` rows (`page_id` resolved through `merged_into_id` to the canonical `Page`) by label/selector shape; find-or-create one `Component` per group (a stable identity — e.g. canonical `page_id` + label — so re-running against a later run's new `Action` rows updates the existing `Component` rather than duplicating it)
  - [x] **Form-field Components (`[ADDED]` — closes a real gap: without this, a discovered form field has validation metadata but no locator, and generation can't target it):** for every `FormField` on a canonical `Form`, find-or-create one `Component` (`type` = the field's `input_type`, `form_id` set, `target_page_id` null) — a stable identity, e.g. canonical `form_id` + field `name`. Set `FormField.component_id` to point at it
  - [x] Derive `ComponentLocator` rows from whatever selector information the source row carries — for button/link Components, from the grouped `Action` rows (see Story 2.2's Dev Notes on capturing this at crawl time); for form-field Components, from the `FormField`'s own captured selector info (see Story 2.2's Dev Notes — capturing a field's locator at fill-time is separate scope from capturing an action's locator at click-time). One `kind="preferred"` plus zero or more `kind="fallback"`, ordered by `priority`, for either kind of `Component`. If Story 2.2 hasn't yet landed real selector capture for one or both, fall back to a label-based locator (lower fidelity, not blocking) rather than inventing selector data that was never observed
  - [x] Derive `Assertion` rows from canonical `PageTransition`/`ApiEndpoint` outcomes attached to the canonical `Page` (e.g. "action X leads to page Y" or "this API call returns status 200"); set `Assertion.component_id` only when the assertion is about a specific element's state (e.g. "success message becomes visible") — leave it null for page/API-level outcomes
- [x] Task 4: Wire `ApplicationModelBuilderActivity` into `DiscoveryWorkflow` (AC: 1)
  - [x] **Read `packages/workflows/src/workflows/discovery_workflow.py` fully before starting this task — see Dev Notes for a critical discrepancy between what Story 2.6's own File List claims and what the file actually contains.** As of this story, `DiscoveryWorkflow.run` dispatches only `DiscoveryActivity`; `InferenceActivity` is *not* currently chained (its docstring says so explicitly, and the code confirms it — despite Story 2.6's File List saying otherwise)
  - [x] Add a second `workflow.execute_activity` call, dispatching `ApplicationModelBuilderActivity` when `discovery_result.status == "complete"` (same gating condition Story 2.6's Task 3 already specified for `InferenceActivity` — a `failed` run has nothing worth modeling)
  - [x] Do **not** also wire `InferenceActivity` here — that remains Story 2.6's task, dispatched as a *third* activity, after this one, once Story 2.6's own rework lands. Leave a comment at the end of this dispatch chain naming `InferenceActivity` as the next link, matching the existing docstring's forward-reference style
- [x] Task 5: Verify end-to-end and record evidence (AC: 1-5)
  - [x] Two `Page` rows captured with different literal URLs that normalize to the same `url_template` (e.g. `/customers/123`, `/customers/456`) resolve to one canonical `Page` after this Activity runs, the other's `merged_into_id` set to it
  - [x] Re-running Discovery against the same Application (a second `DiscoveryRun`) that revisits an already-known page does **not** create a second canonical `Page` for it — the new run's raw `Page` row gets `merged_into_id` pointing at the *existing* canonical row from the earlier run
  - [x] At least one button/link `Component` and at least one form-field `Component` each have more than one `ComponentLocator` row (a preferred + at least one fallback); every `FormField` that has a derived `Component` shows its `component_id` set
  - [x] `DiscoveryWorkflow` dispatches `ApplicationModelBuilderActivity` only when `DiscoveryActivity` returns `status=complete`, never on `failed`
  - [x] Re-running this Activity against the same Discovery Run twice (simulating a Temporal retry) does not create duplicate `Component` rows or flip-flop `merged_into_id` values (AD-9)
  - [x] No test or code path has `DiscoveryActivity` resolve a merge or write `Component`/`ComponentLocator`/`Assertion`, or `InferenceActivity` write to any Application Model table beyond `journey_id` attribution (AD-14)

## Dev Notes

- **Critical, load-bearing discrepancy found while reading `discovery_workflow.py` for this story**: Story 2.6's own Dev Agent Record / File List (2026-07-17, written when that story was still numbered 2.5) claims *"`DiscoveryWorkflow.run` now conditionally dispatches `InferenceActivity`"* — but the file as it exists today does **not** do this. Its docstring explicitly states `InferenceActivity` was deliberately left disconnected ("Re-wire with a second `workflow.execute_activity` call when 2.5 is ready to be part of this workflow again" — the code comment predates this renumbering and still says "2.5," meaning what is now Story 2.6), and `DiscoveryWorkflow.run`'s body only calls `DiscoveryActivity`. This actually simplifies this story's wiring: there is no existing Inference dispatch to displace — this story adds the *second* dispatch (Model Builder), and Story 2.6's rework adds the *third* (Inference), in that order. Do not "fix" the workflow to match Story 2.6's stale File List claim; trust the code and the docstring, not the completion note.
- **This story's scope shifted significantly after its first draft** (see `sprint-change-proposal-2026-07-18.md`'s follow-up correction): originally scoped as "transform generic `Evidence` into structured entities." Now that Story 2.2 writes typed rows directly, this story's actual job is narrower and different in kind: **merge/dedup + a small amount of derivation**, not a JSONB-to-structured transform. Don't reintroduce a transform step that re-parses raw data Story 2.2 already typed correctly.
- **Module vs. Capability is resolved, not open**: the Application Model's page-grouping concept reuses `Capability` (`packages/domain/src/domain/capability.py`) — no new `Module` entity.
- **"Crawl Sessions" (from the original pitch) already exists as `DiscoveryRun`** — no new entity needed for it either.
- **Cross-run merging is the whole point of "reusable"**: a naive implementation might only dedup *within* the current run's own captures, missing the actual requirement — a Page seen in a *previous* Discovery Run against the same Application must also be matched and reused. Query by `application_id` across all Discovery Runs when resolving canonical rows, not just `discovery_run_id`.
- **`merged_into_id` lives only on `Page`, `Form`, `ApiEndpoint`** (per Story 2.2's schema) — `Action` and `PageTransition` don't have it; `Action` rows stay as raw historical detail (Component is the deduped unit built from them), and `PageTransition` dedup happens implicitly once its `from_page_id`/`to_page_id` resolve to canonical Pages (two edges between the same canonical pair should collapse to one row — a find-or-create by (`from_page_id`, `to_page_id`) once both are canonical, not a `merged_into_id` scheme of its own).
- **AD-14's writer boundaries are the one invariant this story must not violate under any refactor**: this Activity is the only writer of `merged_into_id` and of `Component`/`ComponentLocator`/`Assertion`. `DiscoveryActivity` (Story 2.2) only ever writes new rows with `merged_into_id=null`; `InferenceActivity` (Story 2.6) only ever reads canonical rows and writes `journey_id` onto them.
- **This story's Activity does not yet feed `InferenceActivity`** — that consumption wiring is explicitly Story 2.6's task (see epics.md#Story 2.6), not this story's. Do not implement `InferenceActivity` reading these tables here; that would duplicate Story 2.6's work and create a merge conflict between the two stories' implementations.

### Project Structure Notes

- Adds `Component`, `ComponentLocator`, `Assertion` to `packages/domain` (plus `merged_into_id` columns on `Page`/`Form`/`ApiEndpoint` if Story 2.2 didn't already add them), a new `model_builder.py` module + `ApplicationModelBuilderActivity` registration in `apps/workers/discovery`, and a new dispatch in `packages/workflows/src/workflows/discovery_workflow.py`. No new top-level directories beyond Story 1.1's Structural Seed.
- **Depends on Story 2.2's rework (typed capture, not Evidence) and Story 2.4 (session expiry) being in place** — this Activity only runs when `DiscoveryActivity` returns `status=complete`, and reads whatever typed rows Story 2.2 actually produces (including, ideally, the selector-capture dependency flagged in Story 2.2's own Dev Notes). Story 2.6's rework is a *sibling*, not a prerequisite — it depends on this story's output, not the reverse, but both are being reworked in the same change and should land together to avoid one being unusable without the other.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5: Application Model Builder]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md §4.2 — FR-30]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-8, #AD-14, #AD-15, #Module Map — Application Model Builder row]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-18.md]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the typed rows this story reads, and its own crawl-optimization + locator-capture rework]
- [Source: _bmad-output/implementation-artifacts/2-6-ai-journey-capability-inference-from-application-model.md — the sibling story that consumes this one's output]
- [Source: packages/workflows/src/workflows/discovery_workflow.py — current dispatch chain; see Dev Notes for the discrepancy this story must resolve correctly]
- [Source: apps/workers/discovery/src/discovery_worker/activities.py — where `ApplicationModelBuilderActivity` is registered, alongside `discovery_activity`/`inference_activity`]

## Previous Story Intelligence

By strict numbering, this story's immediate predecessor is **Story 2.2 (Autonomous Exploration Captures the Application Model)** — check its actual `packages/domain` schema (`Page`/`Form`/`Action`/`ApiEndpoint`/`PageTransition` field names, and whether it already added `merged_into_id` columns) before writing this story's migration, rather than assuming the field list above is final. Story 2.4 (Session Expiry Handling, `review`) establishes the dispatch condition this story's Task 4 depends on: `DiscoveryRun.status` is `running | complete | failed`.

The engineering patterns below are drawn from Story 2.6 (AI Journey/Capability Inference — implemented 2026-07-17 under its original number, 2.5, before renumbering), genuinely useful prior art regardless of story order:
- **Alembic FK-constraint naming must be explicit** — Story 2.6 hit `op.drop_constraint(None, ...)` not resolving without a named constraint; name every FK constraint this story's migration adds the same way.
- **`InferenceActivity` fetches its input by `discovery_run_id` and calls the AI provider** directly, in `activities.py` — this story's `ApplicationModelBuilderActivity` should follow the same "new activity function alongside the existing ones in `activities.py`, real logic in its own module" split already established for `discovery_activity`/`crawler.py` and `inference_activity`/`identity_key.py`.
- **Idempotency-under-retry (AD-9) is a recurring, explicitly-tested requirement** in this codebase (see Story 2.6's `identity_key`-keyed find-or-create) — apply the same discipline here (Task 2's note on this Activity's own idempotency).

## Git Intelligence Summary

Recent commits (`f420c7d "2.1 to 2.5 has been implmented."`, `48b6499 "1-4 completed, Complete Epic 1"`) confirm Epic 1 is fully committed and Epic 2's Stories 2.1-2.5 (under the numbering at the time of that commit — now 2.1-2.4 and 2.6, after this renumbering) landed together in one commit. No commit yet reflects this Sprint Change Proposal's rework (2.2 reworked twice — crawl-optimization then Evidence removal; 2.6 renumbered from 2.5 and reverted; this story added as 2.5) — expect the next commit touching Epic 2 to cover this story plus 2.2/2.6's rework together, per the proposal's framing that these are one coherent unit of work.

## Latest Technical Notes

- No new library dependencies are anticipated for this story beyond what `apps/workers/discovery` already has (SQLModel, the existing Postgres/Alembic stack) — the merge/derivation logic is plain Python/SQL over already-captured, already-typed data.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
- 2026-07-18 [this session] — Implemented from scratch: `Component`/`ComponentLocator`/`Assertion`
  domain entities plus `FormField.component_id` (`packages/domain`), folded into migration
  `d1e9a4b6f2c3` alongside Story 2.2's typed tables. `model_builder.py`
  (`apps/workers/discovery/src/discovery_worker`): `merge_pages`/`merge_forms`/
  `merge_api_endpoints` resolve canonical rows via `url_template` grouping (idempotent — re-resolves
  by querying current state, never assumes first run), `dedupe_page_transitions` collapses duplicate
  edges once endpoints are canonical, `derive_components_and_assertions` builds button/link and
  form-field Components with preferred+fallback `ComponentLocator`s and derives `Assertion`s from
  canonical transitions/API calls. `ApplicationModelBuilderActivity` registered in `activities.py`
  and wired as the second dispatch in `DiscoveryWorkflow` (after `DiscoveryActivity`, gated on
  `status=complete`). Verified end-to-end against real Postgres: cross-run Page merge, idempotent
  re-run (no duplicate Components, no merged_into_id flip-flop), Component/ComponentLocator
  derivation for both button and form-field elements. `ruff`/`pyright` clean. Status moved to
  `review`.
