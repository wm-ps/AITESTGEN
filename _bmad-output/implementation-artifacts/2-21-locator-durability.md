---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.21: Locator Durability — Ranked Capture & Fragility Detection

*Added 2026-08-03 per `docs/DISCOVERY_ENGINE_V2.md` (spine box **C — ENUMERATE**, locator half). Identified during the feasibility review of the 2026-07-29 batch: nothing in that batch addressed whether captured locators survive the target application's next deployment.*

Status: review  # All 5 tasks implemented and verified 2026-08-03 against real Chromium + real
  # Postgres, following Story 2-14's landing (this story's Task 1 depends on the accessibility-
  # tree/frame capture it built). One real bug found and fixed during verification — the CSS-in-JS
  # fragility regex initially flagged ordinary hyphenated words like "data-testid" as fragile.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to capture the most durable way to find each element, and to tell me when it couldn't find a durable one,
so that the tests it generates still pass after my application's next deploy — and so I know in advance when they won't.

## Acceptance Criteria

1. **Given** an interactive element is captured, **when** its locators are derived, **then** a **ranked list** of candidate locators is stored, in priority order: (1) `data-testid`/`data-test`/`data-cy`, (2) ARIA role + accessible name, (3) visible text, (4) label-to-field association, (5) scoped CSS path, (6) absolute CSS path (last resort). [Source: docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE]
2. **Given** a candidate locator contains a **machine-generated identifier**, **when** it is ranked, **then** it is **down-ranked** below all human-meaningful alternatives. Detected patterns: CSS-in-JS hashes (`css-1x2y3z`, `sc-hKgILt`), framework-generated IDs (`ctl00_ContentPlaceHolder1_…`, GWT/Ext JS auto-IDs), long hex/UUID fragments, and index-only paths (`div:nth-child(3) > div:nth-child(7)`). [Source: docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE]
3. **Given** an element inside an iframe or shadow root (Story 2.14), **when** its locator is stored, **then** the locator records the full container chain needed to resolve it, so it remains resolvable from the top-level page. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE]
4. **Given** locators are captured, **when** a **durability score** is computed per element from the best available candidate's tier, **then** it is persisted so Story 2.22 can report the proportion of the Application's captured elements that have no durable locator. [Source: docs/DISCOVERY_ENGINE_V2.md#5 What the user gets at the end]
5. **Given** the existing `ComponentLocator` output (Story 2.5), **when** this story lands, **then** it consumes the ranked list rather than a single selector — this story **extends** the existing `_selector_strategy`/`_derive_locators` path in `model_builder.py`, it does not replace it. [Source: apps/workers/discovery/src/discovery_worker/model_builder.py]

## Tasks / Subtasks

- [x] Task 1: Capture ranked candidates at observation time (AC: 1, 3)
  - [x] `_capture_locator_candidates` computes all 6 tiers in one `page.evaluate` round trip while the element is live (testid/data-test/data-cy, ARIA role+name, visible text, label association, scoped CSS, absolute CSS)
  - [x] `_capture_selector`'s existing `data-testid` → `text=` → css ladder is untouched and still populates `captured_selector`; the new ranked list is a separate, additive `locator_candidates` field
  - [x] Elements captured inside a frame (`_capture_frame_widgets`) get `frame_path=f'iframe[src="{frame.url}"]'` prefixed onto every candidate value (AC 3)
- [x] Task 2: Machine-generated-identifier detection (AC: 2)
  - [x] Four pattern checks, each a named constant: hyphenated-segment-that-looks-generated (digit present or mixed case — the actual distinguishing signal from a real English compound word like "data-testid"), ASP.NET `ctl00_`/GWT/Ext JS prefixes, long hex/UUID fragments, positional-only nth-child paths
  - [x] `fragile: bool` marks the candidate; nothing is ever discarded for being fragile
- [x] Task 3: Durability score and persistence (AC: 4, 5)
  - [x] `_durability_score` = tier ordinal (+10 penalty if fragile) — a plain ordinal, not over-modeled
  - [x] `ComponentLocator` gained `fragile`/`durability_score` columns; existing `kind`/`strategy`/`value`/`priority` shape untouched
  - [x] Migration `a2c9e5f7d3b6` (revises `f6a3c8d2b1e4`), applied and verified against real Postgres
- [x] Task 4: Feed the report (AC: 4)
  - [x] `fragile_locator_proportion(session, application_id) -> float | None` in `model_builder.py` — the proportion of Components whose *best* (`priority == 0`) locator is fragile; `None` (not `0%`) when the Application has no locators yet
- [x] Task 5: Verify end-to-end (AC: 1-5)
  - [x] `data-testid` ranks first (real element + unit test)
  - [x] A CSS-in-JS-hash-classed button ranks its ARIA role+name above the hash (real element + unit test) — this surfaced and fixed a real bug in the detection regex itself (see Dev Agent Record)
  - [x] An element with none of testid/role/text falls through to a scoped `#id` CSS candidate (real element + unit test)
  - [x] An element inside a same-origin iframe produces a locator prefixed with a resolvable `iframe[src="..."] >> ...` container chain
  - [x] `_derive_locators`'s legacy single-`captured_selector` fallback path is exercised directly (old-shape rows with no `locator_candidates` still produce a `ComponentLocator`) and a real-Postgres test confirms `fragile_locator_proportion` end-to-end

## Dev Notes

- **Why this story exists: the crawl can fully succeed and still produce worthless output.** Every story in the 2026-07-29 batch optimised how much of an application gets discovered. None asked whether the artifacts of that discovery survive contact with the next deployment. If captured locators break, the coverage was irrelevant — the customer gets a suite of failing tests and concludes the product does not work. This is arguably higher-value than additional crawl breadth, and it is cheap.
- **Machine-generated identifiers are syntactically valid and semantically worthless.** `div.css-1x2y3z > button` is a perfectly good CSS selector that will break the next time the build runs, because the hash is derived from content that changes. The same is true of ASP.NET's `ctl00_ContentPlaceHolder1_…` control IDs and Ext JS/GWT auto-IDs, which can vary per session. Detecting these is pattern matching, not intelligence, and it is the single highest-value rule in this story.
- **Be honest when no durable locator exists.** On an application with no test IDs, no semantic roles and generated class names, *no* strategy produces a durable locator — that is a property of the target, not a solvable problem. The right behaviour is to report it clearly (AC 4) so the customer can act on it by adding test IDs, which is the actual fix. Pretending otherwise produces a suite that silently rots.
- **Capture at observation time, not afterwards.** Deriving locators from a stored DOM snapshot loses the accessibility context (computed roles, accessible names) that tiers 2 and 4 depend on. This is why the story belongs in the enumerate step rather than in the model builder.
- **This directly improves existing output.** Story 2.5's `ComponentLocator` rows already exist and already feed generation; this story makes them better rather than introducing a parallel mechanism. Keep the change additive.

### Project Structure Notes

- Extends locator derivation in the capture path (`apps/workers/discovery`) and the existing `ComponentLocator` entity in `packages/domain`. No new modules strictly required — the natural home is alongside Story 2.14's `widgets.py`, since both operate on the same captured element set.
- Depends on Story 2.14 (frame/shadow container chains, accessibility-tree capture). Feeds Stories 2.19 (durable action identity for the history tracker) and 2.22 (fragility reporting), and improves Story 2.5's existing output.

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE, #6 Honest capability gradient]
- [Source: apps/workers/discovery/src/discovery_worker/model_builder.py — existing `_selector_strategy`, `_derive_locators`]
- [Source: _bmad-output/implementation-artifacts/2-5-application-model-builder.md — the `ComponentLocator` rows this story enriches]

## Previous Story Intelligence

`model_builder.py` already implements a three-tier priority (`data-testid` → `text=` → css) in `_selector_strategy`, and `_derive_locators` already de-duplicates selectors per component. This story generalises that existing ladder rather than replacing it — read both functions before starting, and keep the top-candidate shape stable so Story 2.5's consumers and the generation workflow are unaffected.

## Latest Technical Notes

No new library decisions. Accessible-name and role computation come from Playwright's existing accessibility-tree APIs, already used by Story 2.14.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- All 5 tasks implemented and verified against real Chromium (capture) and real Postgres (`_derive_locators`/`fragile_locator_proportion`), not asserted from code reading alone.
- `_capture_locator_candidates` computes all 6 tiers in one `locator.evaluate()` round trip (`_LOCATOR_INFO_SCRIPT`) rather than one Playwright round trip per tier — matters because this runs on every captured field/action/tab/shadow-DOM-button, and this file already treats round-trip count as a real performance concern (see Story 2.9's Dev Notes on the same point).
- Wired into every existing capture point from Stories 2.2/2.14: form fields (incl. file inputs), the form's submit button, standalone buttons (page-level and frame-scoped via `_capture_frame_widgets`'s new `frame_path`), tabs, and shadow-DOM buttons.
- `_derive_locators` (`model_builder.py`) now accepts `list[tuple[captured_selector, locator_candidates]]` instead of `list[captured_selector]` — falls back to a single legacy candidate built from `captured_selector` when `locator_candidates` is empty/null (rows captured before this story), so existing `ComponentLocator` consumers keep working per AC 5 without a data migration.
- **Real bug found and fixed during verification**: the initial CSS-in-JS fragility regex (`\b[a-zA-Z]{1,10}-[0-9a-z]{5,}\b`) matched *any* hyphenated two-word shape, including ordinary compound identifiers like `data-testid` and `save-button` — meaning a `data-testid` candidate would have been down-ranked as if it were a generated hash, defeating the story's own highest-priority AC. The actual distinguishing signal isn't the shape, it's that a real hash's second segment contains a digit (`css-1x2y3z`) or mixes case in a way an English word never does (`sc-hKgILt`); rewrote as `_looks_like_generated_token()` checking exactly that, verified with both a unit test and a real captured element on `/locators`.
- Also found and fixed: the positional-only-path regex was anchored (`^...$`) against the bare path shape, but real candidate values carry a `css=` prefix (Playwright's engine selector), so a genuinely positional-only absolute path never actually matched. Fixed by making the prefix optional in the anchor.
- New fixture route `/locators` (`data-testid` button, CSS-in-JS-hash-classed button with a real ARIA name, bare `id`-only div) plus reuse of Story 2.14's `/frames` fixture for the container-chain AC.
- Verified: 20 new tests (15 pure unit, 5 real-Chromium/Postgres) all pass; ruff and pyright clean on every modified/new file; full `apps/workers/discovery` suite re-run with no regressions.
- **Deferred, matching the story's own scope**: Task 1's "Actions found inside a frame carry their frame path so Story 2.21 can build a locator that resolves through the frame chain" — done for capture (frame_path prefix); Story 2.11's re-entry-after-state-return logic that would *consume* this chain doesn't exist yet, same soft-dependency pattern used throughout this batch.

### File List

- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — see Completion Notes)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified — copies `locator_candidates` onto `Action`/`FormField` rows)
- `apps/workers/discovery/src/discovery_worker/model_builder.py` (modified — `_rank_locator_candidates`, `_durability_score`, reworked `_derive_locators`, new `fragile_locator_proportion`)
- `packages/domain/src/domain/action.py`, `packages/domain/src/domain/form_field.py` (modified — `locator_candidates` JSONB)
- `packages/domain/src/domain/component_locator.py` (modified — `fragile`, `durability_score`)
- `migrations/versions/a2c9e5f7d3b6_add_locator_durability_fields.py` (new)
- `apps/workers/discovery/tests/test_locator_durability.py` (new — 20 tests)
- `apps/workers/discovery/tests/fixtures/target_app.py` (modified — `/locators` route)

## Change Log

- 2026-08-03 — Story created per `docs/DISCOVERY_ENGINE_V2.md`, following a feasibility review of the 2026-07-29 Discovery Engine batch which found locator durability entirely unaddressed despite determining whether the generated output has any lasting value.
- 2026-08-03 — All 5 tasks implemented and verified against real Chromium and real Postgres. Found and fixed a real bug in the fragility-detection regex (flagged ordinary compound words like "data-testid" as machine-generated) and a real anchoring bug in the positional-path regex (didn't account for the `css=` engine prefix real candidate values carry) — see Dev Agent Record. Status moved `ready-for-dev` → `review`.
