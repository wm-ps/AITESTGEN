---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.19: Loop Prevention Consolidation

*Added per `sprint-change-proposal-2026-07-29.md`.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want all of the discovery engine's anti-loop safeguards to run consistently before any action executes,
so that a pathological page pattern can't stall a run even when the primary sampling mechanisms (State Identity, infinite-scroll sampling) don't catch it.

## Acceptance Criteria

1. **Given** a candidate action about to execute, **when** the Planner (Story 2.11) checks it, **then** it applies, in order: state dedup (Story 2.10), action-history check (already executed this exact action from this state?), transition-cycle detection (would this recreate A→B→A→B?), route normalization (parameterized-duplicate sampling), the infinite-scroll/pagination budget (Story 2.9), and a final depth/action/scroll budget ceiling. [Source: epics.md#Story 2.19; FR-46]
2. **Given** these checks are backstops, **when** Story 2.9/2.10's primary sampling mechanisms already prevent a specific loop, **then** this story does not duplicate that logic — it adds only the checks not already covered (the action-history tracker and transition-cycle detection are the two genuinely new pieces). [Source: FR-46]

## Tasks / Subtasks

- [ ] Task 1: Build the action-history tracker (AC: 1, 2)
  - [ ] Add an in-memory (per-run, scoped to the `DiscoveryActivity` execution — same lifetime class as Story 2.10's runtime cache) log of `(page_fingerprint, action_identity)` pairs already executed this run
  - [ ] Wire as one of the Planner's (Story 2.11) specialist questions: "have I already executed this exact action from this exact state?" — this tracker is the Planner's own bookkeeping, not a new specialist module, per the source design document's own description (Section 10)
- [ ] Task 2: Build transition-cycle detection (AC: 1, 2)
  - [ ] Add an in-memory transition-edge log (`from_page_fingerprint → to_page_fingerprint`) for the current run
  - [ ] Detect when a candidate action's predicted/observed transition would recreate a short cycle (A→B→A→B) already present in the log; treat a detected cycle as a SKIP signal to the Planner
- [ ] Task 3: Confirm existing route-normalization and budget mechanisms are correctly ordered (AC: 1, 2)
  - [ ] Route normalization (parameterized-duplicate sampling, e.g. `:id` collapsing) — this already exists implicitly via Story 2.10's route-template hard filter; this task's job is to confirm it runs in the documented order relative to the new Task 1/2 checks, not to build new normalization logic
  - [ ] Infinite-scroll/pagination budget — already built in Story 2.9; confirm it's consulted in this story's ordered sequence, not rebuilt here
  - [ ] Final depth/action/scroll budget ceiling — a simple hard cap (e.g. max actions per Discovery Run, max crawl depth) as the last-resort backstop; if no such ceiling exists yet from earlier stories, add a minimal one here (this is the one piece of Task 3 that may involve genuinely new code, depending on what Story 2.9/2.2 already established)
- [ ] Task 4: Wire the full ordered check sequence into the Planner (AC: 1)
  - [ ] Confirm/wire the Planner (Story 2.11) to run all six checks in the documented order before any action proceeds to the Safety Engine (Story 2.12)
- [ ] Task 5: Verify end-to-end (AC: 1, 2)
  - [ ] A repeated action-from-state pair the crawler has already tried is skipped via the action-history check, independent of Story 2.10's state-identity result
  - [ ] A synthetic A→B→A→B navigation pattern is detected and skipped before it can repeat a third time
  - [ ] The final depth/action/scroll ceiling terminates a deliberately pathological test case (e.g. a page whose structure subtly changes every iteration, evading Story 2.9's SAME-based sampling) within a bounded number of steps

## Dev Notes

- **This story is explicitly a consolidation and gap-fill, not a new primary mechanism** — per FR-46 and architecture, the *primary* anti-loop mechanisms are Story 2.10's State Identity Engine and Story 2.9's infinite-scroll/pagination sampling. This story's only genuinely new pieces are the action-history tracker and transition-cycle detection; everything else here is sequencing/verification of what earlier stories already built.
- **Sequence this story last among the Epic 2 redesign stories** — it depends on Stories 2.9, 2.10, and 2.11 already existing, since its job is to slot new checks into an ordered sequence the Planner already runs.
- **Do not duplicate Story 2.2's existing MAX_ITERATIONS-style placeholder or Story 2.3's exhaustive-traversal stop condition** — those operate at a different level (overall run termination) from this story's per-action loop-prevention checks (whether *this specific* action should proceed right now). Both remain in force independently.

### Project Structure Notes

- Adds action-history/transition-cycle tracking to the existing `apps/workers/discovery` Planner module (Story 2.11). No new domain entities, no new top-level directories.
- Depends on Stories 2.9, 2.10, and 2.11 all being in place.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.19]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Section 18 of the source design document]
- [Source: _bmad-output/implementation-artifacts/2-9-page-readiness-infinite-scroll-pagination.md — the infinite-scroll budget this story's Task 3 confirms, does not rebuild]
- [Source: _bmad-output/implementation-artifacts/2-11-exploration-planner-action-priority-tiering.md — the Planner this story's checks plug into]

## Previous Story Intelligence

Story 2.11's Planner (`planner.py`) already establishes an Action History tracker and Transition History tracker as part of its own Task 2 — check that story's actual implementation first; this story's Task 1/2 may turn out to be largely already built there, in which case this story's real remaining scope is verification/ordering (Task 3/4) rather than net-new tracker code. Do not build a second, duplicate tracker.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
