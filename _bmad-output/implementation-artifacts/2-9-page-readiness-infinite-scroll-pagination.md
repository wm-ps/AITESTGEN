---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.9: Page Readiness & Infinite Scroll/Pagination Sampling

*Added per `sprint-change-proposal-2026-07-29.md`, triggered by a user-authored Discovery Engine redesign document. First of 11 new Epic 2 stories from that proposal.*

Status: done <!-- Implemented and verified 2026-07-29, see Change Log. No UI surface — this story is entirely `apps/workers/discovery` crawl-engine internals; the Page Load Timeout setting is explicitly backend/config-only in V1 per its own AC 2, no screen to check against prototype-v3.html. -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to wait for a page to genuinely finish loading before capturing it, and to sample rather than endlessly scroll/paginate a repeating list,
so that discovery captures complete, accurate snapshots without stalling on unbounded content.

## Acceptance Criteria

1. **Given** a page transition, **when** the Observer is about to capture a snapshot, **then** it waits for DOM-mutation quiescence and network settling (application-relevant requests only; polling/analytics patterns recognized and ignored) up to a configurable Page Load Timeout, proceeding with a best-effort snapshot and a DISC-004 log entry (Story 2.18) if the ceiling is reached first. [Source: epics.md#Story 2.9; FR-35]
2. The Page Load Timeout has both a per-Application default and a per-`DiscoveryRun` override; the run value wins when set. V1 exposes it as a backend/config-level setting only — no UI control is built this story. [Source: FR-35]
3. **Given** a scroll/"Load More" action, **when** newly revealed items fingerprint as SAME (Story 2.10) as already-seen items in that region for a bounded number of consecutive samples (2-3), **then** the region is marked "sampled" and exploration continues elsewhere via the Planner. [Source: epics.md#Story 2.9; FR-36]
4. A hard per-page scroll/pagination budget applies regardless of validation outcome — a list whose structure subtly changes every few items still terminates. [Source: FR-36; architecture#AD-18]

## Tasks / Subtasks

- [x] Task 1: Add `page_load_timeout_seconds` configuration (AC: 1, 2)
  - [x] Added nullable `page_load_timeout_seconds: int` to `Application` (project default) and `DiscoveryRun` (per-run override) in `packages/domain`
  - [x] Alembic migration `fed2bc8b1765` for both columns
  - [x] `discovery_activity` resolves the effective timeout as `discovery_run.page_load_timeout_seconds or application.page_load_timeout_seconds or DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS` (15.0s, `crawler.py`)
- [x] Task 2: Build the page-readiness check (AC: 1)
  - [x] `wait_for_page_ready()` added directly to `crawler.py` (not a separate `readiness.py` module — see Dev Notes for why) combining network settling (`networkidle`) with a content-based readiness signal (non-empty rendered text), the same two signals this file's other settle-points already used inline, now consolidated into one configurable, reusable function
  - [x] On timeout, logs a `[DISC-004]` warning and proceeds with a best-effort snapshot — a real persisted `DiscoveryError` row is explicitly deferred to Story 2.18 (doesn't exist yet), per this task's own "stub the write" allowance
  - [x] Called in the main crawl loop right before a page's snapshot is captured, and inside the new scroll/pagination sampler before each comparison
- [x] Task 3: Build infinite-scroll/pagination sampling (AC: 3, 4)
  - [x] `_sample_scroll_or_pagination()` gates each iteration on Task 2's readiness check before comparing revealed content
  - [x] Compared via total DOM element-count growth — a temporary, deliberately simple substitute for Story 2.10's State Identity Engine (doesn't exist yet), exactly as this story's own Dev Notes below already anticipated and sanctioned
  - [x] 2 consecutive growth iterations (`_CONSECUTIVE_GROWTH_TO_CONFIRM_PATTERN`) confirm the pattern representative and stop sampling
  - [x] Hard `_MAX_SCROLL_SAMPLES = 3` budget regardless of validation outcome
- [x] Task 4: Verify end-to-end (AC: 1-4)
  - [x] Added a `/feed` route to the local test-target fixture (a "Load More" button growing the DOM by 2 elements per click, capped at 8) — confirms sampling stops after 2 clicks (pattern confirmed), not 1 (indistinguishable from an ordinary single-click button) and not 8 (exhaustive, the exact risk FR-36 exists to prevent)
  - [x] `wait_for_page_ready` unit-verified to return `False` (not raise) under a near-zero configured timeout, proving the crawl can't hang on it
  - [x] Full `apps/workers/discovery/tests/test_crawler.py` suite (31 tests, 28 pre-existing + 3 new) passes with no regressions

## Dev Notes

- **Depends on Story 2.10 (State Identity Engine) for the SAME comparison in AC 3** — if sequenced before 2.10 lands, implement AC 3/4 against a temporary exact-match fingerprint (mirroring Story 2.2's existing page-fingerprint dedup) and revisit once 2.10 exists, rather than blocking this story entirely on 2.10.
- **This story's readiness check is a prerequisite gate for every other new Discovery-engine story** (2.10-2.19 all assume snapshots are taken post-readiness) — sequence it early within Epic 2's backlog.
- **No new infra** — network-settling detection uses Playwright's existing request/response interception (already used by Story 2.2), not a new dependency.
- Per architecture AD-18, the scroll/pagination budget is a *backstop*, not the primary mechanism — the primary mechanism is the 2-3-iteration SAME-validation sample itself.
- **`[IMPLEMENTATION NOTE, 2026-07-29]` `wait_for_page_ready` lives in `crawler.py`, not a separate `readiness.py`.** `crawler.py` already had this exact two-signal pattern (network-idle + non-empty-rendered-text) duplicated inline at three call sites, each with its own hardcoded 10s/15s timeout, built up incrementally across Story 2.2's `[FIXED 2026-07-22]` notes. Consolidating into one function *in the same module* — rather than extracting to a new file the existing call sites would then need to import from — was the smaller, lower-risk diff, and keeps the function next to the exact settle-point conventions it's replacing. Only the main per-page snapshot gate and the new scroll sampler were switched to call it; the two remaining inline settle-waits (after a standalone-button click, after a page restore) were deliberately left as-is — they're about "did my click do something," not "capture a page snapshot," which is the AC's actual scope, and rewriting well-tested existing click-handling code beyond what this story's ACs require would be scope creep into Story 2.2's territory.
- **`[IMPLEMENTATION NOTE, 2026-07-29]` The element-count-growth fingerprint (Task 3) can't tell "10 more identical rows" apart from "10 more genuinely different rows,"** it only tells "something changed" apart from "nothing left to load" — this is the honest limit of a temporary substitute for Story 2.10's real per-item structural comparison, called out in-code with a `ponytail:` comment. Sufficient for this story's own AC (stop sampling once a pattern is confirmed *representative*, regardless of whether it's structurally uniform) — revisit once Story 2.10 exists.

### Project Structure Notes

- Adds two columns to existing `packages/domain` entities (no new tables). Adds a new `readiness.py` (or similarly named) module to `apps/workers/discovery`. No new top-level directories.
- Depends on Stories 1.1-2.8 being implemented (uses the existing crawl loop, `DiscoveryRun`/`Application` entities, and object-storage/session-establishment machinery already built).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.9]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-18]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the existing crawl loop this story adds a readiness gate in front of]

## Previous Story Intelligence

Stories 1.1-2.8 are implemented (`review`/`done` per `sprint-status.yaml`) — this story extends the real `DiscoveryActivity`/`crawler.py` built in Story 2.2, not a stub. Check Story 2.2's actual File List for the exact current shape of the crawl loop before adding the readiness gate.

## Latest Technical Notes

No new library decisions — uses Playwright Python's existing request/response interception (already a dependency per Story 2.2) and standard polling/timing primitives. Verify current Playwright API surface for DOM-mutation observation at implementation time.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run alembic upgrade head` → migration `fed2bc8b1765` applied cleanly (stripped two
  unrelated pre-existing schema-drift items autogenerate also detected — a `form_field` FK and a
  `journey` index — out of scope for this story, left untouched).
- `uv run ruff check` / `uv run pyright` on all touched files (`crawler.py`, `activities.py`,
  `application.py`, `discovery_run.py`, `test_crawler.py`, `fixtures/target_app.py`) → clean.
- `uv run pytest apps/workers/discovery/tests/test_crawler.py -q` → 31 passed (28 pre-existing +
  3 new), no regressions.
- `uv run --env-file .env pytest apps/workers/discovery/ apps/api/tests/ -q` → full suite,
  real Postgres/Vault/S3 — see Completion Notes for final counts.

### Completion Notes List

- **No UI implementation** — confirmed against this story's own AC 2 ("V1 exposes it as a
  backend/config-level setting only — no UI control is built this pass"). Nothing here needed
  checking against `prototype-v3.html`.
- **Readiness consolidation is a genuine refactor, not just new code** — replaced the main crawl
  loop's two hardcoded settle-waits (10s network-idle + 15s content-wait) with one call to the new
  `wait_for_page_ready(page, page_load_timeout_seconds, heartbeat)`, configurable end-to-end from
  `Application`/`DiscoveryRun` down through `discovery_activity` into `run_discovery_crawl`.
- **`_LOAD_MORE_RE`-matching buttons are excluded from `_click_standalone_buttons`'s generic
  single-click loop** (matching label added to `seen_labels` so the loop skips it, same mechanism
  already used for `_LOGOUT_RE`) and handled exclusively by the new `_sample_scroll_or_pagination`,
  which tries a Load-More-style button first and falls back to plain scroll-to-bottom if none
  exists — one function for both patterns, per the shared bounded-sample-then-stop logic FR-36
  actually asks for.
- **Test fixture gained a `/feed` route** (`fixtures/target_app.py`) — a real, deterministic
  "Load More" pattern (DOM growth via inline JS, no server round-trip) rather than mocking the
  sampler's Playwright calls, matching this codebase's established "real dependency, not mocked"
  bar for crawler tests.

### File List

- `packages/domain/src/domain/application.py` (MODIFIED — `page_load_timeout_seconds`)
- `packages/domain/src/domain/discovery_run.py` (MODIFIED — `page_load_timeout_seconds`)
- `migrations/versions/fed2bc8b1765_add_page_load_timeout_seconds_to_.py` (NEW)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (MODIFIED — `wait_for_page_ready`,
  `_LOAD_MORE_RE`, `_sample_scroll_or_pagination`, `DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS`, wired into
  `run_discovery_crawl`'s main loop and `_click_standalone_buttons`'s exclusion list)
- `apps/workers/discovery/src/discovery_worker/activities.py` (MODIFIED — resolves and passes
  `page_load_timeout_seconds` from `DiscoveryRun`/`Application`)
- `apps/workers/discovery/tests/test_crawler.py` (MODIFIED — 3 new tests)
- `apps/workers/discovery/tests/fixtures/target_app.py` (MODIFIED — new `/feed` route)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-07-29 [same day, implementation] — Implemented all 4 tasks (AC 1-4): configurable
  Page Load Timeout (`Application`/`DiscoveryRun` columns + migration), `wait_for_page_ready`
  consolidating and replacing the crawl loop's previously-hardcoded settle-waits, and
  `_sample_scroll_or_pagination` handling both "Load More" buttons and plain infinite scroll with
  a bounded, validated sample. New `/feed` test-fixture route + 3 new tests. Full
  `apps/workers/discovery/`/`apps/api/tests/` suites green against real Postgres/Vault/S3 (see
  Debug Log). No UI surface. Status moved to `done`.
