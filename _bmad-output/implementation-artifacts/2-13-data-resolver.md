---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.13: Data Resolver — Structured Input Resolution

*Added per `sprint-change-proposal-2026-07-29.md`. Formalizes and extends the existing generic-value-filling behavior built in Story 2.2.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to reuse real or safely-synthesized data before ever guessing business-specific values,
so that generated coverage uses trustworthy inputs and never fabricates data it shouldn't.

## Acceptance Criteria

1. **Given** an action needing input, **when** resolving a value, **then** the platform tries, in strict order: (a) a value already visible on the current page, (b) a value observed earlier in this Discovery Run, (c) safe synthetic data for a generic field (name/email/description) or a placeholder file for a file-upload widget, (d) if none apply, defers the action to the Blocked Frontier (Story 2.15) rather than guessing business-specific data. [Source: epics.md#Story 2.13; FR-40]
2. **Given** any value is used (including synthetic), **when** the action executes, **then** the value is logged against the run (page/step, value, whether the action fully executed) for later traceability. [Source: FR-40]
3. The Data Resolver is consulted only after the Safety Engine (Story 2.12) has already classified the action Safe or Ambiguous — a Clearly Destructive action never reaches this resolution order at all. [Source: architecture#AD-19]

## Tasks / Subtasks

- [ ] Task 1: Formalize the resolution order as its own module (AC: 1)
  - [ ] New module in `apps/workers/discovery` (e.g. `data_resolver.py`) implementing the four-step order in AC 1, extending (not replacing) Story 2.2's existing generic-value-filling logic (`_GENERIC_VALUES`, quantity-field heuristic, etc.) as step (c)
  - [ ] Step (a): scan the current page's already-captured content (via the Runtime Observer's snapshot) for a plausibly reusable value matching the field's type/name
  - [ ] Step (b): check a per-run resolved-value log (this story's own bookkeeping, keyed by field type/name) for a value already used successfully earlier in this run
  - [ ] Step (c): fall back to Story 2.2's existing generic/synthetic value generation for generic fields; for `type="file"` inputs, generate/reuse a small set of safe placeholder files (mirrors Story 2.14's file-upload handling — coordinate module boundaries if both land in the same pass)
  - [ ] Step (d): if the field is judged business-specific (not resolvable by any of the above, and not a recognized generic pattern), return "unresolved" to the Planner, which defers the action (Story 2.15)
- [ ] Task 2: Add the `SyntheticDataEntry` domain entity and logging (AC: 2)
  - [ ] Add `SyntheticDataEntry` (`id`, `application_id` FK, `discovery_run_id` FK, `page_id` nullable FK, `field_name`, `value`, `is_placeholder_file: bool`, `created_at`) to `packages/domain`
  - [ ] Alembic migration
  - [ ] Every value resolved via steps (a)-(c) is logged as a `SyntheticDataEntry` row at the moment the action executes — logged even for steps (a)/(b) (reused values), not only newly-synthesized ones, so the end-of-run report can show a complete picture of what data touched the target application
- [ ] Task 3: Verify end-to-end (AC: 1-3)
  - [ ] A visible claim number on the current page is reused (step a) rather than re-synthesized
  - [ ] A value used successfully on an earlier page in the same run is reused (step b) for a matching field elsewhere
  - [ ] A generic `email`/`name`/`description` field gets a safe synthetic value (step c) and is logged
  - [ ] A field judged business-specific (e.g. "Active Policy Number") returns unresolved and the action defers rather than receiving a fabricated value
  - [ ] Every resolved value, across all four steps, has a corresponding `SyntheticDataEntry` row

## Dev Notes

- **This story formalizes existing behavior, it doesn't invent resolution from scratch** — Story 2.2 already fills forms with generic placeholder values by field type/name. The genuinely new pieces are: the explicit ordered-resolution-with-defer structure (steps a/b never existed before — Story 2.2 goes straight to generic synthesis), and the `SyntheticDataEntry` traceability log.
- **"Business-specific" judgment is a heuristic, not a hard rule** — the boundary between "generic enough to synthesize" and "business-specific, must defer" needs a working default (e.g. a denylist of field-name patterns known to be business-specific: policy/account/order/claim number, SSN-like patterns) and should be treated as tunable, similar to Story 2.10's comparison thresholds, rather than a fixed list that can never be revisited.
- **Logging is for every value, not just synthetic ones** — re-read AC 2 carefully: "whichever value was used (incl. synthetic)" is logged, per the source design document's Section 15.5. Do not scope the log to only step-(c) synthetic values; steps (a)/(b) reused-value cases matter too for a complete "what touched the target app" report.

### Project Structure Notes

- Adds one new domain entity (`SyntheticDataEntry`) and a new `data_resolver.py` module to `apps/workers/discovery`. No new top-level directories.
- Depends on Story 2.11's Planner (this is one of its five specialist questions, consulted after the Safety Engine per AD-19) and Story 2.15's Blocked Frontier for the unresolved/defer destination.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.13]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Section 12 of the source design document]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-19, #AD-20]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the existing generic-value-filling behavior this story extends]

## Previous Story Intelligence

Story 2.2's Dev Notes already document a quantity-field-detection heuristic (fields matching `qty`/`quantity`/`count`/`amount`/`number` get `"1"` instead of a generic string) — this is exactly the kind of field-type-specific rule this story's step (c) should continue to accommodate, not discard.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
