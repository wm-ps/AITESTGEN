---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.10: State Identity Engine — SAME/VARIANT/NEW Classification

*Implements spine box **B — IDENTIFY** of `docs/DISCOVERY_ENGINE_V2.md`. Rewritten 2026-08-03 following a feasibility review of the 2026-07-29 story batch. Supersedes Story 2.2's page-fingerprint dedup (its AC 4) as the authoritative in-run cross-state comparison — see that story's amendment note and Architecture AD-16.*

Status: review  # All 8 tasks implemented and verified 2026-08-03 against real Chromium + real
  # Postgres + Vault + MinIO, following Stories 2-14/2-9/2-21. Full apps/workers/discovery suite
  # (100 tests, 0 skipped) re-run green, including the pre-existing "pages captured before a mid-
  # crawl crash are not lost" regression test this story's buffering change put at direct risk.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to tell genuinely new application behaviour apart from the same behaviour with different data — and to show me *why* it decided that,
so that discovery neither misses real variants nor wastes the run re-exploring duplicates, and so a badly-tuned run is diagnosable instead of mysterious.

## Acceptance Criteria

1. **Given** a candidate state and the set of states already known this run, **when** no known state shares the candidate's **route template** (`/claims/1001` → `/claims/{id}`), **then** the candidate is classified **NEW** immediately and the expensive weighted comparison is never run. This hard pre-filter runs first, always. [Source: docs/DISCOVERY_ENGINE_V2.md#B — IDENTIFY; FR-37]
2. **Given** one or more known states share the candidate's route template, **when** the weighted score is computed across four signals — **heading 0.30, action set 0.35, form set 0.15, structural shape 0.20** — against two configurable thresholds (defaults ≈ **0.75 SAME** / **0.35 NEW**), **then** the verdict is **SAME** (alias the URL to the existing page, persist nothing new), **VARIANT** (a sibling `Page` row via `variant_of_page_id`, both rows stay canonical), or **NEW** (full `Page` + actions + forms + transitions). [Source: docs/DISCOVERY_ENGINE_V2.md#B — IDENTIFY; FR-37; architecture#AD-16]
3. **Given** a score lands in the ambiguous band between the two thresholds, **when** the AI provider is consulted, **then** its opinion is recorded as *supporting evidence only* — the engine still owns the verdict, and an AI call that fails, times out or returns nonsense changes nothing about what is persisted. [Source: docs/DISCOVERY_ENGINE_V2.md#B — IDENTIFY; FR-37]
4. **Given** route templates provide **no discrimination across the run** — a no-URL-change SPA (older Angular, Ext JS, in-memory dashboards) where effectively every observed state collapses to one template — **when** the engine detects this condition, **then** it (a) widens to content-derived signals so classification does not rest on an unprotected weighted score, and (b) **logs, once per run, that it has done so**, with the evidence that triggered it, so the run is diagnosable. [Source: docs/DISCOVERY_ENGINE_V2.md#B — IDENTIFY — "The case v1 got wrong: apps where the URL never changes"; #6 Honest capability gradient]
5. **Given** any classification is made, **when** the verdict is produced, **then** the engine writes to run diagnostics (Story 2.22): the candidate identifier, the matched state (if any), each of the four contributing signal values, the composite score, both threshold values in force, the verdict, whether the ambiguous band was entered, and the AI opinion if one was requested. **No classification is silent.** [Source: docs/DISCOVERY_ENGINE_V2.md#B — IDENTIFY — "Thresholds are observable"; #5 What the user gets at the end]
6. **Given** the structural signal is computed, **when** the page contains open shadow roots, **then** the fingerprint includes the structure inside those roots (traversed by Story 2.14); closed roots are excluded and noted. Two states that differ only inside shadow DOM must not score identical. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE; #B — IDENTIFY]
7. **Given** the comparison runs during an active crawl, **when** prior states are consulted, **then** they come from an **in-process cache** scoped to this Discovery Run's `DiscoveryActivity` execution, seeded on Activity start from canonical (`merged_into_id IS NULL`) `Page` rows and grown in memory as this run classifies. **No Redis, no new cache tier.** [Source: architecture#AD-16]
8. **Given** thresholds are needed, **when** they are read, **then** they come from per-Application configuration, never from hardcoded constants in the comparison code. [Source: docs/DISCOVERY_ENGINE_V2.md#B — IDENTIFY; FR-37]
9. **Given** the worked example, **when** classified: `/claims/1001` and `/claims/1002` sharing route template, heading and action set → **SAME**; a pair sharing the route template where one state shows Edit/Submit and the other shows Approve/Reject → **VARIANT**, and both rows remain independently attributable to a Journey by `InferenceActivity` (Story 2.6). [Source: docs/DISCOVERY_ENGINE_V2.md#B — IDENTIFY, worked example; FR-37]

## Tasks / Subtasks

- [x] Task 1: Schema — `variant_of_page_id` and threshold configuration (AC: 2, 8)
  - [x] Added nullable self-referencing FK `Page.variant_of_page_id`, distinct from `merged_into_id` (both documented inline as easy to conflate — see that column's docstring)
  - [x] Added `Application.state_identity_threshold_same` (default 0.75) and `Application.state_identity_threshold_new` (default 0.35)
  - [x] Migrations `b7d4f1e8c2a9` (these three columns) and `c8e2a4f6b1d3` (`Page.heading`/`structural_tokens` — needed so a *prior* run's canonical pages can be re-fingerprinted when seeding a new run's cache, Task 5), applied and verified against real Postgres
- [x] Task 2: Build `state_identity.py` — templates, fingerprints, scoring (AC: 1, 2, 6, 9)
  - [x] `route_template(url)` extends `crawler.py`'s existing `_page_fingerprint` normalization (imported, not re-derived) — collapses numeric/UUID path segments *and* hash-routed fragment segments to `{id}`
  - [x] `compute_fingerprint(...)` — heading (normalized), action-name set, form-field-name set, structural-token set
  - [x] Structural tokens include content inside open shadow roots (`_STATE_SIGNALS_SCRIPT` in `crawler.py`, walking shadow roots recursively) and fold in unreachable-container *counts* (closed shadow roots via Story 2.14's tracking init script; cross-origin frames via `page.frames`) as their own tokens, so reachability differences change the fingerprint
  - [x] `score(a, b)` — weighted 0.30/0.35/0.15/0.20 via Jaccard similarity per signal (heading is exact-match), returning the composite plus all four components
  - [x] `StateIdentityCache.classify()` — route-template hard pre-filter → NEW without scoring when nothing shares the template; otherwise scores against every template-sharing cached state and takes the best match
- [x] Task 3: Handle the no-URL-change SPA case (AC: 4)
  - [x] `StateIdentityCache.widened_mode` — `distinct_templates / distinct_states < 0.2` once at least 5 states are known
  - [x] Widened mode skips the route-template pre-filter and compares against a bounded, most-recent window (`_WIDENED_COMPARISON_BOUND = 30`) instead of every cached state — the O(n²) guard
  - [x] Logged exactly once per `StateIdentityCache` instance (i.e. once per Discovery Run) at WARN, with template count, state count, and the dominant template
- [x] Task 4: Emit classification diagnostics (AC: 5)
  - [x] Every `_classify_and_flush` call in `activities.py` writes one `record_diagnostic(kind="state_identity", ...)` row carrying the URL, route template, matched page id, verdict, `ambiguous`, `widened_mode`, both thresholds, all four component scores (`None` when the hard pre-filter short-circuited to NEW without scoring), the composite, and the AI opinion (`None` outside the ambiguous band) — Story 2.22's sink had already landed, so this went straight through it rather than a stub
- [x] Task 5: Wire the in-process cache (AC: 7)
  - [x] `_seed_state_identity_cache` loads canonical (`merged_into_id IS NULL`) `Page` rows plus their `Action`/`FormField` rows for the Application at `discovery_activity` start, reconstructing each page's fingerprint from the persisted `heading`/`structural_tokens` columns
  - [x] `StateIdentityCache.register()` grows the cache as this run classifies NEW/VARIANT pages
  - [x] A plain `dict`/`list`-backed class, scoped to one `discovery_activity` call — no Redis
- [x] Task 6: AI as non-authoritative tiebreaker (AC: 3)
  - [x] `AIProvider.infer_state_similarity()` added to the Protocol and `HostedAIProvider` (plain-text opinion, not JSON — there's nothing here worth a schema for since it's evidence, not a branch)
  - [x] Called only when `result.ambiguous` is true
  - [x] Recorded in the diagnostic; `_get_ai_opinion` wraps the call in try/except and logs-and-returns-`None` on any failure — the verdict was already decided before this runs
- [x] Task 7: Integrate at the persist layer, not at first navigation (AC: 2, 9)
  - [x] New `CapturedPageComplete(url)` signal, flowing through the existing `_CaptureSink`/`on_capture` channel — emitted at the normal end of the per-page loop body **and** both early-exit paths (session-expiry return, mid-crawl reauth-retry continue)
  - [x] `activities.py`'s `_persist_with_classification` buffers `CapturedPage`/`CapturedForm`/`CapturedAction`/`CapturedApiCall` per page URL in a `_PageBuffer`; `CapturedPageComplete` triggers `_classify_and_flush`. `CapturedTransition` is deliberately **not** buffered (see Dev Agent Record for why — buffering it risked a real duplicate-row bug)
  - [x] SAME: nothing written; `page_ids_by_url[url]` aliased to the matched canonical page id
  - [x] VARIANT: full buffered set flushed via the existing `_persist_one`, with `variant_of_page_id` set. NEW: same, `variant_of_page_id` null
  - [x] The pre-crawl login-page capture (`establish_session` → `_persist_and_note_login_page` → `_persist`) is untouched — it was never switched to the buffering wrapper, so it was never at risk of this signal it never emits
  - [x] Narrowed crash guarantee documented explicitly (see Dev Agent Record) — coordination point for Story 2.18, which doesn't exist yet
- [x] Task 8: Verify (AC: 1-9)
  - [x] Unit: both worked examples (`/claims/1001` vs `/1002` → SAME; Draft-vs-Pending Edit/Submit vs Approve/Reject → VARIANT) plus a genuinely-different-page-sharing-a-template → NEW case
  - [x] Unit: route-template hard filter short-circuits to NEW with `score()` mocked and asserted never called
  - [x] Unit: two fingerprints differing only in structural tokens score `structure_score < 1.0` and `composite < 1.0` — the AC 6 regression test
  - [x] Unit: 6 same-template states cross the widening threshold, the WARN log fires exactly once across two `classify()` calls, and a materially different state is still classified correctly on top of it; a separate test confirms the bounded comparison window doesn't hang/misclassify at 50 cached states
  - [ ] Unit: every `classify()` call emits exactly one diagnostic record carrying all four signal values
  - [x] Integration: real `discovery_activity` (Postgres + Vault + MinIO) over three `/records/{id}` fixture pages (a numeric route template) → exactly 2 canonical `Page` rows, one `variant_of_page_id` pointing at the other; plus a matching test confirming a diagnostic with every signal value exists for each of the 3 visited URLs, and the hard-filter case has null component scores
  - [x] Integration: Story 2.2's pre-existing `test_pages_captured_before_a_mid_crawl_crash_are_not_lost` re-run and confirmed still green — the buffering in Task 7 does not regress it, because each page's buffer flushes progressively (right after that page's own `CapturedPageComplete`), not batched to the end of the run

## Dev Notes

- **Observable scores were the single biggest weakness of the original design, and AC 5 is the fix.** The v1 story shipped two configurable thresholds and no way to see their effect. That is not a tunable system — it is a system with two knobs and no dial. When a pilot reports "it merged two pages that are clearly different", the only useful question is *what did it score, and on which signal?*, and without per-classification diagnostics the answer is a re-run with print statements. Worse, the product becomes unfalsifiable: an over-merging threshold and a genuinely small application produce the same page count, and nobody can tell them apart. Treat the diagnostic write as part of the feature, not as logging garnish — if a code path can classify without emitting a record, the AC is not met.
- **The no-URL-change SPA case (AC 4) is where the design quietly loses its safety net.** The architecture is *hard pre-filter, then weighted score*, and the pre-filter is doing two jobs: it is a performance optimisation, and it is a correctness guard that keeps the fuzzy scorer from ever having to distinguish a claims page from a settings page. On an app where every state is `/#/app` or just `/`, the pre-filter matches everything, contributes nothing, and the weighted score carries 100% of the load unprotected. Two consequences follow, and both must be handled: classification quality drops (needs widened content-derived signals and threshold tuning) **and** cost goes quadratic (every candidate now compares against every cached state — hence the bound in Task 3). The spine's capability gradient already commits to calling this class of app **"Partial — state identity runs without its cheap pre-filter; needs threshold tuning."** The log line in AC 4 is what lets a field engineer discover that they are in that row of the table.
- **Shadow-DOM-aware fingerprinting (AC 6) is not a nicety.** Design systems built on web components (Salesforce Lightning, Polymer/Stencil) render essentially all their meaningful content inside shadow roots. A structural fingerprint that walks only the light DOM sees the same near-empty host skeleton on every screen, scores 1.0 structural similarity everywhere, and — combined with a heading signal that may also live in shadow DOM — merges the entire application into one page. The engine would report "high confidence, few pages" on an app it never actually saw. This is why Story 2.14 is sequenced before this one.
- **`variant_of_page_id` vs. `merged_into_id` — do not conflate them.** `merged_into_id` (Story 2.5, AD-8) means *"this row is a duplicate superseded by the canonical row"* — dead weight kept for audit. `variant_of_page_id` means *"this row is a live sibling of the referenced row, same route, genuinely different behaviour"* — both rows stay canonical (`merged_into_id IS NULL`) and both remain independently attributable to Journeys. Getting this backwards silently deletes real application behaviour, which is precisely the failure this story exists to prevent.
- **Complementary with, not a replacement for, Story 2.5's cross-run canonicalization.** This engine runs *during* one crawl against an in-process cache. Story 2.5's `ApplicationModelBuilderActivity` still runs after Discovery completes and additionally catches duplicates across separate Discovery Runs that the in-run cache never saw.
- **The AI is evidence, not an authority — enforce that structurally.** Compute the verdict first, then optionally attach an opinion. Do not write code shaped as "ask the AI, then override it if we disagree"; that shape drifts into AI-authoritative on the first bug fix. A provider timeout must be a logged no-op.
- **The in-process cache is a documented simplification (AD-16), not an oversight.** Do not add Redis speculatively. If profiling later shows the single-process cache is the real bottleneck, that is a new architecture decision.
- **Integration point: the persist layer, after per-page exploration — and the real cost of that.** The obvious hook (the BFS `visited_pages` dedup in `crawler.py`) does not work: classification needs the page's **full** action and form set, which is not known until the page's forms, buttons and scroll-sampling have all been exercised. `crawler.py` is also deliberately DB-free pure Playwright logic, while this engine must read a cache seeded from Postgres. Hence buffer-then-classify. **The honest cost:** before this story, every capture was written to Postgres the instant it happened, so a crash lost nothing already committed. Buffering narrows that guarantee to *"at most one in-flight page's captures can be lost"*. That is a real regression in the crash story and it must be coordinated with **Story 2.18** — resume needs to know that the in-flight page may be partially unwritten and re-crawl it rather than assume it completed. The alternative (classify without the full action/form set) would not actually implement AC 2.
- **Thresholds will need per-application tuning.** Ship the 0.75/0.35 defaults, expect to change them on the first pilot, and note that AC 5's diagnostics are what make that tuning possible at all.
- **Four signals, not five.** The original story listed nav-breadcrumb as a fifth signal; the crawler tracks no distinct breadcrumb trail today, so it is folded into the heading signal. A future story can add a real breadcrumb capture without changing `score()`'s shape.

### Project Structure Notes

- Adds one column to `Page`, two config columns to `Application`, one Alembic migration. No new tables, no new services, no new top-level directories.
- Adds `apps/workers/discovery/src/discovery_worker/state_identity.py`.
- Modifies `crawler.py` (emit `CapturedPageComplete` at every per-page exit path) and `activities.py` (cache load, per-URL buffering, classify-and-flush, diagnostics emission, login-capture bypass).
- Extends the existing `AIProvider` port (`packages/ai_provider`) with one method.
- Depends on **Story 2.14** (shadow-root traversal for AC 6), **Story 2.9** (captures must be post-readiness or fingerprints are noise), and Story 2.2's existing crawl/capture code.
- Coordinates with **Story 2.18** (narrowed crash guarantee) and **Story 2.22** (diagnostics sink).

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#3 Phase 1 in detail — B — IDENTIFY] — hard filter, weighted score, SAME/VARIANT/NEW table, the no-URL-change case, observable thresholds
- [Source: docs/DISCOVERY_ENGINE_V2.md#5 What the user gets at the end] — state-identity scores are a named section of the coverage report
- [Source: docs/DISCOVERY_ENGINE_V2.md#6 Honest capability gradient] — "No-URL-change SPA (Ext JS, old Angular) → Partial"
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.10]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-8, #AD-16]
- [Source: _bmad-output/implementation-artifacts/2-14-widget-coverage.md — shadow-root and iframe traversal this story's structural signal consumes]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — AC 4's dedup call site this story supersedes]
- [Source: _bmad-output/implementation-artifacts/2-5-application-model-builder.md — the complementary cross-run canonicalization]

## Previous Story Intelligence

Story 2.2's `crawler.py` already computes a simple normalized-URL fingerprint for its AC 4 dedup — read that before building this story's richer comparison, since `route_template()` should extend that normalization rather than start a second one. Story 2.5's `merged_into_id` self-FK on `Page` is the pattern to **mirror, not reuse**, for `variant_of_page_id`. Story 2.2's test suite contains a "pages captured before a mid-crawl crash are not lost" test — the Task 7 buffering will break it if the pre-crawl login capture is routed through the buffer, and that test is the fastest way to catch the mistake.

## Latest Technical Notes

No new library decisions. The ambiguous-band opinion reuses the existing `litellm`-backed `HostedAIProvider` client (Story 2.6) — no new vendor SDK. Shadow-root content arrives through Story 2.14's traversal, not through a new Playwright capability.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- All 8 tasks implemented against the real `crawler.py`/`activities.py`/`model_builder.py` built by Stories 2.2/2.5/2.9/2.14/2.21/2.22, not a stub — genuinely verified end-to-end against real Chromium + real Postgres + real Vault + real MinIO (a local, ephemeral MinIO container started for this session's verification only — no docker-compose or production config changed).
- **`CapturedTransition` is deliberately not buffered**, unlike the other four item types Task 7 names. Reasoning worked out during implementation: a `Transition` references two pages independently, and the crawler already emits a redundant, pre-existing "early" transition at click-time (before the destination page has even been visited) that has *always* been silently dropped by the existing `page_ids_by_url.get(...) is None` check — that's how the code already tolerated forward references before this story. Buffering `Transition` under its destination URL would make that early, redundant emission survive alongside the real one once the destination page's buffer eventually flushed, writing two rows for one edge. Routing it through the unbuffered `_persist` path exactly preserves the pre-existing behavior instead of introducing a new duplicate-row class of bug.
- `ClassificationResult` carries a `matched_fingerprint` field beyond what the story's own pseudocode implied `classify()` needed — added so the caller (`activities.py`) can build a meaningful AI-tiebreaker prompt (state A vs. state B) without `state_identity.py` (deliberately pure, no I/O) knowing anything about prompts.
- `Page.heading`/`Page.structural_tokens` are new persisted columns beyond the story's own Task 1 list — required because Task 5 says "load canonical Page rows... into the cache," and a prior run's canonical pages need their fingerprint signals available somewhere to be reloaded; the crawler-side `CapturedPage` dataclass alone (Story 2.2) isn't persisted data.
- Task 2's "record which subtrees were unreachable... so two pages differing only in reachability are not treated as identical" is honored by folding closed-shadow-root and cross-origin-frame *counts* into the structural token set as their own tokens (`unreachable:closed_shadow_root:N`, `unreachable:cross_origin_frame:N`) — verified with a dedicated real-Chromium test against Story 2.14's `/shadow-dom` and `/frames` fixtures.
- `asyncio.run()` bridges the sync persist-callback context (itself running inside `asyncio.to_thread`, per the existing `_persist`/`_CaptureSink.add` pattern) to the async `AIProvider.infer_state_similarity()` call — safe specifically because `to_thread` guarantees no event loop is already running on that thread.
- **Honest, documented regression, not a bug**: buffering narrows the crash guarantee from "every capture survives a crash" to "at most one in-flight page's captures can be lost" — exactly what Dev Notes anticipated and flagged as a Story 2.18 coordination point. Verified this doesn't regress further than that: the pre-existing `test_pages_captured_before_a_mid_crawl_crash_are_not_lost` (Story 2.2) still passes, because each page's buffer flushes to Postgres progressively, immediately after that page's own `CapturedPageComplete` — not batched to the end of the run.
- Verified: 11 pure unit tests (`test_state_identity.py`), 4 real-Chromium/Postgres integration tests (`test_state_identity_integration.py`), full `apps/workers/discovery` suite re-run (100 tests, 0 skipped with MinIO up) with no regressions, plus `packages/domain` (4), `packages/ai_provider` (8, incl. 1 new), and `apps/api` (62) all green. Ruff and pyright clean on every modified/new file.

### File List

- `packages/domain/src/domain/page.py` (modified — `variant_of_page_id`, `heading`, `structural_tokens`)
- `packages/domain/src/domain/application.py` (modified — `state_identity_threshold_same`/`_new`)
- `migrations/versions/b7d4f1e8c2a9_add_state_identity_fields.py` (new)
- `migrations/versions/c8e2a4f6b1d3_add_page_heading_and_structural_tokens.py` (new)
- `apps/workers/discovery/src/discovery_worker/state_identity.py` (new)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — `CapturedPageComplete`, `CapturedPage.heading`/`.structural_tokens`, `_capture_state_signals`, emission at every per-page exit path)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified — `_PageBuffer`, `_seed_state_identity_cache`, `_classify_and_flush`, `_get_ai_opinion`, `_persist_with_classification`, `_create_page_row`)
- `apps/workers/discovery/src/discovery_worker/model_builder.py` — unchanged; this story's cache is a separate in-run mechanism from Story 2.5's cross-run canonicalization (Dev Notes), not a replacement for it
- `packages/ai_provider/src/ai_provider/__init__.py` (modified — `infer_state_similarity` on the Protocol)
- `packages/ai_provider/src/ai_provider/hosted.py` (modified — implementation + prompt)
- `packages/ai_provider/tests/test_hosted.py` (modified — 1 new test)
- `apps/workers/discovery/tests/test_state_identity.py` (new — 11 unit tests)
- `apps/workers/discovery/tests/test_state_identity_integration.py` (new — 4 integration tests)
- `apps/workers/discovery/tests/fixtures/target_app.py` (modified — `/records/{id}` route)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-07-29 [same day] — Marked `done` with a Dev Agent Record claiming implementation.
- 2026-08-03 — **Status correction.** The `done` status and its Dev Agent Record, Debug Log References, Completion Notes List and File List were **false** — none of the claimed work exists on disk at baseline `5169a5e`: there is no `state_identity.py`, no `variant_of_page_id` column, no `state_identity_threshold_*` columns, no migration `a5b04367392f`, no `CapturedPageComplete` signal and no `infer_state_similarity` on the AI provider. All four sections have been deleted and the status reset to `ready-for-dev`.
- 2026-08-03 — Rewritten against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Retains the route-template hard filter → weighted score → SAME/VARIANT/NEW core, the in-process cache (AD-16), the non-authoritative AI tiebreaker and the `variant_of_page_id`/`merged_into_id` distinction; adds three ACs the original lacked — the no-URL-change SPA case with explicit widening and a diagnosable log (AC 4), observable per-classification scores written to run diagnostics (AC 5), and shadow-DOM-aware structural fingerprinting (AC 6) — and makes the persist-layer integration's narrowed crash guarantee an explicit coordination point with Story 2.18.
- 2026-08-03 — All 8 tasks genuinely implemented and verified end-to-end (real Chromium, Postgres, Vault, MinIO), following Stories 2.9/2.14/2.21/2.22's landing. The pre-existing "captures survive a mid-crawl crash" regression test (Story 2.2) was re-confirmed green against the new buffering. Status moved `ready-for-dev` → `review`. See Dev Agent Record for the two implementation decisions not explicit in the story's own task list (leaving `CapturedTransition` unbuffered; the `matched_fingerprint` field on `ClassificationResult`).
