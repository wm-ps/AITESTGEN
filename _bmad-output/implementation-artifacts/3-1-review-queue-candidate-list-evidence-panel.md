# Story 3.1: Discover Journeys — Candidate List & Detail Panel

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Renamed/updated 2026-07-15 (was "Review Queue — Candidate List & Evidence Panel"): this is now the pipeline's step 2 ("Discover Journeys"), and folds in FR-23 (Journey detail, relocated from the deferred Epic 6 Journey Explorer). No persistent nav rail exists — see Story 1.2. See `sprint-change-proposal-2026-07-15.md`.*

## Story

As a reviewer,
I want to see all candidate Journeys in a list and inspect the discovered detail behind any one of them,
so that I can judge each inference against what discovery actually captured.

## Acceptance Criteria

1. **Given** candidate Journeys exist for an Application, **when** the reviewer reaches the Discover Journeys pipeline step, **then** each candidate row shows its business-language name and a step count. [Source: epics.md#Story 3.1; FR-9]
2. Selecting a row loads that Journey's discovered step-by-step detail — each step's route, method, and stage badge (e.g. "Login," "MFA Verification") — into a detail panel on the right, replacing any prior selection. [Source: epics.md#Story 3.1; FR-23 (relocated 2026-07-15)]
3. No confidence, risk, or importance score/percentage/star/flag appears anywhere on a candidate row or in the detail panel. [Source: UX-DR21]

**`[RESOLVED 2026-07-15]`** `New`/`Dupe` badges and the live pending-count indicator are confirmed **cut** — neither is built. The detail panel **is** sticky on scroll at 340px width; its content changes only when the reviewer selects a different candidate row, never as a side effect of scrolling. [Source: epics.md#Story 3.1]

## Tasks / Subtasks

- [ ] Task 1: Build the Discover Journeys read endpoint (AC: 1)
  - [ ] `GET` endpoint returning candidate (`status="candidate"`) Journeys for an Application, Organization-scoped via Story 1.2's middleware, each with: business-language name and step count. No `New`/`Dupe` distinction is returned — that badge is cut (see AC gap-resolution note above)
  - [ ] **Capabilities are not independently listed as candidate rows.** Neither `DESIGN.md` nor `EXPERIENCE.md` describes a Capability-specific row, badge, or panel anywhere in this pattern — only Journey rows. This resolves an apparent tension with FR-9's "Journeys and Capabilities are presented to a human reviewer" wording: Capability curation happens implicitly through its Journeys, not as a separately reviewed queue item. `[UPDATED 2026-07-15]` There is no Capability "approval state" to derive anymore — Capability, like Journey, is simply `candidate` or `deleted` (Story 2.5), part of the Trusted Knowledge Model from the moment it's discovered
- [ ] Task 2: Build the Journey step-detail read endpoint (AC: 2)
  - [ ] `[FIX 2026-07-20]` `GET` endpoint returning a Journey's discovered step-by-step detail — each step's route, method, and stage badge (e.g. "Login," "MFA Verification") — derived from **`JourneyStep` rows for the Journey, ordered by `step_order`**, each carrying its `stage_label` and joining through to its underlying canonical `Page`/`Form`/`ApiEndpoint`/`Component` row for route/method detail, attributed by Story 2.6's `InferenceActivity` (FR-23, relocated from the deferred Journey Explorer). *Corrected alongside Story 2.6's rework — this previously said "derived from the `Evidence` rows where `journey_id` matches, attributed by Story 2.5's `InferenceActivity`," which was doubly stale: the `Evidence` table was removed by Story 2.2's 2026-07-18 rework, and `InferenceActivity` is Story 2.6 (Story 2.5 is the Application Model Builder), not Story 2.5.*
- [ ] Task 3: Build the Discover Journeys screen (AC: 1-3)
  - [ ] Two-pane layout: scannable candidate-row list (left) + a sticky-on-scroll detail panel (right), fixed at 340px width — confirmed 2026-07-15, no longer a `[GAP]`. The panel's content changes only when the reviewer selects a different candidate row; scrolling the list never changes what the panel shows
  - [ ] Each row: business-language name and step count only, per `DESIGN.md`'s badge component conventions (tinted wash + saturated text, same hue — never solid fill) for any badge that *does* appear elsewhere on the row (none currently specified for this row beyond the step count)
  - [ ] Selecting a row replaces the detail panel's content with that Journey's step-by-step detail — each step's route, method (rendered in monospace where appropriate), and stage badge — not a raw evidence-log dump
  - [ ] **Hard constraint, not a style preference:** no confidence/risk/importance score, percentage, star, or priority flag anywhere on a row or in the detail panel — this is called out explicitly (UX-DR21) as a deliberate product cut, re-affirmed during PRD finalization, not something to "helpfully" add later
  - [ ] Application-name breadcrumb *is* shown on this screen (Discover Journeys is Application-scoped), consistent with the rule established for Discovery Progress in Story 2.1
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] A candidate Journey shows its business-language name and step count; no `New`/`Dupe` badge or live pending-count indicator appears anywhere on the screen — a deliberate negative check, not just a positive functional test
  - [ ] Selecting different rows correctly replaces (not stacks) the detail panel's content, showing route/method/stage-badge step detail
  - [ ] Scrolling the candidate list keeps the detail panel fixed in view (sticky) and never changes its content — only selecting a different row does
  - [ ] No confidence/risk/importance UI element exists anywhere on this screen — a deliberate negative check worth including in review, not just a positive functional test

## Dev Notes

- **Capability-as-independently-reviewed-item is a real ambiguity in FR-9 vs. the UX spine, resolved here in favor of the UX spine** (Capability curation is derived, not a separate queue row) since the UX documents were built with much more granular attention to exactly this screen than the PRD's one-line FR. If this resolution turns out wrong once Story 3.4's delete logic is actually built, that's worth surfacing back to product, not silently reworking.
- **UX-DR21 (no confidence/risk/importance signal) is one of the two hard, repeatedly-reaffirmed constraints in this entire product** (the other being the no-merge/split/edit rule on Journey curation, Story 3.4's territory — `[UPDATED 2026-07-15]` no longer a "four-action" rule; Approve/Reject are removed, leaving just Rename/Delete) — `EXPERIENCE.md`'s Inspiration & Anti-patterns section names this as a "recurring temptation for 'helpful' UI" to resist at the product-decision level, not just the visual level. Take it seriously in code review.
- **2026-07-15 IA change:** this story was renamed from "Review Queue — Candidate List & Evidence Panel" to "Discover Journeys — Candidate List & Detail Panel" and now also delivers FR-23 (Journey step detail, relocated from the deferred Epic 6 Journey Explorer). There is no persistent nav rail in the current IA (Story 1.2).
- **`[RESOLVED 2026-07-15]` Three previously-flagged gaps are now settled by explicit product decision, not just prototype evidence:** `New`/`Dupe` badges are cut (no same-batch or cross-batch duplicate-flagging UI is built); the live pending-count indicator is cut (its only home, the nav rail, is retired, and no on-screen replacement is being built); and the detail panel is confirmed sticky-on-scroll at 340px, with content that only changes on row selection. This removes the `Journey.duplicate_of_journey_id` field and the corresponding `InferenceActivity` extension that an earlier draft of this story scoped — there is no consumer for that data anymore. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

### Project Structure Notes

- Adds Discover Journeys list and step-detail read endpoints to `apps/api`, and builds the Discover Journeys screen in `apps/web`. No new entities, no changes to `InferenceActivity`, no new top-level directories.
- **Depends on Epic 1 and all of Epic 2 (Stories 1.1–1.5, 2.1–2.5) being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1: Discover Journeys — Candidate List & Detail Panel]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-9]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-13]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — badge, evidence-panel]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Review & Trust Model; #Component Patterns]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — `InferenceActivity` and `identity_key` this story reads from (no changes made to it)]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md — original Story 3.1 gap-resolution decision]

## Previous Story Intelligence

All of Epic 1 and Epic 2 remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 2.5 is implemented, check its File List for `InferenceActivity`'s exact structure and `identity_key` computation before building this story's step-detail endpoint (Task 2) — no changes to `InferenceActivity` itself are needed for this story.

## Latest Technical Notes

No new library decisions — this story builds on the existing FastAPI/SQLModel/React stack.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2026-07-20 — `[FIX]` Task 2's step-detail endpoint description corrected alongside Story 2.6's
  rework (which introduced the `JourneyStep` join entity — ordered, stage-labeled attribution
  rows — replacing the bare `journey_id` FK the old wording assumed): now reads "`JourneyStep`
  rows ordered by `step_order`" instead of the stale, doubly-wrong "`Evidence` rows where
  `journey_id` matches, attributed by Story 2.5's `InferenceActivity`" (the `Evidence` table was
  already removed by Story 2.2's 2026-07-18 rework, and `InferenceActivity` is Story 2.6, not
  2.5). No other part of this story changed; it remains `ready-for-dev`, unimplemented.
