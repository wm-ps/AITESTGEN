# Story 3.5: Review Queue Empty State & New-Journey Flagging on Re-Discovery

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**`[GAP — flagged 2026-07-15]`** The empty-state treatment described in this story's AC was not reachable in the current reference prototype (never seen with zero remaining candidates against the new Discover Journeys screen) and is not confirmed present or cut. Retained unchanged as last-confirmed spec pending re-verification — do not mark this story deferred or backlog. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

## Story

As a reviewer,
I want a clear confirmation once I've triaged every candidate, and to see only genuinely new Journeys on a re-discovery run,
so that I never have to re-review something I've already decided on.

## Acceptance Criteria

1. **Given** the reviewer has decided on every candidate in the queue, **when** the last undecided row is resolved, **then** the queue's list is replaced by an empty-state panel showing a factual confirmation line plus an Approved/Rejected count pair. [Source: epics.md#Story 3.5; FR-9; UX-DR14]
2. **Given** discovery is re-run on a previously discovered Application, **when** `InferenceActivity` produces new candidates, **then** only candidates whose `identity_key` does not match any existing Journey in the Application are surfaced in the review queue — already-approved Journeys are never automatically re-surfaced, and a suppressed match does not alter the existing Journey's `discovery_run_id` or evidence attribution. [Source: epics.md#Story 3.5; FR-15; architecture#AD-13]

## Tasks / Subtasks

- [ ] Task 1: Build the empty-state panel (AC: 1)
  - [ ] Dashed-border panel, circular check icon, one-line factual confirmation (e.g. "Review queue cleared. All candidates from the {date} run have been triaged.", matching `EXPERIENCE.md`'s calibration example — no exclamation points, no celebratory language), plus an Approved/Rejected count pair
  - [ ] **Trigger condition:** replace the queue-row list when zero `status="candidate"` Journeys remain for the Application — this can be reached via any mix of approve/reject/delete (Story 3.4's delete doesn't get its own "resolved" badge state, but it does remove the row from the undecided set, so it counts toward emptying the queue)
  - [ ] **Count-pair scope, resolved from `EXPERIENCE.md`'s Flow 1 example** ("5 approved, 1 rejected" for candidates "from the Jul 12 run"): the pair counts Approved and Rejected Journeys from the specific Discovery Run whose candidates were just fully triaged, not an all-time Application total, and **excludes deleted rows** — the UX example and UX-DR14 both name only an Approved/Rejected pair, never a three-way count including deleted
- [ ] Task 2: Wire the empty-state trigger into the existing queue/count mechanism (AC: 1)
  - [ ] Reuse Story 3.1's live pending-count mechanism to detect the zero-undecided condition rather than building a second, parallel counting path
- [ ] Task 3: Extend `InferenceActivity` for cross-run re-discovery suppression (AC: 2)
  - [ ] **This is where `identity_key`/AD-13 finally gets used for the purpose it was originally built for in Story 2.5 — distinct from Story 3.1's same-batch `duplicate_of_journey_id` mechanism.** Keep the two clearly separate in the code: 3.1's mechanism flags and *displays* a same-run duplicate with a `Dupe` badge (the candidate still gets created); this story's mechanism *prevents a new candidate from being created at all* when it matches an existing Journey from a **prior** Discovery Run. Don't merge or conflate the two checks
  - [ ] When computing a new candidate's `identity_key`, check it against every non-`deleted` Journey (`candidate`, `approved`, or `rejected`) already on the Application from an earlier `discovery_run_id`. On a match, do not create a new `Journey` row for that candidate — this is the suppression FR-15 describes ("only newly-discovered Journeys ... are flagged")
  - [ ] **Evidence attribution on a suppressed match: leave the newly-captured `Evidence` rows unattributed (`journey_id` stays null) rather than attributing them to the existing matching Journey.** This is the safest reading of AD-13's "does not alter the existing Journey's ... evidence attribution" — the rule guards against exactly this temptation (enriching the old Journey with fresh evidence on a re-confirming run), and FR-15 is explicit that this is "a simple existence check... a materially smaller capability than change detection." Attributing new evidence to the old Journey would be a step toward change detection that FR-15 explicitly disclaims for V1
  - [ ] **A candidate matching a previously-**deleted** Journey is *not* suppressed — it's treated as new and surfaced normally.** This is a secondary, less-certain judgment call (flagged as such, unlike the core approved-Journey suppression rule which is directly stated in FR-15/AD-13): a reviewer's delete doesn't carry the same "permanently decided, never resurface" weight as approve/reject, since FR-13 doesn't describe delete as blocking future re-discovery the way FR-15 explicitly describes approval as doing
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Approving/rejecting/deleting the last undecided candidate for an Application replaces the queue list with the empty-state panel, showing the correct Approved/Rejected counts for that run (deleted excluded)
  - [ ] Re-running discovery on an Application with an already-approved Journey does not create a duplicate candidate for it, and the approved Journey's `discovery_run_id`/evidence attribution are provably unchanged after the re-run
  - [ ] A genuinely new Journey (no `identity_key` match) from the re-discovery run is surfaced normally
  - [ ] A candidate matching a previously-deleted Journey's `identity_key` is surfaced as new, not suppressed

## Dev Notes

- **This story required going back into Story 2.5's `InferenceActivity` a second time** (Story 3.1 already extended it once, for same-batch `Dupe` flagging). Both extensions live in the same function but serve different purposes — comment the code clearly enough that a third pass doesn't conflate them.
- **The evidence-non-attribution choice on suppression is a judgment call about a genuinely ambiguous architecture sentence**, not a certainty — flagged explicitly in case a future story (or real pilot feedback) reveals reviewers actually want to see "this Journey was re-confirmed by N discovery runs," which would argue for a different design (e.g., a `confirmed_run_ids` list) that this story deliberately doesn't build, consistent with keeping FR-15 to its stated "existence check" scope.
- **FR-15's Out-of-Scope note is worth re-reading before extending this story**: "V1 cannot detect that a previously-approved Journey's underlying runtime behavior has changed — only that a Journey it has never seen before now exists." Any temptation to make this story "smarter" (diffing evidence shapes, flagging behavior drift) is explicitly out of scope.

### Project Structure Notes

- Extends `InferenceActivity` (`apps/workers/discovery`, Stories 2.5 and 3.1) and the Review Journeys screen (`apps/web`, Story 3.1) with the empty-state panel. No new entities, no new top-level directories.
- **Depends on Epic 1, Epic 2, and Stories 3.1–3.4 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. This is the last story in Epic 3.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.5: Review Queue Empty State & New-Journey Flagging on Re-Discovery]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-9, FR-15 (including its Out of Scope note)]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-13]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — Empty state]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#State Patterns — Review queue cleared; #Key Flows — Flow 1 climax ("5 approved, 1 rejected")]
- [Source: _bmad-output/implementation-artifacts/2-5-ai-journey-capability-inference-from-evidence.md — `identity_key`'s original purpose, consumed here]
- [Source: _bmad-output/implementation-artifacts/3-1-review-queue-candidate-list-evidence-panel.md — the same-batch `Dupe`-flagging mechanism this story must not conflate with]

## Previous Story Intelligence

Epic 1, Epic 2, and Stories 3.1–3.4 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 3.1 is implemented, check its File List for exactly how it extended `InferenceActivity` for `duplicate_of_journey_id` before adding this story's separate cross-run suppression check to the same function.

## Latest Technical Notes

No new library decisions — extends the existing FastAPI/SQLModel/React/Temporal stack.

## Project Context Reference

No `project-context.md` exists yet in this repository. Epic 3 is now fully spec'd — a strong point to run `bmad-generate-project-context` once Epics 1-3 are implemented, before starting Epic 4.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
