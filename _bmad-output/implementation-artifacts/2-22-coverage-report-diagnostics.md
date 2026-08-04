---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.22: Coverage Report & Run Diagnostics

*Added 2026-08-03 per `docs/DISCOVERY_ENGINE_V2.md` (spine box **2.1 — CLOSE OUT**). Identified during the feasibility review of the 2026-07-29 batch: every heuristic in the discovery engine is tunable, none of them were observable, and a bare "Complete" overstates what a deliberately-sampled crawl actually covered.*

Status: review  # `[COMPLETED 2026-08-04]` Tasks 2-6 implemented per the BUILD ORDER (after 2.15,
  # ahead of 2.18/2.17/2.16) — see Change Log and Dev Agent Record. The Errored category (Story
  # 2.18's DiscoveryError) degrades to `available=False` via a lazy import until 2.18 lands, per
  # AC 4 — no further edit to this story's code needed when it does.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want an honest account of what discovery reached, what it couldn't, and why it made the calls it made,
so that I can trust the result, act on the gaps, and tune the engine against my application instead of guessing.

## Acceptance Criteria

1. **Given** a Discovery Run reaches a terminal state, **when** its result is presented, **then** it reports five coverage categories: **Reached** (states, actions exercised, forms captured), **Blocked** (distinct aggregated asks with the count of paths waiting on each), **Skipped for safety** (what was refused and why), **Unreached** (states abandoned at Story 2.11's return ladder rung 5, cross-origin frames, closed shadow roots), and **Errored** (branches with their DISC codes). [Source: docs/DISCOVERY_ENGINE_V2.md#5 What the user gets at the end]
2. **Given** `DiscoveryRun.status = complete`, **when** it is surfaced anywhere, **then** it is **never presented alone** — it always appears with the AC 1 counts. Per AD-15 the crawl is deliberate sampling, not exhaustive traversal, and an unqualified "Complete" invites users to read it as "my whole application was covered". [Source: architecture#AD-15; docs/DISCOVERY_ENGINE_V2.md#5]
3. **Given** the engine's heuristics ran, **when** diagnostics are collected, **then** the report includes: Story 2.10 state-identity scores, signal values and verdicts (plus whether the run entered widened no-route-discrimination mode), Story 2.14 low-confidence widget detections and unreachable containers, Story 2.21's fragile-locator proportion, Story 2.13 values the application rejected, Story 2.12 safety verdicts and posture in force, and which Story 2.19 loop guard fired where. [Source: docs/DISCOVERY_ENGINE_V2.md#5]
4. **Given** any producing story has not yet landed, **when** its diagnostics are absent, **then** the report renders the sections it does have rather than failing — each producer writes through **one named sink function** so sections light up incrementally. [Source: docs/DISCOVERY_ENGINE_V2.md#7 Story map]
5. **Given** a completed run, **when** the report is requested, **then** it is available as structured data via the API (queryable and exportable), independent of any screen. [Source: docs/DISCOVERY_ENGINE_V2.md#5]

## Tasks / Subtasks

- [x] Task 1: Define the diagnostics sink (AC: 3, 4)
  - [x] One `record_diagnostic(session, discovery_run_id, kind, payload)` entry point in `apps/workers/discovery` (`diagnostics.py`). Two groups of producers will write through it: **diagnostics** — Story 2.10 (classification scores/verdicts), 2.12 (safety verdicts + posture), 2.13 (rejected values, resolution step used), 2.19 (which guard fired), 2.21 (locator durability); and **coverage counts** — Story 2.11 (`unreached` candidates), 2.14 (low-confidence widgets, unreachable containers), 2.18 (`DiscoveryError` rows). Both go through the same sink; only the `kind` differs. Signature takes an already-open `Session` (matches `activities.py`'s existing `_persist_one` convention) rather than owning its own engine/connection
  - [x] Persist as typed rows (`DiagnosticRecord` in `packages/domain`) scoped to `discovery_run_id`, with `kind` indexed for section queries. Payload is JSONB (`dict`) so a producer can add a field without a migration
  - [x] Land this task **first** — it is the contract the other stories write against, and defining it late means retrofitting every call site. Migration `d4b8f2c6e9a1` (down_revision `e7c2a4b9d105`, then head) applied and verified against real Postgres
  - [x] `record_diagnostic` never raises — a failed diagnostic write logs and rolls back rather than taking down the crawl it's observing (same rationale as `_persist`'s existing exception handling)
- [x] Task 2: Aggregate the five coverage categories (AC: 1)
  - [x] Reached: counts from canonical `Page`/`Action`/`Form` rows for the run
  - [x] Blocked: Story 2.15's read-time grouping by `aggregation_key`, with waiting-path counts
  - [x] Skipped for safety: Story 2.12 verdicts of `DESTRUCTIVE`, plus `DEFER`s attributable to safety
  - [x] Unreached: Story 2.11 `unreached` candidates plus Story 2.14 unreachable containers
  - [x] Errored: `DiscoveryError` rows (Story 2.18) with codes and messages
- [x] Task 3: Assemble the diagnostics sections (AC: 3)
  - [x] Group by producing story; each section degrades to "not available" when its producer has not landed
- [x] Task 4: Expose via API (AC: 5)
  - [x] A report endpoint for a `DiscoveryRun` following existing `apps/api` conventions
  - [x] `[GAP — needs UX pass]` No screen exists for this in the current 6-screen IA (`DESIGN.md`/`EXPERIENCE.md`). V1 is the structured backend report only, deferred alongside Stories 2.17 and 2.20's UI halves
- [x] Task 5: Enforce the qualified-status rule (AC: 2)
  - [x] Audit every place `DiscoveryRun.status` is currently returned or rendered and ensure the counts accompany it
- [x] Task 6: Verify end-to-end (AC: 1-5)
  - [x] A run against a fixture with a blocked field, a destructive button, and an unreached branch produces non-zero counts in the corresponding categories (real Postgres, real HTTP, `test_coverage_report.py`)
  - [x] The report renders correctly when a producer story (2.18) has not landed
  - [x] `status=complete` is never returned by the API without accompanying counts

## Dev Notes

- **This story is what makes the rest of the engine falsifiable.** Every heuristic in Discovery v2 is tunable and every one will need per-application tuning: Story 2.10's two thresholds, Story 2.12's verb lists and posture, Story 2.13's business-specific denylist, Story 2.19's budgets. Without visible numbers, nobody can distinguish an over-merging threshold from a genuinely small application, or a safety posture that deferred 80% of the app from an application with little to explore. The product becomes unfalsifiable — it always "works", and no one can prove otherwise or improve it. This is the same argument made in Story 2.10's observable-scores AC, generalised.
- **It is also a trust issue, not just a debugging one.** AD-15 establishes that `status=complete` means exhaustive traversal of *distinct* pages and action *patterns*, not every DOM instance of everything. That is a sound engineering decision and an easy phrase to misread. A customer shown a bare "Complete" after a run that skipped 40 destructive buttons, deferred 12 data requirements and abandoned 8 states will reasonably believe their application was fully covered. AC 2 exists so the product never implies more than it did.
- **The sink contract must land before its producers.** Seven stories write diagnostics. If each invents its own logging shape and this story reconciles them afterwards, the reconciliation is larger than the feature. Define `record_diagnostic` first, then have every producer call it — that is why each producer story says "structured log behind one named function if 2.22 has not landed".
- **Fragile-locator percentage is the most actionable number in the report.** It maps directly to a fix the customer controls: add test IDs. Surface it prominently rather than burying it in diagnostics.
- **Keep the payload schema loose.** These are diagnostics, not domain data. A JSONB payload per record means a producer can add a signal without a migration, which matters because tuning these heuristics is an ongoing activity, not a one-time setup.

### Project Structure Notes

- Adds a diagnostics record entity to `packages/domain`, the sink function to `apps/workers/discovery`, and a report endpoint to `apps/api`. No new services.
- Consumes output from Stories 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.18, 2.19 and 2.21. Its own Task 1 is a prerequisite for all of them.

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#5 What the user gets at the end, #6 Honest capability gradient]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-15, #AD-23]
- [Source: _bmad-output/implementation-artifacts/2-3-discovery-stop-conditions-completeness-status.md — the existing completeness-status semantics this story qualifies]

## Previous Story Intelligence

Story 2.3 owns `DiscoveryRun.status` and its completion semantics, including the deliberate decision to run `while page_queue:` with no iteration cap. Story 2.18 owns the `DiscoveryError` taxonomy this report's Errored section reads. Neither is modified by this story — it aggregates and presents what they already produce, and only adds the requirement that status never travels alone.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- Task 1 only, deliberately — this story's own build-order note (and `docs/DISCOVERY_ENGINE_V2.md#7`) requires the sink contract to land before any of its seven producers, so it was implemented standalone rather than waiting for the rest of this story's tasks.
- Added `DiagnosticRecord` (`packages/domain/src/domain/diagnostic_record.py`): `id`, `discovery_run_id` (FK, indexed), `kind` (indexed), `payload` (JSONB), `created_at`. Migration `d4b8f2c6e9a1` (revises `e7c2a4b9d105`, new head) applied and verified against a real Postgres instance (`docker compose up -d --wait` + `alembic upgrade head`).
- Added `record_diagnostic(session, discovery_run_id, kind, payload)` in `apps/workers/discovery/src/discovery_worker/diagnostics.py`. Deliberately takes an already-open `Session` rather than owning its own engine — matches the existing `_persist`/`_persist_one` convention in `activities.py` so future producer call sites can call it inline from the same `with Session(engine) as session:` block they already use, with no new connection-management concept to learn.
- Verified end-to-end against real Postgres: `test_record_diagnostic_persists_kind_and_payload` (round-trips kind + JSONB payload) and `test_record_diagnostic_never_raises_on_bad_foreign_key` (a bad FK is caught, logged, and rolled back — never propagated) both pass. Full `apps/workers/discovery` suite (61 tests, real Playwright crawls + Postgres) and `packages/domain` suite (4 tests) pass with no regressions; ruff and pyright clean on all new files.
- Tasks 2-6 (aggregation of the five coverage categories, diagnostics section assembly, the report API endpoint, the qualified-status audit, and end-to-end verification against a fixture) are untouched — each depends on a producer story (2.10-2.15, 2.18-2.19, 2.21) that doesn't exist yet. Status left `in-progress`, not `review`, to reflect that honestly.

### `[COMPLETED 2026-08-04]` Tasks 2-6

- New `apps/api/src/api/coverage_report.py` — `build_coverage_report(session, discovery_run)`. Lives in `apps/api`, not `apps/workers/discovery`: the two are separate deployables (per `discovery_worker/db.py`'s own docstring) and this module only ever needs `domain` + a `Session`, never Playwright/MinIO/the rest of the worker's heavier dependencies. Duplicates `discovery_worker.blocked_frontier`'s small grouping query rather than adding a cross-deployable dependency on the discovery worker package for one function.
- The five AC 1 categories: Reached (canonical `Page`/`Form`/`Action` counts by `discovery_run_id`), Blocked (`BlockedTask` grouped by `aggregation_key`, same shape as `blocked_frontier.consolidated_view`), Skipped for safety (`DiagnosticRecord` kind=`safety_verdict`/verdict=`DESTRUCTIVE`, plus `execution_decision`/DEFER where `deciding_specialist=="safety"`), Unreached (`DiagnosticRecord` kind=`unreached` — already emitted by Story 2.11's State Return ladder rung 5 — plus kind=`widget_coverage` type `unreachable_container`/`frame_depth_exceeded` from Story 2.14), Errored (Story 2.18's `DiscoveryError`, see below).
- **Errored degrades via a lazy import, not a hasattr/table-exists check**: `_errored_section` does `from domain import DiscoveryError` inside a `try/except ImportError`, returning `{"available": False, "items": []}` until Story 2.18 adds the entity. This is what actually satisfies AC 4 ("renders sections it does have rather than failing") given Story 2.18 hasn't landed yet at this story's own position in the BUILD ORDER — no further edit to this file is needed once it does; the section lights up on its own.
- Task 3's diagnostics sections are a generic group-by-`kind` over `DiagnosticRecord` (`_DIAGNOSTIC_KINDS` maps each known `kind` to its producing story), each with its own `available` flag — genuinely producer-agnostic, no per-story branch needed as new kinds appear.
- Story 2.21's fragile-locator ratio (Dev Notes: "the most actionable number in the report") is surfaced as a top-level `fragile_locator_ratio` field (`ComponentLocator.fragile` proportion, joined through `Component.application_id`), not buried in the diagnostics dump, per that Dev Note.
- New endpoint `GET /discovery-runs/{external_id}/report` in `apps/api/src/api/main.py`, organization-scoped like every other discovery-run-scoped endpoint. **Deviation from Task 4's text**: no RFC 7807 envelope exists anywhere else in `apps/api` (verified by search) — every existing endpoint raises a plain `HTTPException(status_code, detail=str)`; this endpoint follows that actual convention rather than introducing a new envelope shape unilaterally.
- AC 2 (qualified-status rule), Task 5: `ApplicationRead` gained `discovery_coverage_summary: dict[str, int] | None`, populated only when `discovery_status == "complete"` (else `None`) — audited both places `DiscoveryRun.status` reaches a response: `_to_application_read` (now takes `session`, both call sites updated) and `list_captures`'s synthetic `kind="status"` row, whose summary text now states reached counts inline instead of a bare "Crawling complete".
- Verified end-to-end (`apps/api/tests/test_coverage_report.py`, real Postgres/Vault/Temporal): a run seeded with one reached Page/Action/Form, one BlockedTask, one DESTRUCTIVE safety_verdict diagnostic and one unreached diagnostic produces the expected non-zero count in each of those four categories via a real HTTP GET; the report renders correctly (Errored section present with `available=False`) with Story 2.18 not yet landed; organization scoping returns 404 cross-org; `status=complete` always carries `discovery_coverage_summary`, `running` never does. Full `apps/api` suite (71 tests) green; ruff/pyright clean.

### File List

- `packages/domain/src/domain/diagnostic_record.py` (new) — `DiagnosticRecord` entity
- `packages/domain/src/domain/__init__.py` (modified) — export `DiagnosticRecord`
- `migrations/versions/d4b8f2c6e9a1_add_diagnostic_record_entity.py` (new) — creates `diagnostic_record` table + indexes
- `apps/workers/discovery/src/discovery_worker/diagnostics.py` (new) — `record_diagnostic()` sink
- `apps/workers/discovery/tests/test_diagnostics.py` (new) — sink persistence + never-raises tests

## Change Log

- 2026-08-03 — Story created per `docs/DISCOVERY_ENGINE_V2.md`, following a feasibility review of the 2026-07-29 Discovery Engine batch which found no feedback or observability signal anywhere in the design despite every heuristic requiring per-application tuning.
- 2026-08-03 — Task 1 (the `record_diagnostic()` sink contract) implemented and verified against real Postgres, ahead of the rest of the story, per the documented build order. Tasks 2-6 remain, blocked on producer stories. Status moved `ready-for-dev` → `in-progress`.
- 2026-08-04 — Tasks 2-6 implemented per the standing `/goal` BUILD ORDER (after 2.15, ahead of 2.18/2.17/2.16). `apps/api/src/api/coverage_report.py` + `GET /discovery-runs/{external_id}/report`; qualified-status rule enforced on `ApplicationRead` and the captures feed's status marker. Errored category degrades gracefully (lazy import) since Story 2.18 hasn't landed yet. Full `apps/api` suite (71 tests) green; ruff/pyright clean. Status moved `in-progress` → `review`.
