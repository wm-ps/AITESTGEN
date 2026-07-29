---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.17: Save-as-Project — Cross-Session Pause & Resume

*Added per `sprint-change-proposal-2026-07-29.md`. "Project" maps onto the existing `Application` entity — no new `Project` table is introduced; see Architecture AD-22.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to pause an entire in-progress discovery effort and resume it later without losing progress or re-exploring what's already confirmed,
so that missing test data doesn't force me to finish everything in one sitting.

## Acceptance Criteria

1. **Given** a running Discovery Run, **when** the user pauses it, **then** `DiscoveryRun.status` is set to `paused`; the confirmed Application Model, open `BlockedTask`s (Story 2.15), and the remaining exploration queue are all already durable — no new persistence mechanism beyond what Stories 2.15/2.16/2.2 already write. [Source: epics.md#Story 2.17; FR-44; architecture#AD-22]
2. **Given** a paused project, **when** the user resumes it (same or different session), **then** the platform re-authenticates fresh, loads the confirmed model and open Blocked items, and does not re-explore any already-canonical state. [Source: FR-44]
3. Every fingerprint-cache lookup (Story 2.10), `BlockedTask` (Story 2.15), and remaining-exploration-queue entry is scoped by the existing `application_id` — pausing/resuming is a matter of filtering by that ID, not a new grouping mechanism. [Source: architecture#AD-22]

**`[GAP — flagged, not designed here]`** The dashboard surfacing Confirmed/Blocked/Remaining counts and "Paused — Action Needed" status (per the source document's worked example) has no equivalent screen in the current 6-screen IA (`DESIGN.md`/`EXPERIENCE.md`) — needs a UX pass before this AC's frontend half can be built; see Story 1.2's amendment note.

## Tasks / Subtasks

- [ ] Task 1: Extend `DiscoveryRun.status` with `paused` (AC: 1)
  - [ ] Update the `status` field's allowed values from `running | complete | failed` to `running | complete | failed | paused` in `packages/domain` — no schema change needed if `status` is already a plain string column (per Story 2.1's existing convention, not a DB enum); if it is a DB enum, add a migration for the new value
  - [ ] Add a `pause_discovery_run` operation (API endpoint or service function, following Story 2.1's `start_discovery_run` pattern) that sets `status="paused"` on a running `DiscoveryRun` — does not touch any other table; everything else needed for resume is already durable per Stories 2.2/2.15/2.16
- [ ] Task 2: Build the resume-a-project flow (AC: 2, 3)
  - [ ] Add a `resume_discovery_run` operation: re-authenticate (reuse Story 2.2's `establish_session`, no assumption of a live prior session — mirrors Story 2.4's/AD-11's existing "session expiry means re-auth" philosophy), load canonical `Page`/`Journey` rows for the `application_id`, load open `BlockedTask` rows for the same `application_id`, and resume the exploration queue from wherever Story 2.2's crawl loop left off (queue state is already checkpointed via the same real-time typed-row writes AD-8 already requires — no new checkpoint format)
  - [ ] Verify every read in this path filters by `application_id`, not a new grouping key — per AD-22, "Project" is the existing `Application`, this task must not introduce a parallel scoping mechanism
- [ ] Task 3: Verify end-to-end (AC: 1-3)
  - [ ] Pausing a running Discovery Run sets `status=paused` without touching any other table
  - [ ] Resuming a paused run (simulate "days later" by tearing down and restarting the worker process) re-authenticates fresh and does not re-explore any state already present as a canonical `Page`
  - [ ] Confirm no new "Project" table or grouping column was introduced anywhere in this story's implementation

## Dev Notes

- **This story is almost entirely a status-value extension plus a resume-orchestration wrapper around existing durability** — Stories 2.2 (typed-row real-time writes), 2.15/2.16 (`BlockedTask`/`ExplorationStep`), and 2.5 (canonical Application Model) already provide everything "don't lose progress" requires. Do not build a second, parallel persistence layer for pause/resume; that would violate AD-22's explicit "no new Project table" decision.
- **The dashboard `[GAP]` is real and should not be worked around with ad hoc UI** — this story's frontend surface is intentionally left undesigned pending a UX pass (see Story 1.2's amendment note and the architecture Deferred section). Implementing only the backend halves of AC 1/2/3 and stopping there, pending that UX pass, is the correct scope for this story as currently written — do not invent a dashboard layout to "complete" the story.
- **Crash recovery (Story 2.18) and pause/resume share the same resume path** — a `paused` status set deliberately by the user and a mid-crawl worker crash both resume via the mechanism this story builds (per AD-22/AD-23). Coordinate module boundaries with Story 2.18 so the resume logic isn't duplicated.

### Project Structure Notes

- Extends the existing `DiscoveryRun.status` value set — no new domain entity. Adds `pause_discovery_run`/`resume_discovery_run` operations, likely in `apps/api/src/api/discovery.py` (mirroring Story 2.1's `start_discovery_run`) plus the worker-side resume orchestration in `apps/workers/discovery`.
- Depends on Stories 2.2, 2.5, 2.10, 2.15, 2.16 all being in place — this story's "don't re-explore" guarantee is only as good as those stories' durability.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.17]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Sections 16, 16.1-16.5 of the source design document]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-11, #AD-13, #AD-22]
- [Source: _bmad-output/implementation-artifacts/1-2-sign-in-organization-scoped-workspace.md — the Home screen `[GAP]` note this story's frontend half is blocked on]
- [Source: _bmad-output/implementation-artifacts/2-4-session-expiry-handling.md — the existing re-authentication philosophy this story's resume flow mirrors]

## Previous Story Intelligence

Story 2.1's `start_discovery_run` (`apps/api/src/api/discovery.py`) is the pattern to follow for this story's `pause_discovery_run`/`resume_discovery_run` — check its exact current shape before adding siblings to it.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
