# Story 3.5: New-Journey Flagging on Re-Discovery

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Renamed 2026-07-15 (was "Review Queue Empty State & New-Journey Flagging on Re-Discovery") — see `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`. This story's empty-state half is cut: it existed only because the old approve/reject model forced a decision on every row before the queue could "clear." With Approve/Reject cut (Stories 3.2/3.3) and every discovered Journey trusted by default, there is no forced per-row decision and no zero-undecided state to trigger an empty-state screen — a reviewer can delete what they don't want and move on whenever they're satisfied. Only the re-discovery dedup logic below survives, unchanged in substance.*

## Story

As a reviewer,
I want to see only genuinely new Journeys on a re-discovery run,
so that I never have to re-review something I've already seen before.

## Acceptance Criteria

1. **Given** discovery is re-run on a previously discovered Application, **when** `InferenceActivity` produces new candidates, **then** only candidates whose `identity_key` does not match any existing Journey in the Application are surfaced — already-known Journeys are never automatically re-created, and a suppressed match does not alter the existing Journey's `discovery_run_id` or evidence attribution. [Source: epics.md#Story 3.5; FR-15; architecture#AD-13]

## Tasks / Subtasks

- [ ] Task 1: Extend `InferenceActivity` for cross-run re-discovery suppression (AC: 1)
  - [ ] **This is where `identity_key`/AD-13 finally gets used for the purpose it was originally built for in Story 2.5.**
  - [ ] When computing a new candidate's `identity_key`, check it against every non-`deleted` Journey already on the Application from an earlier `discovery_run_id`. On a match, do not create a new `Journey` row for that candidate — this is the suppression FR-15 describes ("only newly-discovered Journeys ... are flagged")
  - [ ] **Evidence attribution on a suppressed match: leave the newly-captured `Evidence` rows unattributed (`journey_id` stays null) rather than attributing them to the existing matching Journey.** This is the safest reading of AD-13's "does not alter the existing Journey's ... evidence attribution" — the rule guards against exactly this temptation (enriching the old Journey with fresh evidence on a re-confirming run), and FR-15 is explicit that this is "a simple existence check... a materially smaller capability than change detection." Attributing new evidence to the old Journey would be a step toward change detection that FR-15 explicitly disclaims for V1
  - [ ] **A candidate matching a previously-`deleted` Journey is *not* suppressed — it's treated as new and surfaced normally.** This is a secondary, less-certain judgment call (flagged as such, unlike the core suppression rule which is directly stated in FR-15/AD-13): a reviewer's delete doesn't necessarily carry a "permanently decided, never resurface" weight — FR-13 doesn't describe delete as blocking future re-discovery the way FR-15 describes an existing (non-deleted) Journey as suppressing a re-match
- [ ] Task 2: Verify end-to-end and record evidence (AC: 1)
  - [ ] Re-running discovery on an Application with an already-known (non-deleted) Journey does not create a duplicate candidate for it, and that Journey's `discovery_run_id`/evidence attribution are provably unchanged after the re-run
  - [ ] A genuinely new Journey (no `identity_key` match) from the re-discovery run is surfaced normally, and — per Story 2.5's Task 5 — immediately starts its own `GenerationWorkflow`
  - [ ] A candidate matching a previously-deleted Journey's `identity_key` is surfaced as new (and generates), not suppressed

## Dev Notes

- **This story extends Story 2.5's `InferenceActivity` for cross-run suppression** — the only extension it needs beyond Story 2.5's original scope (an earlier draft of Story 3.1 also touched this function for same-batch `Dupe` flagging, but that mechanism was cut — see Story 3.1's resolved-gaps note).
- **The evidence-non-attribution choice on suppression is a judgment call about a genuinely ambiguous architecture sentence**, not a certainty — flagged explicitly in case a future story (or real pilot feedback) reveals reviewers actually want to see "this Journey was re-confirmed by N discovery runs," which would argue for a different design (e.g., a `confirmed_run_ids` list) that this story deliberately doesn't build, consistent with keeping FR-15 to its stated "existence check" scope.
- **FR-15's Out-of-Scope note is worth re-reading before extending this story**: "V1 cannot detect that a previously-discovered Journey's underlying runtime behavior has changed — only that a Journey it has never seen before now exists." Any temptation to make this story "smarter" (diffing evidence shapes, flagging behavior drift) is explicitly out of scope.
- **`[RESOLVED 2026-07-15]` The empty-state half of this story is cut, not deferred** — it's not that the screen is unbuilt-for-now, it's that nothing in the new curation model (rename/delete only, no approve/reject) ever forces a "have I resolved everything?" moment the way the old model did. If a future revision reintroduces some form of per-row gate, an empty-state concept could return then — it isn't ruled out architecturally, just currently pointless.

### Project Structure Notes

- Extends `InferenceActivity` (`apps/workers/discovery`, Story 2.5). No new entities, no UI work, no new top-level directories.
- **Depends on Epic 1, Epic 2 (Story 2.5), and Story 3.4 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. This is the last story in Epic 3.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.5: New-Journey Flagging on Re-Discovery]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-15 (including its Out of Scope note)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-13]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — `identity_key`'s original purpose, consumed here; Task 5's `GenerationWorkflow`-start, which a newly-surfaced Journey also triggers]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md — original decision to cut Approve/Reject and this story's empty-state half]

## Previous Story Intelligence

Epic 1, Epic 2 (Story 2.5), and Story 3.4 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Story 3.1 makes no changes to `InferenceActivity` (its earlier same-batch duplicate-detection scope was cut) — this story is the only one extending it beyond Story 2.5's original implementation.

## Latest Technical Notes

No new library decisions — extends the existing FastAPI/Temporal stack.

## Project Context Reference

No `project-context.md` exists yet in this repository. Epic 3 is now fully spec'd — a strong point to run `bmad-generate-project-context` once Epics 1-3 are implemented, before starting Epic 4.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
