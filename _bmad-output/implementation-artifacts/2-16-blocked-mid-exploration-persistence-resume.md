---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.16: Blocked Path Record & Re-Crawl Resume

*Implements the resume half of spine box **E** of `docs/DISCOVERY_ENGINE_V2.md`. **Mechanism replaced 2026-08-03** following a feasibility review: the original step-replay resume does not work reliably against arbitrary applications and has been replaced with re-crawl from the nearest confirmed entry point. `ExplorationStep` is deliberately not named `JourneyStep` — see Architecture AD-20.*

Status: review  # `[COMPLETED 2026-08-04]` All tasks implemented — see Change Log and Dev Agent Record.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the route to a blocked area remembered and re-reachable once I supply what was missing,
so that answering the question actually unblocks the exploration — without the platform blindly re-submitting forms and creating duplicate records in my application.

## Acceptance Criteria

1. **Given** a block occurs after N successful steps, **when** the `BlockedTask` (Story 2.15) is written, **then** all N steps are persisted as ordered `ExplorationStep` rows referencing their already-confirmed `Page` by FK (never duplicating page content), including the action taken and the input values used at each step. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT; FR-43; architecture#AD-20]
2. **Given** the recorded steps, **when** they are used, **then** they serve as a **human-readable diagnostic record of how the crawler reached the blocked point** — shown in Story 2.22's report — and explicitly **not** as a replay script. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT]
3. **Given** a user supplies the missing value, **when** resume begins, **then** the value is written to the Test Data Pool (Story 2.20) under the block's `aggregation_key`, a fresh browser session is established, and the engine **re-crawls from the nearest confirmed entry point** — the last canonical `Page` on the recorded path that is reachable by URL — under normal crawl rules. No stored step is blindly re-executed. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT]
4. **Given** the re-crawl reaches the previously blocked action, **when** the now-pooled value resolves it, **then** the `BlockedTask` is marked `resolved` with `resolved_at` set, and exploration continues downstream normally. [Source: FR-43]
5. **Given** a resumed path blocks again further along, **when** the new block is recorded, **then** the same `BlockedTask` record is extended rather than a new unrelated one created. [Source: FR-43]
6. **Given** no confirmed entry point on the recorded path is reachable by URL, **when** resume is attempted, **then** the engine re-crawls from the Application's root, and the report states that the shorter path could not be used. Resume degrades; it never fails silently. [Source: docs/DISCOVERY_ENGINE_V2.md#F — RETURN]

## Tasks / Subtasks

- [x] Task 1: Add the `ExplorationStep` entity (AC: 1)
  - [x] Add `ExplorationStep` (`id`, `blocked_task_id` FK, `step_order: int`, `page_id` FK, `action_description`, `input_values: JSONB`, `created_at`) to `packages/domain`; `UNIQUE(blocked_task_id, step_order)`
  - [x] Alembic migration
- [x] Task 2: Record the path at block time (AC: 1, 2)
  - [x] `[SCOPED]` Rather than new per-click bookkeeping threaded through the whole crawl (a "Planner in-memory log"), the path is reconstructed retroactively at DEFER time by walking the already-durable `PageTransition` graph backward from the blocked page to its entry point — every hop this walk finds was already committed in real time by the existing capture layer, so no new per-click log is needed to answer "how did we get here"
  - [x] On DEFER, the whole reconstructed path is flushed as `ExplorationStep` rows — the full path, not only the blocking step
  - [x] `[DISCLOSED]` Only the terminal (blocking) step's `input_values` are populated — preceding hops' resolved values aren't durably tracked elsewhere in the engine, so per-hop masking is moot for them; the terminal step is masked when it carries a sensitive value
- [x] Task 3: Build re-crawl resume (AC: 3, 4, 6)
  - [x] New `resume.py` in `apps/workers/discovery`
  - [x] Write the supplied value into the Test Data Pool under the `BlockedTask`'s `aggregation_key` — this is what makes the value available everywhere that key appears, not just on this one path
  - [x] Establish a fresh session via Story 2.2's existing `establish_session` (never assume the blocking session survived)
  - [x] Select the **nearest confirmed entry point**: walk the recorded `ExplorationStep` list backwards for the last `Page` that's still canonical (URL-reachability itself is confirmed live, by the resumed crawl's own re-navigation and Story 2.10 re-fingerprinting)
  - [x] Re-crawl forward from there under normal rules — reuses `run_discovery_crawl` verbatim, so Story 2.12 safety, Story 2.19 loop guards, Story 2.11 state return all apply unchanged, not a second execution path
  - [x] If no entry point qualifies, fall back to the Application root and record that via a `resume` diagnostic (surfaces in Story 2.22's report)
  - [x] On completing the resume crawl, mark the `BlockedTask` resolved — the pool now satisfies the aggregation key by construction, so this crawl cannot re-DEFER on the same key
- [x] Task 4: Extend on re-block (AC: 5)
  - [x] `_record_exploration_path` continues `step_order` from the existing maximum for that `BlockedTask` rather than starting over
- [x] Task 5: Verify end-to-end (AC: 1-6)
  - [x] A multi-step wizard path (`/wizard/step-a` -> `step-b` -> `step-c`, real Chromium) blocking at step-c records every hop, not just the blocking one (`test_exploration_resume.py`)
  - [x] Supplying the value writes it to the pool and resumes from the nearest confirmed page (`step-b`), **not** by replaying `step-a` onward
  - [x] `step-a` (fixture: an order-creating submit) produces **no duplicate record** on resume — verified directly against the fixture's own order counter, the specific harm the mechanism change exists to prevent
  - [x] A path with no reachable entry point (blocked on the very first page visited) falls back to the root — `resumed_from_root=True`, exercised as the degenerate case of the same mechanism
  - [x] A path blocking twice (two independent Discovery Runs, same field) extends one `BlockedTask` across both blocks, `step_order` continuing rather than colliding

## Dev Notes

- **Why the mechanism was replaced.** The 2026-07-29 version replayed every already-succeeded step with its stored inputs, skipping "known-irreversible" steps by navigating directly to their resulting page. The feasibility review found four independent reasons that cannot be made reliable:
  1. **"Known-irreversible" is not knowable from the DOM** — the same undecidable problem as the Safety Engine, except here the cost of guessing wrong is a duplicate real business record in the customer's application.
  2. **Deep-linking past a skipped step usually fails** — step 4 of a wizard is meaningless without steps 1-3's server-side state, so "navigate directly to its resulting Page" lands on an error or a redirect.
  3. **Stored inputs go stale** — the original staleness-checked only the newly supplied value, never the stored ones. An order number captured yesterday may be consumed, expired or deleted.
  4. **The target application may have changed** between block and resume.
  Architecture **AD-21 itself concedes the problem** — *"Where this cannot be generalized across target applications, flag it as an app-specific open question at implementation time"* — which is the design acknowledging it has no answer. **AD-21 should be amended to match this story.**
- **Why re-crawl is the right replacement.** Re-crawling from a confirmed entry point with better data in hand is slower and dramatically more robust: it makes no assumption about idempotency, needs no irreversibility oracle, revalidates that the path still exists, and cannot create a duplicate record through blind re-submission. It also reuses machinery that already has to work — the normal crawl loop — instead of a second, parallel execution path that would only ever run on resume and would therefore be the least-tested code in the engine.
- **The steps are still worth recording.** They are how a user understands *what* was blocked and *where*, and how the entry point is chosen. Recording them is cheap; treating them as executable is what was expensive.
- **The naming distinction is load-bearing.** `ExplorationStep` records a crawl-time path that may never become a `Journey` — `InferenceActivity` (Story 2.6) creates `Journey` rows from the confirmed Application Model after Discovery completes, independent of any `BlockedTask`. Naming this `JourneyStep` would imply a relationship that does not exist. See AD-20.
- **Build this story last, and be willing to cut it.** Story 2.20's Test Data Pool prevents most blocks from ever occurring, which is a far cheaper way to get most of this outcome. If pilot data shows few blocks surviving the pool, the remaining value here is small — a user can simply re-run discovery with the pool populated.

### Project Structure Notes

- Adds the `ExplorationStep` entity to `packages/domain` and `resume.py` to `apps/workers/discovery`. No new top-level directories.
- Depends on Story 2.15 (`BlockedTask` FK), Story 2.11 (the step log and state return), Story 2.10 (entry-point re-fingerprint confirmation) and Story 2.20 (where the supplied value lands).

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT, #F — RETURN]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.16]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-20, #AD-21 — AD-21 requires amendment, see Dev Notes]
- [Source: _bmad-output/implementation-artifacts/2-15-blocked-frontier.md — the `BlockedTask` shell this story extends]

## Previous Story Intelligence

Story 2.15 must exist first — `ExplorationStep` has a hard FK dependency on `BlockedTask`. Story 2.2's `establish_session` (login heuristic + SSO storage-state reuse) is reused verbatim for the fresh session; do not write a second session path.

## Latest Technical Notes

No new library decisions. Re-crawl resume reuses the existing crawl loop rather than introducing a separate replay executor.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- `ExplorationStep` (`packages/domain/src/domain/exploration_step.py`) + migration `d2e3f4a5b6c7` (revises `c1d2e3f4a5b6`, new head, chained after Story 2.18's `DiscoveryError` migration). Applied and verified against real Postgres.
- **Task 2 scoped, disclosed**: rather than new per-click bookkeeping threaded through the whole crawl loop ("the Planner maintains an in-memory ordered log"), `activities.py`'s new `_record_exploration_path` reconstructs the path *retroactively*, at DEFER time, by walking the already-durable `PageTransition` graph backward from the blocked page to its entry point. Every hop this walk finds was already committed in real time by the existing capture layer (`_persist_one`) — no new bookkeeping structure is needed to answer "how did we get here", and it can't drift out of sync with what was actually captured (a live log could, if a code path forgot to record into it). Wired into the existing `execution_decision`/DEFER branch of `_record_diagnostic`, right alongside `blocked_frontier.attach_or_create`.
- Only the terminal (blocking) step's `input_values` are populated — inspected both DEFER payload shapes in `crawler.py` (the data-resolver field-defer and the safety/approval button-defer) and neither ever carries an actual value at the moment it defers (that's *why* it deferred); masking a value from a sensitive pool entry is therefore moot for this reconstruction — disclosed rather than silently glossed over.
- `step_order` continues from `select(func.max(...))` over the target `BlockedTask`'s existing rows (Task 4/AC 5) — the same row `blocked_frontier.attach_or_create` already resolves to by `aggregation_key`, so a second, independent block on the same field extends the trail instead of colliding with `UNIQUE(blocked_task_id, step_order)`.
- `resume.py`: `resume_blocked_task` — writes the supplied value into `TestDataEntry` under the block's `aggregation_key` (update-in-place if a row already exists for that key), establishes a fresh session (Story 2.2's `establish_session`, never assuming the blocking session survived), picks the nearest still-canonical `Page` from the recorded `ExplorationStep` path (skipping the blocking step itself, which never resolved), and re-crawls forward from there via `run_discovery_crawl` — the exact same function every other Discovery Run uses, not a second execution path. Falls back to the Application root when no step qualifies, logging a `resume` diagnostic either way (now included in Story 2.22's `_DIAGNOSTIC_KINDS`). Marks the `BlockedTask` resolved on completion — sound because the pool now satisfies `data_resolver.resolve()`'s step 1 for that key, so this specific crawl cannot re-DEFER on it.
- No caller wires `resume_blocked_task` up yet — same disclosed `[GAP — needs UX pass]` as Stories 2.17/2.20/2.22 (answering a `BlockedTask` has no screen in the current 6-screen IA).
- New fixture: `/wizard/step-a` (submits, creates a real order via `_wizard_orders`, redirects to step-b) -> `/wizard/step-b` (plain link) -> `/wizard/step-c` (required, business-specific "Policy Number" field — always defers). Verified end-to-end against real Chromium/Postgres/Vault/MinIO (`test_exploration_resume.py`): the full 3-hop path is recorded; resuming writes the pool entry and re-crawls from `step-b` (never replaying `step-a`) — `_wizard_orders` length stays at exactly 1 before and after resume, the specific duplicate-record harm this story's mechanism replacement exists to prevent; a block with no preceding hop (started directly at the blocked page) correctly falls back to the Application root (`resumed_from_root=True`); two independent blocks on the same field across two Discovery Runs extend one `BlockedTask`'s step trail rather than colliding. `ExplorationStep` domain round-trip + `UNIQUE` constraint verified separately (`test_exploration_step.py`). Full `apps/workers/discovery` suite green; ruff/pyright clean.

### File List

- `packages/domain/src/domain/exploration_step.py` (new) — `ExplorationStep` entity
- `packages/domain/src/domain/__init__.py` (modified) — export `ExplorationStep`
- `migrations/versions/d2e3f4a5b6c7_add_exploration_step_entity.py` (new)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified) — `_record_exploration_path`, wired into the DEFER branch
- `apps/workers/discovery/src/discovery_worker/resume.py` (new) — `resume_blocked_task`
- `apps/api/src/api/coverage_report.py` (modified) — `resume` added to `_DIAGNOSTIC_KINDS`
- `apps/workers/discovery/tests/fixtures/target_app.py` (modified) — `/wizard/step-a`/`step-b`/`step-c` fixture
- `apps/workers/discovery/tests/test_exploration_resume.py` (new)
- `apps/workers/discovery/tests/test_exploration_step.py` (new)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-08-03 — **Mechanism replaced** against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Step-replay resume (with "skip known-irreversible steps and deep-link past them") was found unreliable against arbitrary applications for four independent reasons, with AD-21 already conceding the general case is unsolved; replaced with re-crawl from the nearest URL-reachable confirmed entry point, with the supplied value written into the Test Data Pool (Story 2.20). `ExplorationStep` retained as a diagnostic record rather than a replay script. Story retitled and re-sequenced last in the epic.
- 2026-08-04 — All tasks implemented per the standing `/goal` BUILD ORDER (last in the epic, after 2-22/2-18/2-17). See Dev Agent Record. Status moved `ready-for-dev` → `review`.
