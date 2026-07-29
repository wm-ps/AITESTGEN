---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.18: Crash Recovery & Error Taxonomy

*Added per `sprint-change-proposal-2026-07-29.md`.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operator,
I want engine crashes to recover automatically and target-application failures to be logged with both a machine-readable code and a plain-language explanation,
so that transient infrastructure or target-app issues don't silently corrupt or truncate a discovery run's results.

## Acceptance Criteria

1. **Given** an engine-side crash (process/container restart mid-run), **when** the worker restarts, **then** `DiscoveryActivity` resumes from the last checkpointed (already-committed typed row) position, treating any in-flight action at crash time as unconfirmed and re-verifying rather than assuming success — no separate checkpoint mechanism beyond existing real-time typed-row writes. [Source: epics.md#Story 2.18; FR-45; architecture#AD-23]
2. **Given** a target-application failure (5xx, broken render, or a Story 2.9 Page Load Timeout), **when** it recurs after a small bounded number of retries, **then** the branch is written as a `DiscoveryError` row (`Errored`, not misclassified as NEW or silently dropped) and exploration continues elsewhere. [Source: FR-45]
3. **Given** any `DiscoveryError`, **when** surfaced, **then** it carries both a fixed `error_code` (a starter taxonomy: DISC-001 engine crash, DISC-002 auth expired, DISC-003 app unresponsive, DISC-004 page load timeout, DISC-005 navigation lost, DISC-006 blocked-data/informational) and a human-readable message with a suggested next action — the end-of-run report lists Errored branches alongside Blocked (Story 2.15) and Skipped-Unsafe (Story 2.12) items. [Source: FR-45]

## Tasks / Subtasks

- [ ] Task 1: Add the `DiscoveryError` domain entity (AC: 2, 3)
  - [ ] Add `DiscoveryError` (`id`, `application_id` FK, `discovery_run_id` FK, `page_id` nullable FK, `error_code` [`"DISC-001" | "DISC-002" | "DISC-003" | "DISC-004" | "DISC-005" | "DISC-006"`], `message: str`, `retry_count: int`, `created_at`) to `packages/domain`
  - [ ] Alembic migration
- [ ] Task 2: Wire engine-crash recovery (AC: 1)
  - [ ] Confirm (this is largely a verification task, not new code) that Temporal's own retry semantics plus the existing real-time typed-row writes (`Page`/`Action`/`ApiEndpoint`/`PageTransition`, AD-8) already provide "resume from last confirmed-safe point" for free — a Temporal Activity retry re-enters `DiscoveryActivity`, which must treat any action that was in-flight at crash time as unconfirmed (i.e. re-verify the current page state via Story 2.9's readiness check rather than assuming the last attempted action succeeded) before continuing the exploration queue
  - [ ] Write a `DiscoveryError` row with `error_code="DISC-001"` when a restart is detected (e.g. via Temporal's activity-attempt-count signal) — informational, does not block anything
  - [ ] This mechanism is shared with Story 2.17's `paused`-state resume — coordinate module boundaries so the "reload confirmed model, resume exploration queue" logic isn't duplicated between the two stories
- [ ] Task 3: Wire target-application failure handling (AC: 2, 3)
  - [ ] On a navigation/action that raises (network/DNS error), returns 5xx, or exceeds Story 2.9's Page Load Timeout, retry a small bounded number of times (e.g. 2, per the source document's example)
  - [ ] If still failing after retries, write a `DiscoveryError` row (`error_code="DISC-003"` for app-unresponsive, `"DISC-004"` for a timeout specifically) with a human-readable message and a suggested next action (e.g. "Increase the Page Load Timeout for this application, or check whether the app was under maintenance during this run")
  - [ ] Mark the branch visited-and-skipped (no `Page` row) — this reuses Story 2.2's existing AC 9 broken-destination-skip behavior; this story's addition is the structured `DiscoveryError` log entry, not a new skip mechanism
  - [ ] `DISC-005` (navigation lost — browser lost track of the expected page/state after an action) and `DISC-002` (auth expired mid-crawl — already handled behaviorally by Story 2.4, this story just gives it a matching error code) are logged the same way when detected by their respective existing mechanisms
- [ ] Task 4: Surface errors in the end-of-run report (AC: 3)
  - [ ] Extend Story 2.3's completion report (its amended AC 3) to read `DiscoveryError` rows for the run, grouped/counted alongside Blocked and Skipped-Unsafe items
- [ ] Task 5: Verify end-to-end (AC: 1-3)
  - [ ] Killing the worker process mid-crawl and restarting it resumes from the last confirmed point, with a `DISC-001` entry logged
  - [ ] A page that 5xxs twice is marked Errored (`DISC-003`) and excluded from the exploration queue, not retried forever
  - [ ] Every `DiscoveryError` row has both a machine-readable code and a non-empty human-readable message

## Dev Notes

- **This story is mostly wiring and logging, not new recovery machinery** — per architecture AD-23, crash recovery is a natural consequence of the real-time typed-row writes Story 2.2/AD-8 already do, plus Temporal's own at-least-once retry (AD-9). Resist building a separate, bespoke checkpoint file/table; the existing typed rows already are the checkpoint.
- **DISC-006 (blocked-data) is informational, not a failure** — per FR-45's note, it appears in the same end-of-run reporting surface as genuine errors for completeness, but per Story 2.15/FR-42 it is an expected, non-failure outcome. Do not treat it as a retry-then-fail case in this story's Task 3 logic; it's produced by Story 2.15's own Blocked Frontier path, not by this story.
- **The starter taxonomy is deliberately small (6 codes)** — do not invent additional codes speculatively; if a genuinely new failure mode surfaces during implementation that doesn't fit DISC-001..006, flag it for a follow-up decision rather than expanding the enum ad hoc.

### Project Structure Notes

- Adds one new domain entity (`DiscoveryError`) to `packages/domain`. Extends existing retry/skip logic in `apps/workers/discovery` (Story 2.2's crawler) rather than adding a new crawl mechanism.
- Depends on Story 2.9 (Page Load Timeout, source of DISC-004) and Story 2.3 (completion report this story's Task 4 extends).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.18]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Sections 17, 17.1-17.6 of the source design document]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8, #AD-9, #AD-11, #AD-23]
- [Source: _bmad-output/implementation-artifacts/2-4-session-expiry-handling.md — existing session-expiry detection, matched to DISC-002]
- [Source: _bmad-output/implementation-artifacts/2-3-discovery-stop-conditions-completeness-status.md — the completion report this story's Task 4 extends]

## Previous Story Intelligence

Story 2.2's AC 9 (broken/error-destination handling — a destination that fails to load or responds 4xx/5xx is marked visited and skipped) already implements the *skip* half of this story's Task 3 — check `crawler.py`'s existing implementation before adding the `DiscoveryError`-logging half, to avoid duplicating the skip logic itself.

## Latest Technical Notes

No new library decisions. Detecting an Activity-retry-in-progress for `DISC-001` logging uses Temporal's existing activity-info API (attempt count), already available via the Python SDK.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
