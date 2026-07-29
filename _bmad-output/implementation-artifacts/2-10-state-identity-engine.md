---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.10: State Identity Engine — SAME/VARIANT/NEW Classification

*Added per `sprint-change-proposal-2026-07-29.md`. Supersedes Story 2.2's page-fingerprint dedup (AC 4) as the authoritative cross-state comparison — see that story's amendment note and Architecture AD-16.*

Status: done <!-- Implemented and verified 2026-07-29, see Change Log. No UI surface — this story is entirely apps/workers/discovery + packages/ai_provider internals (the Discovery Decision Engine); nothing here has a screen to check against prototype-v3.html. -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to tell genuinely new application behavior apart from the same behavior with different data,
so that discovery doesn't miss real variants or waste effort re-exploring duplicates.

## Acceptance Criteria

1. **Given** an observed state, **when** compared against previously-seen states sharing the same route template, **then** a weighted score (heading match, action-set overlap, form-set overlap, nav breadcrumb match, structural similarity) against two configurable thresholds yields SAME (discarded — different data, identical behavior), VARIANT (a new sibling `Page` row via `variant_of_page_id`), or NEW (a full new `Page`/actions/transitions). [Source: epics.md#Story 2.10; FR-37; architecture#AD-16]
2. Routes that differ structurally (the hard filter) are never scored — they are immediately NEW, without running the weighted comparison. [Source: FR-37]
3. **Given** a score between the two thresholds, **when** the classification is genuinely ambiguous, **then** the AI provider may supply a supporting, non-authoritative opinion (Heading/Status/Actions for State A vs. State B) — the State Identity Engine still owns the final verdict. [Source: FR-37]
4. Comparison thresholds are stored as configuration (per-Application, tunable), never hardcoded. [Source: FR-37]
5. **Given** the comparison runs during an active crawl, **when** checking prior states, **then** it reads from an in-process cache scoped to this Discovery Run's `DiscoveryActivity` execution, rebuilt from canonical (`merged_into_id IS NULL`) `Page` rows on Activity start — not a new persistent cache tier. [Source: architecture#AD-16]
6. A `/claims/1001` vs `/claims/1002` pair sharing route template, heading, and action set classifies SAME; a pair sharing the route template but with materially different action sets (e.g. Edit/Submit vs. Approve/Reject) classifies VARIANT, and both remain independently attributable to a Journey by `InferenceActivity` (Story 2.6). [Source: FR-37, worked example]

## Tasks / Subtasks

- [x] Task 1: Add `Page.variant_of_page_id` and comparison-threshold configuration (AC: 1, 4)
  - [x] Added nullable `variant_of_page_id` (self-referencing FK to `page.id`) to `Page` — distinct from `merged_into_id`
  - [x] Added `Application.state_identity_threshold_same` (default 0.75) / `state_identity_threshold_new` (default 0.35) — per-Application, not hardcoded
  - [x] Alembic migration `a5b04367392f`
- [x] Task 2: Build the canonical-fingerprint comparison (AC: 1, 2, 6)
  - [x] New module `apps/workers/discovery/src/discovery_worker/state_identity.py`: `route_template()`, `compute_fingerprint()`, `score()`, `StateIdentityCache`. Four signals, not five — nav breadcrumb is folded into the heading signal (see Dev Notes; the crawler doesn't track a distinct breadcrumb trail today)
  - [x] Hard filter: `StateIdentityCache.classify()` returns NEW immediately when no cache entry shares the candidate's route template — the weighted score never runs at all in that case
  - [x] Weighted score (heading 0.30, actions 0.35, forms 0.15, structure 0.20) against the two configured thresholds
- [x] Task 3: Wire the in-process runtime cache (AC: 5)
  - [x] `_load_state_identity_cache()` (`activities.py`) loads all canonical (`merged_into_id IS NULL`) `Page` rows for the Application, plus each one's `Action`/`Form` rows, into the cache at `discovery_activity` start
  - [x] The cache is grown in-memory as this run classifies its own NEW/VARIANT pages (`state_identity_cache.add(...)`) — read AND written for the duration of the Activity, per the task's own instruction
  - [x] No Redis — a plain in-process dict, per AD-16
- [x] Task 4: Wire AI-assisted ambiguous-case opinion (AC: 3)
  - [x] Added `AIProvider.infer_state_similarity()` to the Protocol + `HostedAIProvider` implementation (`packages/ai_provider`) — small payload (heading + actions for both states), same `litellm`-proxy HTTP pattern as `infer_journeys`
  - [x] Called only when `Classification.ambiguous` is `True` (score strictly between the two thresholds); logged for visibility only — the verdict computed above is never changed by it. A call failure defaults to `"variant"` internally and never propagates to affect persistence
- [x] Task 5: Wire VARIANT/NEW writes and replace Story 2.2's AC 4 dedup call site (AC: 1)
  - [x] On SAME: nothing written — not even this page's own Actions/Forms/ApiCalls/Transitions (Section 7.4/7.5 of the source design doc: "nothing new... nothing written"); only `page_ids_by_url[url]` is aliased to the matched canonical page so anything referencing this URL later still resolves
  - [x] On VARIANT: full `Page`/`Action`/`Form`/`ApiEndpoint`/`PageTransition` set written, `Page.variant_of_page_id` set to the matched page's id
  - [x] On NEW: same full set written, `variant_of_page_id` left null
  - [x] **Integration point, deliberately not where the story's own draft assumed**: classification runs in `activities.py`'s persist layer, not inside `crawler.py`'s BFS `visited_pages` dedup — see Dev Notes for why, and for the real complication this required solving (a page's full action/form set isn't known until its per-page exploration finishes, not at first navigation)
- [x] Task 6: Verify end-to-end (AC: 1-6)
  - [x] `test_state_identity.py` (7 unit tests, pure functions/classes, no DB) — SAME/VARIANT/NEW scoring and cache classification, including the exact Draft-vs-Pending worked example
  - [x] `test_discovery_activity_integration.py::test_state_identity_engine_dedupes_same_and_keeps_variant` — a real crawl against 3 same-route-template live pages (`/orders/1,2,3`): confirms exactly 2 `Page` rows (order 2 deduped SAME), one with `variant_of_page_id` pointing at the other
  - [x] Full `apps/workers/discovery/` + `apps/api/tests/` + `packages/ai_provider/` suites green — see Debug Log

## Dev Notes

- **`variant_of_page_id` vs. `merged_into_id` — do not conflate.** `merged_into_id` (Story 2.5, AD-8) means "this row is a duplicate, superseded by the canonical row" — a merged row is effectively dead weight kept for audit. `variant_of_page_id` means "this row is a live sibling of the referenced row, sharing a route but genuinely different behavior" — both rows stay canonical (`merged_into_id = null`) and both remain independently attributable to Journeys. Getting this backwards would silently merge away real application behavior — exactly the risk this story exists to prevent (see the source document's Section 7.7 "Common Doubt" worked example).
- **Complementary with, not a replacement for, Story 2.5's cross-run canonicalization** — this engine runs *during* one crawl, against an in-process cache; Story 2.5's `ApplicationModelBuilderActivity` still runs after Discovery completes and additionally catches duplicates across separate Discovery Runs the in-run cache never saw. See Story 2.5's own amendment note.
- **In-process cache is a deliberate, documented simplification (architecture AD-16), not an oversight** — do not add Redis speculatively. If a future profiling pass shows a single-process cache is the actual bottleneck, that's a new architecture decision, not something to pre-build here.
- **Thresholds need real-world tuning** — ship with a reasonable default pair but expect them to need adjustment per pilot Application; this is exactly why they're configuration, not constants.
- **`[IMPLEMENTATION NOTE, 2026-07-29]` Classification runs in `activities.py`'s persist layer, not inside `crawler.py`'s traversal.** The obvious-looking integration point — hook into the BFS's `visited_pages` dedup check in `crawler.py` — doesn't actually work: classification needs a page's full action-set and form-set (AC 1), which aren't known until *after* that page's forms/buttons/scroll-sampling have all been exercised, not at the moment it's first navigated to. `crawler.py` is also deliberately DB-free (pure Playwright logic); the State Identity Engine needs to read/grow a cache seeded from Postgres. Solution: `crawler.py` gained one small addition — a `CapturedPageComplete(url)` signal emitted once a page's full capture set is known (end of its per-page loop body, plus every early-exit path: session-expiry, mid-crawl reauth retry) — and `activities.py`'s persist layer now *buffers* a page's Page/Action/Form/ApiCall/Transition items per URL until that signal arrives, then classifies and either flushes (NEW/VARIANT) or discards (SAME) the whole batch as one unit.
- **`[IMPLEMENTATION NOTE, 2026-07-29]` Real, bounded trade-off: per-page buffering, not per-item.** Before this story, every capture was written to Postgres the instant it happened — a crash could lose at most nothing already-committed. Buffering a full page's captures until `CapturedPageComplete` narrows that guarantee to "at most one in-flight page's captures, not the whole run" on a genuine mid-page crash. Accepted and documented rather than worked around, matching this codebase's existing risk-acceptance style (e.g. PRD §12's explicitly accepted risks) — the alternative (classify without the full action/form set) wouldn't actually implement AC 1.
- **`[REGRESSION FOUND AND FIXED, 2026-07-29]` The pre-crawl login-page capture (`establish_session`, called before `run_discovery_crawl` even starts) also flowed through the same `_persist` callback.** Since that capture has no matching `CapturedPageComplete` (it happens outside the crawl loop entirely), routing it through the new buffering `_persist` silently stranded every login-page capture forever — caught by the pre-existing `test_pages_captured_before_a_mid_crawl_crash_are_not_lost` test, which failed with zero pages persisted at all. Fixed: the login-page capture now calls `_persist_one` directly, bypassing buffering/classification entirely, exactly matching its pre-Story-2.10 behavior.

### Project Structure Notes

- Adds one column + two config fields to existing `packages/domain` entities. Adds a new `state_identity.py` module to `apps/workers/discovery`. Extends the existing `AIProvider` port (`packages/ai_provider`) with one new method. No new top-level directories, no new services.
- Depends on Story 2.9 (readiness gate must run before any comparison) and Story 2.2's existing crawl/capture code (this story's Task 5 replaces one specific dedup call site within it, not the whole crawler).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.10]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Sections 7, 7.7 of the source design document]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8, #AD-16]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — AC 4's dedup call site this story supersedes]
- [Source: _bmad-output/implementation-artifacts/2-5-application-model-builder.md — the complementary cross-run canonicalization]

## Previous Story Intelligence

Story 2.2's `crawler.py` already computes a simple exact-fingerprint (normalized URL) for its AC 4 dedup — check its actual implementation before building this story's richer comparison, since this story's fingerprint computation likely reuses or extends that existing normalization rather than starting from scratch. Story 2.5's `merged_into_id` self-FK on `Page` is the pattern to mirror (not reuse) for this story's new `variant_of_page_id` column.

## Latest Technical Notes

No new library decisions. If Task 4's AI-assisted opinion is implemented, it reuses the existing `litellm`-backed `HostedAIProvider` client (Story 2.6) — no new vendor SDK.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run alembic upgrade head` → migration `a5b04367392f` applied cleanly (stripped the same
  unrelated pre-existing schema-drift items autogenerate detected in Story 2.9's migration too —
  a `form_field` FK and a `journey` index — left untouched, out of scope).
- `uv run ruff check` / `uv run pyright` on all touched/added files → clean (two pre-existing,
  unrelated errors elsewhere in the repo — `journey.py`'s line length, `test_hosted.py`'s
  `Scenario(**kwargs)` type inference — confirmed untouched by this story).
- `uv run pytest apps/workers/discovery/tests/test_state_identity.py -q` → 7 passed.
- `uv run --env-file .env pytest apps/workers/discovery/tests/test_discovery_activity_integration.py -v`
  → 6 passed, including the new SAME/VARIANT end-to-end test — **after** fixing the login-page
  regression below (first run: 5 passed, 1 failed).
- `uv run --env-file .env pytest apps/workers/discovery/ apps/api/tests/ packages/ai_provider/ -q`
  → full regression suite, real Postgres/Vault/S3 — see Completion Notes for final counts.

### Completion Notes List

- **No UI implementation** — this story is entirely `apps/workers/discovery` +
  `packages/ai_provider` internals (the Discovery Decision Engine). Nothing to check against
  `prototype-v3.html`.
- **Found and fixed a real regression during verification**, not just implemented the story blind
  — see Dev Notes' `[REGRESSION FOUND AND FIXED]` entry (the pre-crawl login-page capture was
  silently stranded by the new buffering logic; caught by a pre-existing test, not a new one).
- **Extended the test fixture** (`fixtures/target_app.py`) with `/orders/{order_id}` (three
  same-route-template pages: two identical → SAME, one with a materially different action →
  VARIANT) to get a real, live end-to-end proof of AC 1/2/6 rather than only unit-testing the
  scoring math in isolation.
- **`nav breadcrumb` is not a separately-tracked signal** — folded into the heading score (see
  Dev Notes) since the crawler has no distinct breadcrumb-trail capture today. A future story can
  add one without changing `score()`'s shape.

### File List

- `packages/domain/src/domain/page.py` (MODIFIED — `variant_of_page_id`)
- `packages/domain/src/domain/application.py` (MODIFIED — `state_identity_threshold_same`/`_new`)
- `migrations/versions/a5b04367392f_add_state_identity_engine_columns_for_.py` (NEW)
- `apps/workers/discovery/src/discovery_worker/state_identity.py` (NEW)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (MODIFIED — `CapturedPageComplete`,
  emitted at every per-page exit path)
- `apps/workers/discovery/src/discovery_worker/activities.py` (MODIFIED — `_load_state_identity_cache`,
  per-URL buffering in `_persist`, `_classify_and_flush`, `_log_ambiguous_opinion`; login-page
  capture switched to a direct, non-buffering path)
- `packages/ai_provider/src/ai_provider/__init__.py` (MODIFIED — `infer_state_similarity` on the
  `AIProvider` Protocol)
- `packages/ai_provider/src/ai_provider/hosted.py` (MODIFIED — implementation + prompt)
- `apps/workers/discovery/tests/test_state_identity.py` (NEW — 7 unit tests)
- `apps/workers/discovery/tests/test_discovery_activity_integration.py` (MODIFIED — 1 new
  end-to-end test)
- `apps/workers/discovery/tests/fixtures/target_app.py` (MODIFIED — new `/orders/{order_id}` route)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-07-29 [same day, implementation] — Implemented all 6 tasks (AC 1-6): `Page.variant_of_page_id`
  + `Application` threshold columns, `state_identity.py`'s fingerprint/scoring/cache logic,
  `AIProvider.infer_state_similarity` for the ambiguous-band supporting opinion, and the
  `CapturedPageComplete`-signaled buffer-then-classify integration in `activities.py`. Found and
  fixed a real regression (the pre-crawl login-page capture being silently stranded by the new
  buffering) via a pre-existing test, not a new one. Added a live end-to-end SAME/VARIANT test
  against 3 new same-route-template fixture pages, plus 7 pure-function unit tests. Full
  `apps/workers/discovery/`/`apps/api/tests/`/`packages/ai_provider/` suites green against real
  Postgres/Vault/S3. No UI surface. Status moved to `done`.
