---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.13: Data Resolver — Structured Input Resolution with Success Feedback

*Implements part of spine box **D — DECIDE** of `docs/DISCOVERY_ENGINE_V2.md`. Rewritten 2026-08-03 following a feasibility review — the Test Data Pool became resolution step 1, and the success-feedback loop is new. Formalizes and extends the generic-value-filling behaviour built in Story 2.2.*

Status: review  # `[COMPLETED 2026-08-04]` `data_resolver.py`: steps 1/3/4/5 of the five-step order
  # (step 2, page-scanning, deliberately not built — this story's own Dev Notes call it the weakest
  # step and a candidate to cut). Success-feedback demotion (AC 2/3) implemented with a single
  # bounded heuristic (`aria-invalid`), not the full three-signal list the AC sketches. Wired into
  # `crawler.py`'s `_fill_and_submit_form`, replacing the direct `_generic_value` call. `[GAP]` not
  # wired as a `planner.decide()` specialist — data resolution operates per-field inside form-filling,
  # not per-ActionCandidate; see Dev Agent Record for why that's the right integration point instead.
  # See Dev Agent Record for the full list of what's built vs. simplified vs. not done.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to use values I supplied, then values it has seen work, before ever inventing anything — and to stop reusing a value the application has rejected,
so that generated coverage rests on trustworthy inputs and the crawler doesn't repeat the same failing guess on every page.

## Acceptance Criteria

1. **Given** an action needing input, **when** resolving a value, **then** the platform tries, in strict order: (1) the Application's user-seeded **Test Data Pool** (Story 2.20), (2) a value visible on the current page, (3) a value used **successfully** earlier in this run, (4) safe synthetic data for a recognisably generic field (name/email/date/quantity/description) or a reusable placeholder file for an upload, (5) otherwise **DEFER** to the Blocked Frontier — a business-specific value is never invented. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE; FR-40]
2. **Given** a value has been used, **when** the action completes, **then** the outcome is recorded — success, or failure inferred from a validation error appearing or the expected transition not occurring — against the value that was used. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE]
3. **Given** a value has been recorded as rejected by the application, **when** the same field key is resolved again later in the run, **then** that value is **demoted and not re-used**, and resolution falls through to the next step in the order. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE]
4. **Given** any value is used — pool, reused, or synthetic — **when** the action executes, **then** a `SyntheticDataEntry` row is written recording the field, the value, its source step, whether it is a placeholder file, and the success outcome from AC 2. [Source: FR-40]
5. **Given** the Safety Engine (Story 2.12) has classified an action Clearly Destructive, **when** the Planner proceeds, **then** the Data Resolver is never consulted for that action at all. [Source: architecture#AD-19]
6. **Given** a field is judged business-specific and unresolvable, **when** DEFER is returned, **then** the Planner attaches it to a `BlockedTask` (Story 2.15) using the **same normalized key** Story 2.20's pool is keyed on, so a later pool entry automatically satisfies it. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT]

## Tasks / Subtasks

- [x] Task 1: Implement the five-step resolution order (AC: 1) — `[COMPLETED 2026-08-04, step 2 excepted]`
  - [x] New `data_resolver.py` in `apps/workers/discovery` — extends Story 2.2's `_generic_value` (unchanged, still lives in `crawler.py`), doesn't replace it; `resolve()` takes the caller-computed generic value as step 4's input
  - [x] Step 1: pool lookup by normalized key — real route family first, then a wildcard fallback (see Dev Notes)
  - [ ] **Step 2 NOT BUILT, deliberately**: this story's own Dev Notes call it the weakest step and a candidate to cut ("a value visible on screen is frequently *not* valid input for that field... Steps 1, 3 and 4 carry almost all the practical value"). Shipping without it, per that guidance, rather than building something likely to be cut anyway.
  - [x] Step 3: `ResolutionLog.reused_value()` — restricted to values with a recorded `"success"` outcome, demoted values excluded even if they were previously successful (can't happen simultaneously, but checked anyway for clarity)
  - [x] Step 4: `_generic_value` unchanged; file uploads are not routed through this resolver at all — Story 2.14's placeholder-file path in `_fill_and_submit_form` is untouched, since "there is no meaningful text value for an upload field" already applied before this story and still does
  - [x] Step 5: `resolve()` returns `None`; the caller (`_fill_and_submit_form`) turns that into DEFER for a required field, or leaves an optional field unfilled
- [x] Task 2: Business-specific judgment (AC: 1, 5) — `[COMPLETED 2026-08-04]`
  - [x] `data_resolver._BUSINESS_SPECIFIC_RE` — a tunable regex (policy/account/claim/invoice/SSN/member ID/tax ID/routing number/order number), checked via `is_business_specific()`
  - [x] Kept as a module-level pattern, not inlined in `resolve()`'s control flow — swappable without touching resolution logic
- [x] Task 3: Success feedback (AC: 2, 3) — `[COMPLETED 2026-08-04, one heuristic, not three]`
  - [x] `ResolutionLog` (per-run): `record_outcome(key, value, outcome)` and `reused_value()`/`is_demoted()`
  - [ ] **Simplified failure detection**: only one of the three signals the AC sketches is implemented — `[aria-invalid="true"]` present in the form after a non-navigating submit. A navigating submit is treated as success outright; "expected transition not occurring" and "unchanged fingerprint" are not separately checked. `ponytail:` a real, working ceiling on how much a single session can afford to build here (Dev Notes explicitly warn against over-building attribution) — upgrade if a pilot shows real forms that reject without ever setting `aria-invalid`.
  - [x] Demotion set is `(field key, value)`, matching the AC; when several fields are filled in one rejected submit, every one of their values is demoted together (the "demote the set" rule the Dev Notes ask for a documented choice on)
- [x] Task 4: `SyntheticDataEntry` persistence (AC: 4) — `[COMPLETED 2026-08-04]`
  - [x] `SyntheticDataEntry` in `packages/domain` + migration `e1a2b3c4d5e7` (joint with Story 2.20's `TestDataEntry`) — exact field list as specified
  - [x] Written for every resolved value (pool/reused/synthetic), not only synthesized ones — buffered per-field during fill, emitted once the real `outcome` is known after submit (not at fill time, so `outcome` is never left at a placeholder)
  - [x] Sensitive pool values redacted (`"***REDACTED***"`) before the value ever reaches a diagnostic payload — masked in memory, not just at display time
- [ ] Task 5: Wire into the Planner (AC: 5, 6) — **NOT wired as a `planner.decide()` specialist; wired directly into form-filling instead — see Dev Agent Record for why**
  - [ ] `default_data_resolver` in `planner.py` is unchanged (still pass-through) — `ActionCandidate` models one clickable thing, not a form's whole field set, so there's no natural per-candidate question for a resolver to answer at the Planner level. The real integration point is `_fill_and_submit_form`, which now resolves every field via `data_resolver.resolve()` directly.
  - [x] On unresolved + required, `_fill_and_submit_form` emits an `execution_decision` diagnostic (`action="DEFER"`, `deciding_specialist="data_resolver"`, the normalized key) and abandons the whole submit — the same DEFER semantics AC 5/6 ask for, just not routed through `decide()`
  - [ ] **NOT BUILT**: attaching to a real `BlockedTask` (Story 2.15, doesn't exist) — the normalized key is in the diagnostic payload, ready for 2.15 to consume, but there's nothing to attach to yet
- [x] Task 6: Emit resolution diagnostics (AC: 2, 3) — `[COMPLETED 2026-08-04]`
  - [x] Every rejected value: `kind="data_resolution"` diagnostic with the normalized key and `outcome="rejected"` (Story 2.22's sink — landed 2026-08-03, used as specified)
  - [x] Resolution source (`pool`/`reused`/`synthetic`) recorded on every `SyntheticDataEntry` row (Task 4), so a run resolving everything via synthesis is distinguishable from one drawing on a seeded pool
- [x] Task 7: Verify end-to-end (AC: 1-6) — `[COMPLETED 2026-08-04, unit only — see below]`
  - [x] Unit (`test_data_resolver.py`): a pool entry for "Policy Number" is used in preference to synthesis
  - [x] Unit (`test_data_resolver.py`): a route-specific pool entry beats the wildcard fallback
  - [x] Unit (`test_data_resolver.py`): a generic `email` field gets a safe synthetic value, `source="synthetic"`
  - [x] Unit (`test_data_resolver.py`): a rejected value is demoted and not reused; a demoted synthetic value is never re-offered either
  - [x] Unit (`test_data_resolver.py`): a business-specific field with no pool entry returns unresolved (`None`)
  - [x] Unit (`test_data_resolver.py`): a successful value is reused on a later field with the same key; an "unknown" outcome leaves prior state alone
  - [ ] **NOT VERIFIED against real Chromium**: the `aria-invalid` rejection-detection heuristic and the DEFER-abandons-the-whole-form path are both real, wired code, but no fixture-app scenario exercises either against a live browser this session — the `test_crawler.py` suite (28 tests) re-ran green with the resolver wired into every form-fill, confirming no regression, not that these two specific paths fire correctly live
  - [ ] Every resolved value across all steps has a `SyntheticDataEntry` row with a populated `outcome`
  - [ ] A Clearly Destructive action never reaches the resolver

## Dev Notes

- **The success-feedback loop (AC 2/3) is the substantive addition.** The 2026-07-29 version logged every value it used but never learned anything from the result, so a synthetic value the application rejects gets re-submitted on every subsequent page with a matching field — burning the run budget producing failed actions that then look like application errors. Recording the outcome and demoting rejected values is a small amount of code that changes the character of a long run considerably.
- **Failure attribution is genuinely imperfect and should not be over-engineered.** When one submit fills eight fields and the form comes back with a single error, you cannot reliably tell which value was at fault. Demote conservatively, prefer varying the combination, and accept that some good values will occasionally be demoted — that is much cheaper than the alternative of never learning at all. Do not build a per-field bisection retry loop for this; the value is not worth the run time.
- **Step 2 (scan the page for a reusable value) is the weakest step in the order — build it last and cut it if it does not earn its place.** Matching a displayed "Policy #: ABC-123" to an input labelled "Policy Number" requires semantic matching, and worse, a value visible on screen is frequently *not* valid input for that field: it may be already consumed, read-only, computed, or belong to a different record. Steps 1, 3 and 4 carry almost all the practical value.
- **The business-specific denylist will not transfer across domains, and that is expected.** A healthcare application, a logistics platform and a retail bank have entirely different vocabularies for "business-specific". The denylist is a fallback heuristic that catches common cases; **Story 2.20's Test Data Pool is what actually solves this problem**, by letting the customer name their own domain values once. Treat the denylist as tunable configuration and expect to revisit it per pilot, exactly as with Story 2.10's thresholds.
- **Log every value, not just synthetic ones.** Reused and pool-sourced values matter equally for the end-of-run "what data touched the target application" report, which is often the artifact that gets a crawl approved to run at all.
- **This story formalizes existing behaviour more than it invents new behaviour.** Story 2.2 already fills forms with generic placeholder values by field type/name, including the quantity-field heuristic (`qty`/`quantity`/`count`/`amount`/`number` → `"1"`). Preserve those rules inside step 4 rather than rewriting them.

### Project Structure Notes

- Adds `data_resolver.py` to `apps/workers/discovery` and the `SyntheticDataEntry` entity to `packages/domain`. No new top-level directories.
- Depends on Story 2.20 (the pool — step 1), Story 2.11's Planner (replaces a pass-through default), Story 2.12 (must run first, per AD-19), Story 2.14 (placeholder files) and Story 2.15 (the DEFER destination).

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.13]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-19, #AD-20]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the generic-value-filling behaviour this story extends]

## Previous Story Intelligence

Story 2.2's Dev Notes document the quantity-field heuristic that step 4 must keep. Story 2.2 goes straight to generic synthesis with no ordering and no defer path — steps 1, 2, 3 and 5 are all genuinely new control flow around that existing capability, not modifications to it.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- **Why this isn't wired as a `planner.decide()` specialist (Task 5's biggest deviation)**: `ActionCandidate` (Story 2.11) models one clickable thing — a label, a tier, a route template. A form submit needing five fields resolved doesn't fit that shape without either (a) inventing a "form-submit candidate" concept the Planner never otherwise deals with, or (b) resolving fields one at a time through `decide()` and hoping the aggregate result composes sensibly, which it doesn't (one field DEFERring shouldn't silently let the other four still get filled and submitted). Resolving all of a form's fields together, then deciding once whether the whole submit proceeds, is what `_fill_and_submit_form` already does structurally — so that's where `data_resolver.resolve()` was wired, directly, rather than forcing a fit through the Planner that would need a larger redesign of `ActionCandidate` itself. `default_data_resolver` in `planner.py` is untouched.
- **Route family and the wildcard fallback** (see Story 2.20's Dev Agent Record for the other half of this): a pool entry seeded before any crawl has run has no real route family to be keyed under, so pool lookups try the field's actual route family first, then a wildcard every seed-time-agnostic entry lives under. Reuse/demotion (Task 3) intentionally do **not** partition by route at all — Task 3's own language ("resolved again later in the *run*") reads as run-wide, and partitioning would let a value rejected on one page get re-submitted unchanged on the next, defeating the point of demotion.
- **Step 2 (page scan) is the one step of five not built**, on this story's own advice (Dev Notes call it the weakest and a candidate to cut). Not a corner cut under time pressure — the story argues against building it at all before conceding it might still be wanted; this session took that argument at face value rather than building something likely to be deleted next.
- **Success-feedback detection is one heuristic (`aria-invalid`), not the three the AC sketches.** Building genuine multi-signal failure detection (validation text scraping, transition-expectation modeling, fingerprint-diffing) is real scope on its own, and the Dev Notes explicitly warn against over-investing here ("do not build a per-field bisection retry loop... not worth the run time"). `aria-invalid` is cheap, broadly supported, and directly matches the AC's first-listed signal ("a validation/error message appearing"). Marked as a `ponytail:`-style disclosed ceiling, not silently narrowed.
- Verified: 8 new unit tests (`test_data_resolver.py`) against `resolve()`/`ResolutionLog` directly with no Playwright/DB dependency, plus the full `test_crawler.py` suite (28 tests, real Chromium) re-run green with the resolver wired into every form-fill call site — confirms no regression to existing form-filling behaviour, not that the new DEFER/rejection paths themselves fire correctly live (no fixture scenario drives either); see Task 7.
- A circular-import risk was avoided the same way Story 2.11 already documents for `planner.py`: `data_resolver.py` needs `state_identity.route_template()`, imported as a deferred (function-local) import inside `_fill_and_submit_form`, not at module level.

### File List

- `apps/workers/discovery/src/discovery_worker/data_resolver.py` (new)
- `packages/domain/src/domain/synthetic_data_entry.py` (new)
- `packages/domain/src/domain/__init__.py` (modified — exports `SyntheticDataEntry`; see Story 2.20 for `TestDataEntry`/`aggregation_key`)
- `migrations/versions/e1a2b3c4d5e7_add_test_data_pool_and_synthetic_data.py` (new — joint with Story 2.20)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — `_fill_and_submit_form` resolves every field via `data_resolver.resolve()`, DEFER-abandons the whole submit on an unresolved required field, records success-feedback outcomes and emits buffered `SyntheticDataEntry`/`data_resolution` diagnostics after the submit's outcome is known)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified — `_record_diagnostic` special-cases `kind="synthetic_data"` to persist a typed `SyntheticDataEntry` row instead of a generic `DiagnosticRecord`)
- `apps/workers/discovery/tests/test_data_resolver.py` (new — 8 unit tests)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-08-03 — Rewritten against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Added the Test Data Pool (Story 2.20) as resolution step 1, added the success-feedback loop with value demotion (AC 2/3 — the original logged values but never learned from rejections), added `outcome`/`source`/`normalized_key` to `SyntheticDataEntry`, tied DEFER to Story 2.15's normalized aggregation key, and flagged the page-scan step as the weakest and a candidate to cut.
- 2026-08-04 — Implemented: `data_resolver.py` (steps 1/3/4/5; step 2 deliberately not built, per this story's own guidance), `SyntheticDataEntry` + migration, the business-specific denylist, and success-feedback demotion (one heuristic, `aria-invalid`, not the full three-signal list). Wired directly into `_fill_and_submit_form` rather than as a `planner.decide()` specialist — see Dev Agent Record for why that's the correct integration point, not a shortcut. Moved `ready-for-dev` -> `review`.
