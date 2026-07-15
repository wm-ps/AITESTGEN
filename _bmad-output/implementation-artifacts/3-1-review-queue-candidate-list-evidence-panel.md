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

**`[GAP — flagged 2026-07-15]`** `New`/`Dupe` badges, a live pending-count indicator, and sticky-on-scroll behavior for the detail panel were part of the prior revision's spec but were not confirmed present in the current reference prototype. Retained as last-confirmed spec pending re-verification — do not assume they're gone, but don't assume they survived unchanged either. [Source: epics.md#Story 3.1]

## Tasks / Subtasks

- [ ] Task 1: Fill a gap discovered while speccing this story — same-batch duplicate detection was never assigned to a story (AC: 1)
  - [ ] **The `Dupe` badge ("Overlaps {other Journey}") requires knowing, at candidate-creation time, whether a new Journey overlaps another candidate — this was not covered by Story 2.5's AC, which only computed `identity_key` for cross-run re-discovery dedup (AD-13, consumed later by Story 3.5's FR-15 suppression logic).** Same-*batch* duplicate flagging (two candidates from the *same* inference run that the AI awkwardly split) is a distinct concern from cross-*run* dedup, but reuses the same `identity_key` mechanism: two candidates whose `identity_key`s match or substantially overlap are duplicates of each other
  - [ ] Add `Journey.duplicate_of_journey_id` (nullable, self-referencing FK) to `packages/domain`, plus an Alembic migration
  - [ ] Extend `InferenceActivity` (Story 2.5, `apps/workers/discovery`) so that after computing each candidate's `identity_key`, it also checks for a match against (a) other candidates just created in the same batch, and (b) any existing non-`rejected` Journey already on the Application — if found, set `duplicate_of_journey_id` on the newer candidate. This is a small, targeted addition to Story 2.5's already-implemented logic, not a rewrite — flag it clearly when picking up this story so the change to 2.5's file is deliberate, not accidental
- [ ] Task 2: Build the Discover Journeys read endpoint (AC: 1)
  - [ ] `GET` endpoint returning candidate (`status="candidate"`) Journeys for an Application, Organization-scoped via Story 1.2's middleware, each with: business-language name, step count, and (pending the `[GAP]` above) either `New` or (if `duplicate_of_journey_id` is set) the overlapped Journey's name for a `Dupe` badge
  - [ ] **Capabilities are not independently listed as candidate rows.** Neither `DESIGN.md` nor `EXPERIENCE.md` describes a Capability-specific row, badge, or panel anywhere in this pattern — only Journey rows. This resolves an apparent tension with FR-9's "Journeys and Capabilities are presented to a human reviewer" wording: Capability review happens implicitly, derived from its Journeys' approval state, not as a separately reviewed queue item. This derivation mechanism belongs to Story 3.2 (Approve), not here — flagged now so 3.2 doesn't have to rediscover it
- [ ] Task 3: Wire the live pending-count indicator (AC: 1) — **`[GAP]`: no persistent nav rail exists in the current IA (Story 1.2), so there is no nav-rail link to badge; build this as an on-screen indicator instead, and re-verify its exact placement once a fuller prototype export confirms it**
  - [ ] Architecture's Deferred section explicitly leaves this delivery mechanism (client-side refetch/decrement vs. a push channel) to the implementer, with no AD or port involved either way. Client-side refetch/decrement after each triage action is a reasonable default, consistent with the polling approach already used for Story 2.2's live-feed list — a WebSocket/SSE push channel is a valid alternative but not required
- [ ] Task 4: Build the Journey step-detail read endpoint (AC: 2)
  - [ ] `GET` endpoint returning a Journey's discovered step-by-step detail — each step's route, method, and stage badge (e.g. "Login," "MFA Verification") — derived from the `Evidence` rows where `journey_id` matches, attributed by Story 2.5's `InferenceActivity` (FR-23, relocated from the deferred Journey Explorer)
- [ ] Task 5: Build the Discover Journeys screen (AC: 1-3)
  - [ ] Two-pane layout: scannable candidate-row list (left) + a detail panel (right) — **`[GAP]`: whether the panel is sticky-on-scroll and its exact width are unconfirmed in the current prototype; retain the prior 340px/sticky treatment as a reasonable default pending re-verification**
  - [ ] Each row: business-language name, step count, and (pending the `[GAP]` above) a `New` or `Dupe` badge (never both), per `DESIGN.md`'s badge component (tinted wash + saturated text, same hue — never solid fill)
  - [ ] Selecting a row replaces the detail panel's content with that Journey's step-by-step detail — each step's route, method (rendered in monospace where appropriate), and stage badge — not a raw evidence-log dump
  - [ ] **Hard constraint, not a style preference:** no confidence/risk/importance score, percentage, star, or priority flag anywhere on a row or in the detail panel — this is called out explicitly (UX-DR21) as a deliberate product cut, re-affirmed during PRD finalization, not something to "helpfully" add later
  - [ ] Application-name breadcrumb *is* shown on this screen (Discover Journeys is Application-scoped), consistent with the rule established for Discovery Progress in Story 2.1
- [ ] Task 6: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] A candidate Journey shows its business-language name and step count; if the `New`/`Dupe` distinction is confirmed present, one created without an identity-key collision shows `New` and one flagged by Task 1's logic shows `Dupe` naming the correct overlapped Journey
  - [ ] The live pending-count indicator matches the number of undecided (`status="candidate"`) Journeys and updates after a triage action (Epic 3's later stories add the actual approve/reject actions, but this story's count must already reflect whatever undecided set exists)
  - [ ] Selecting different rows correctly replaces (not stacks) the detail panel's content, showing route/method/stage-badge step detail
  - [ ] No confidence/risk/importance UI element exists anywhere on this screen — a deliberate negative check worth including in review, not just a positive functional test

## Dev Notes

- **This story required going back to extend Story 2.5, not just Story 2.1's workflow.** That's worth naming explicitly: cross-story gaps found while speccing a later story are more common in an epic like this one, where the data a screen needs (duplicate flagging) was produced upstream by an inference step whose own AC didn't anticipate the display requirement. Treat Task 1 as authoritative over Story 2.5's original file for this specific field/behavior.
- **Capability-as-independently-reviewed-item is a real ambiguity in FR-9 vs. the UX spine, resolved here in favor of the UX spine** (Capability review is derived, not a separate queue row) since the UX documents were built with much more granular attention to exactly this screen than the PRD's one-line FR. If this resolution turns out wrong once Story 3.2 is actually built, that's worth surfacing back to product, not silently reworking.
- **UX-DR21 (no confidence/risk/importance signal) is one of the two hard, repeatedly-reaffirmed constraints in this entire product** (the other being the four-action-only Journey review, Story 3.2-3.4's territory) — `EXPERIENCE.md`'s Inspiration & Anti-patterns section names this as a "recurring temptation for 'helpful' UI" to resist at the product-decision level, not just the visual level. Take it seriously in code review.
- **2026-07-15 IA change:** this story was renamed from "Review Queue — Candidate List & Evidence Panel" to "Discover Journeys — Candidate List & Detail Panel" and now also delivers FR-23 (Journey step detail, relocated from the deferred Epic 6 Journey Explorer). There is no persistent nav rail in the current IA (Story 1.2) — the live pending-count indicator (Task 3) needs a new home on-screen, not a nav-rail badge. `New`/`Dupe` badges and the detail panel's sticky/width treatment are retained as last-confirmed spec but flagged `[GAP]` pending re-verification against a fuller prototype export. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

### Project Structure Notes

- Extends `Journey` (`packages/domain`, Story 2.5) with `duplicate_of_journey_id`, extends `InferenceActivity` (Story 2.5), adds Discover Journeys list and step-detail endpoints to `apps/api`, and builds the Discover Journeys screen in `apps/web`. No new top-level directories.
- **Depends on Epic 1 and all of Epic 2 (Stories 1.1–1.5, 2.1–2.5) being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1: Discover Journeys — Candidate List & Detail Panel]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-9]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-13; #Deferred — review-queue live-count delivery mechanism]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — badge, evidence-panel, Nav rail]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Review & Trust Model; #Component Patterns; #Key Flows — Flow 1 (Dupe badge example: "Page_Flow_7 ... Overlaps Claims Approval")]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — `InferenceActivity` and `identity_key` this story extends]

## Previous Story Intelligence

All of Epic 1 and Epic 2 remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 2.5 is implemented, check its File List for `InferenceActivity`'s exact structure and `identity_key` computation before adding the duplicate-detection logic in Task 1 — this story edits that function rather than adding a parallel one.

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
