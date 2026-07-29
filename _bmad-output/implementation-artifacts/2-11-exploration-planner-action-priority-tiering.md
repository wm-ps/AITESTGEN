---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.11: Exploration Planner & Action Priority Tiering

*Added per `sprint-change-proposal-2026-07-29.md`. Supersedes Story 2.2's navigation-first rule (AC 5) for the untried-in-page-action-vs-unvisited-nav case — see Architecture AD-17.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to fully explore a page's own actions before navigating away from it,
so that no page's behavior is left partially understood because the crawler moved on too soon.

## Acceptance Criteria

1. **Given** a candidate action, **when** it is tagged, **then** it is classified Tier 1 (in-page: buttons, forms, expand/collapse, filters, in-page tab switches, scroll/"Load More" triggers) or Tier 2 (navigation-intent: primary nav links, sidebar/menu items, breadcrumb links) deterministically — ARIA/landmark role, route-changing href vs. same-page anchor, position in page layout — with AI as a fallback only for genuinely ambiguous cases. [Source: epics.md#Story 2.11; FR-38; architecture#AD-17]
2. **Given** a state with untried Tier 1 actions, **when** the Planner selects the next action, **then** every untried Tier 1 action — including finishing Story 2.9's scroll/pagination sampling — is exhausted before any Tier 2 action is attempted. [Source: FR-38]
3. **Given** a candidate action, **when** the Planner evaluates it, **then** it asks, in order: State Identity Engine (Story 2.10 — already explored this state? SAME → discard), Action History (already executed this exact action from this state?), Transition History (would this create a loop?), Safety Engine (Story 2.12 — Safe/Destructive/Ambiguous), Data Resolver (Story 2.13 — is required input available?) — and combines the answers into exactly one Execution Decision: EXECUTE / DEFER / SKIP. [Source: epics.md#Story 2.11; FR-38]
4. All Tier 1 actions on a state are processed through the AC 3 decision sequence before any Tier 2 action on that same state. [Source: FR-38]

## Tasks / Subtasks

- [ ] Task 1: Build action-tier tagging (AC: 1)
  - [ ] Extend the Action Extractor (the part of `crawler.py`/`activities.py` that enumerates candidate actions post-NEW/VARIANT classification) to tag each candidate `tier: 1 | 2` at extraction time
  - [ ] Deterministic rules: `role="tab"`/in-page anchor/no route-changing href/layout position outside `<nav>`/menu landmarks → Tier 1; `<nav>`/sidebar/menu/breadcrumb landmark, or an href pointing to a different route → Tier 2
  - [ ] For genuinely ambiguous cases (e.g. a button that looks in-page but triggers a route change), fall back to an AI-assisted classification via the `AIProvider` port (AD-3) — mirrors Story 2.10's Task 4 pattern; the Extractor's own deterministic rule still owns the default when the AI call isn't warranted
- [ ] Task 2: Build the Exploration Planner as an explicit component (AC: 2, 3, 4)
  - [ ] New module in `apps/workers/discovery` (e.g. `planner.py`) formalizing the decision sequence in AC 3 — currently this logic is implicit/scattered across `crawler.py`; this task centralizes it into one place that asks each specialist (State Identity, action-history tracker, transition-history tracker, Safety Engine, Data Resolver) exactly one question each and combines their answers
  - [ ] Maintain an Action History tracker (already-executed-action log, scoped to this run) and a Transition History tracker (A→B edge log, for cycle detection) — these are the Planner's own bookkeeping, not owned by any other specialist
  - [ ] Selection order: exhaust untried Tier 1 candidates on the current state (per AC 2) before considering any Tier 2 candidate
- [ ] Task 3: Wire Execution Decision to Playwright action/DEFER/SKIP handling (AC: 3)
  - [ ] EXECUTE → existing Playwright action-execution path (Story 2.2) → observe result → loop back to Runtime Observer
  - [ ] DEFER → hand off to Story 2.15's Blocked Frontier (may not exist yet at implementation time — coordinate sequencing; a minimal stub queue is acceptable if 2.15 lands later)
  - [ ] SKIP → discard, Planner continues with the next candidate
- [ ] Task 4: Verify end-to-end (AC: 1-4)
  - [ ] A page with 3 untried Tier 1 buttons and 1 untried Tier 2 nav link processes all 3 buttons before the nav link
  - [ ] A tab-group widget's tabs are correctly tagged Tier 1 (cross-check against Story 2.14 once it lands)
  - [ ] The Planner's five-question sequence produces a single, traceable Execution Decision per candidate, loggable for debugging

## Dev Notes

- **This is a genuine priority-order reversal for one specific case, not a full rewrite of Story 2.2's crawl-walk mechanics.** Story 2.2's AD-15 rules 1-4 (page-fingerprint dedup, representative-action/form sampling, error-destination handling, button-triggered-navigation-continuation) are unaffected and stay in `crawler.py`/`activities.py` as-is. Only the *ordering decision* between an untried Tier-1 action and an unvisited Tier-2 nav target changes — see architecture AD-17's explicit note that the old "navigation-first" rule never actually addressed this case, it addressed "prefer nav over *repeating* an already-done action."
- **The Planner doesn't have intelligence of its own** — per the source design document's explicit principle, it asks each specialist one question and combines answers; resist the temptation to fold Safety/Data-Resolver logic into the Planner module itself. Those stay in Stories 2.12/2.13's own modules.
- **Sequencing risk**: this story's Task 2/3 references Stories 2.12 (Safety Engine) and 2.13 (Data Resolver), which may not exist yet depending on implementation order. Build the Planner's specialist-interface shape first (a simple function/protocol per specialist) so 2.12/2.13 can be dropped in without reworking the Planner's own control flow.

### Project Structure Notes

- Adds a new `planner.py` module to `apps/workers/discovery`, and tier-tagging to the existing Action Extractor code. No new domain entities, no new top-level directories.
- Depends on Story 2.9 (readiness) and Story 2.10 (State Identity Engine, consulted as the first Planner question). Stories 2.12/2.13 plug into this Planner's specialist-interface shape once built.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.11]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Sections 8-10 of the source design document]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-3, #AD-15, #AD-17]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the existing navigation-first rule (AC 5) this story partially supersedes]

## Previous Story Intelligence

Story 2.2's `crawler.py` currently makes navigation-vs-repeat decisions inline, without a formally separated "Planner" module — check its actual structure before deciding how much of this story's Task 2 is new code vs. refactoring existing decision points into the new `planner.py`.

## Latest Technical Notes

No new library decisions. AI-assisted tier classification (Task 1) reuses the existing `AIProvider` port/`HostedAIProvider` client.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
