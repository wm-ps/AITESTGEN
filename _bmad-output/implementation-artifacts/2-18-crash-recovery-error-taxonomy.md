---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.18: Crash Recovery & Error Taxonomy

*Added per `sprint-change-proposal-2026-07-29.md`.*

Status: review  # `[COMPLETED 2026-08-04]` All tasks implemented — see Change Log and Dev Agent Record.

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

- [x] Task 1: Add the `DiscoveryError` domain entity (AC: 2, 3)
  - [x] Add `DiscoveryError` (`id`, `application_id` FK, `discovery_run_id` FK, `page_id` nullable FK, `error_code` [`"DISC-001" | "DISC-002" | "DISC-003" | "DISC-004" | "DISC-005" | "DISC-006"`], `message: str`, `retry_count: int`, `created_at`) to `packages/domain`
  - [x] Alembic migration
- [x] Task 2: Wire engine-crash recovery (AC: 1)
  - [x] Confirm (this is largely a verification task, not new code) that Temporal's own retry semantics plus the existing real-time typed-row writes (`Page`/`Action`/`ApiEndpoint`/`PageTransition`, AD-8) already provide "resume from last confirmed-safe point" for free — a Temporal Activity retry re-enters `DiscoveryActivity`, which must treat any action that was in-flight at crash time as unconfirmed (i.e. re-verify the current page state via Story 2.9's readiness check rather than assuming the last attempted action succeeded) before continuing the exploration queue
  - [x] Write a `DiscoveryError` row with `error_code="DISC-001"` when a restart is detected (e.g. via Temporal's activity-attempt-count signal) — informational, does not block anything
  - [x] This mechanism is shared with Story 2.17's `paused`-state resume — coordinate module boundaries so the "reload confirmed model, resume exploration queue" logic isn't duplicated between the two stories
- [x] Task 3: Wire target-application failure handling (AC: 2, 3)
  - [x] On a navigation/action that raises (network/DNS error), returns 5xx, or exceeds Story 2.9's Page Load Timeout, retry a small bounded number of times (e.g. 2, per the source document's example)
  - [x] If still failing after retries, write a `DiscoveryError` row (`error_code="DISC-003"` for app-unresponsive, `"DISC-004"` for a timeout specifically) with a human-readable message and a suggested next action (e.g. "Increase the Page Load Timeout for this application, or check whether the app was under maintenance during this run")
  - [x] Mark the branch visited-and-skipped (no `Page` row) — this reuses Story 2.2's existing AC 9 broken-destination-skip behavior; this story's addition is the structured `DiscoveryError` log entry, not a new skip mechanism
  - [x] `DISC-005` (navigation lost — browser lost track of the expected page/state after an action) and `DISC-002` (auth expired mid-crawl — already handled behaviorally by Story 2.4, this story just gives it a matching error code) are logged the same way when detected by their respective existing mechanisms
- [x] Task 4: Surface errors in the end-of-run report (AC: 3)
  - [x] Writes through Story 2.22's diagnostics sink (kind=`discovery_error`, persisted as a typed `DiscoveryError` row) rather than extending Story 2.3's completion report directly — 2.22 landed first in the BUILD ORDER, per that story's own Dev Notes note
- [x] Task 5: Verify end-to-end (AC: 1-3)
  - [x] A Temporal activity-attempt > 1 (the observable proxy for "the worker restarted mid-run") logs a `DISC-001` entry — verified via `activity.info().attempt`; a literal kill-and-restart of the worker process is outside any session's reach (no real Temporal worker process runs during tests), same disclosed limitation pattern as other stories in this sprint
  - [x] A page that 5xxs is retried (bounded, `_MAX_NAV_RETRIES=2`) then marked Errored (`DISC-003`) and excluded from the exploration queue, not retried forever — verified against a real fixture route (`/server-error`) with real Chromium
  - [x] Every `DiscoveryError` row has both a machine-readable code and a non-empty human-readable message

## Dev Notes

- **This story is mostly wiring and logging, not new recovery machinery** — per architecture AD-23, crash recovery is a natural consequence of the real-time typed-row writes Story 2.2/AD-8 already do, plus Temporal's own at-least-once retry (AD-9). Resist building a separate, bespoke checkpoint file/table; the existing typed rows already are the checkpoint.
- **`[2026-08-03]` Story 2.10 narrows the checkpoint guarantee this story depends on — coordinate the two.** The State Identity Engine must know a page's *full* action and form set before it can classify, which means captures are buffered per page and flushed only once that page's exploration completes. The pre-2.10 guarantee was "anything already written is safe"; afterwards it becomes "anything already written is safe, except at most one in-flight page's captures." That is an accepted, bounded trade-off (see Story 2.10's Dev Notes), but this story's AC 1 resume logic must treat a partially-captured in-flight page as unconfirmed and re-verify it, not assume it was persisted.
- **`[2026-08-03]` The end-of-run reporting surface is now Story 2.22's**, which reads this story's `DiscoveryError` rows for its Errored category. Task 4 should write through Story 2.22's diagnostics sink rather than extending Story 2.3's completion report directly, if 2.22 has landed first. See `docs/DISCOVERY_ENGINE_V2.md#5`.
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

## Dev Agent Record

### Completion Notes List

- `DiscoveryError` (`packages/domain/src/domain/discovery_error.py`) + migration `c1d2e3f4a5b6` (revises `b4c8e2a6d1f9`, new head) — a typed row, not a generic `DiagnosticRecord` payload, so Story 2.22's report can query it directly (same reasoning as `SyntheticDataEntry`). Applied and verified against real Postgres.
- Wired through `activities.py`'s `_record_diagnostic` as a new `kind == "discovery_error"` special case, exactly mirroring the existing `synthetic_data` branch: writes the typed row, falls back to a swallowed exception (never raises) on a write failure.
- Task 2 (AC 1): a Temporal activity-attempt check (`activity.info().attempt > 1`) at the top of `discovery_activity`, before the crawl starts, logs `DISC-001`. No new checkpoint mechanism — confirmed the existing real-time typed-row writes (`_persist`/`_persist_with_classification`) already are the checkpoint AD-23 describes; an in-flight page's buffered captures (`_PageBuffer`, flushed only on `CapturedPageComplete`) are simply lost on a crash before that signal, which is exactly "treat as unconfirmed, re-verify" — the next attempt's fresh crawl re-captures that page properly rather than trusting a partial buffer.
- Task 3 (AC 2/3), all in `crawler.py`'s main crawl loop: `page.goto(url)` now retries up to `_MAX_NAV_RETRIES=2` additional times on a raised exception or a 5xx response before logging `DISC-003` and skipping the page (the pre-existing plain 4xx skip, Story 2.2 AC 9, is untouched — a 4xx is not a target-application *failure*, so it's still never retried and never logged as an error). `wait_for_page_ready` gained an `on_diagnostic` parameter — an unsettled page now logs `DISC-004` (informational; capture still proceeds best-effort, Story 2.9's own never-block/fail/retry/abort guarantee is unchanged). The session-expiry terminal branch now logs `DISC-002` alongside its existing behavior (Story 2.4/AD-11 still owns detection). The form-submit restore-failure branch (`_recover_login_if_needed` returning `False`) now logs `DISC-005`. `DISC-006` needed no code here per this story's own Dev Notes — it's produced by Story 2.15's Blocked Frontier path and already surfaces via 2.22's separate Blocked category, not through `DiscoveryError`.
- Task 4 (AC 3): no separate report-extension code — Story 2.22 landed first in the BUILD ORDER and its `coverage_report.py` already reads `DiscoveryError` via a lazy import that was written in anticipation of this story; adding the entity here is what flips that section from `available=False` to real rows, with zero edits to `coverage_report.py`. Verified with a new test in `apps/api/tests/test_coverage_report.py`.
- New fixture route `/server-error` (always 503) in `tests/fixtures/target_app.py`, distinct from the existing `/broken` (404) — proves the retry+DISC-003 path is exercised only for a genuine target-application failure, not the ordinary AC-9 4xx skip.
- Verified end-to-end: `test_crawler.py` (real Chromium) — a 5xx destination is retried then logged as `DISC-003` with `retry_count > 1` and never persisted as a Page; a 404 destination is never logged as a `discovery_error`. `test_page_readiness.py` — an unsettled page (`/never-settles`) logs `DISC-004`. `test_discovery_error.py` (real Postgres) — the entity round-trips code/message/retry_count. `apps/api/tests/test_coverage_report.py` — the Errored section reports real rows once `DiscoveryError` exists. Full `apps/workers/discovery` suite and `apps/api` suite green; ruff/pyright clean.
- **Not built, disclosed**: a literal "kill the worker process and restart it" test is outside any session's reach (no real standalone Temporal worker process runs during automated tests) — `DISC-001`'s logging path is verified via `activity.info().attempt`, the same signal production code uses, rather than a live process-kill simulation.

### File List

- `packages/domain/src/domain/discovery_error.py` (new) — `DiscoveryError` entity
- `packages/domain/src/domain/__init__.py` (modified) — export `DiscoveryError`/`ErrorCode`
- `migrations/versions/c1d2e3f4a5b6_add_discovery_error_entity.py` (new)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified) — `discovery_error` sink special-case, DISC-001 attempt check
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified) — bounded nav retry + DISC-003, DISC-004 wiring in `wait_for_page_ready`, DISC-002/DISC-005 logging
- `apps/workers/discovery/tests/fixtures/target_app.py` (modified) — new `/server-error` route
- `apps/workers/discovery/tests/test_crawler.py` (modified) — DISC-003/4xx-no-error tests, `on_diagnostic` threaded through `_crawl`
- `apps/workers/discovery/tests/test_page_readiness.py` (modified) — DISC-004 test
- `apps/workers/discovery/tests/test_discovery_error.py` (new) — entity round-trip test
- `apps/api/src/api/coverage_report.py` (unmodified — the lazy-import degradation written during Story 2.22 already covers this)
- `apps/api/tests/test_coverage_report.py` (modified) — Errored-section-lights-up test

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-08-04 — All tasks implemented per the standing `/goal` BUILD ORDER (after 2-22, ahead of 2-17/2-16). See Dev Agent Record. Status moved `ready-for-dev` → `review`.
