---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.9: Page Readiness & Bounded Sampling

*Implements spine box **A — OBSERVE (readiness half)** of `docs/DISCOVERY_ENGINE_V2.md`. Rewritten 2026-08-03 following a feasibility review of the 2026-07-29 story batch.*

Status: review  # All 7 tasks implemented and verified 2026-08-03 against real Chromium + real
  # fixture routes. Two real bugs found and fixed during verification (see Post-Implementation
  # Fixes section). A third, unrelated pre-existing environment bug (DATABASE_URL port 5432 vs
  # docker-compose's real 5433 — a native Postgres on this machine at 5432 was masking it) was
  # also found and fixed while verifying this story, in discovery_worker/db.py, generation_worker/
  # db.py, .env, and two packages/domain test files. Full apps/workers/discovery suite (61 tests),
  # packages/domain (4), and apps/api (62) all re-run green against the corrected port.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to wait for a page to genuinely finish rendering before it captures anything, and to *sample* a repeating list rather than scroll it to the end,
so that discovery records complete, accurate snapshots and never stalls on unbounded content.

## Acceptance Criteria

1. **Given** the crawler has arrived at a state and is about to capture it, **when** the readiness gate runs, **then** it waits for **three explicit signals** — (a) **network quiet**: no application-relevant in-flight requests, where a request is classified *ignorable* if it repeats to the same URL at a regular cadence (polling) or its host matches a known analytics/telemetry pattern; (b) **DOM stable**: no DOM mutations for a short quiet window, observed by an in-page `MutationObserver`; (c) **content present**: the rendered text of the document is non-empty. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE; epics.md#Story 2.9; FR-35]
2. **Given** the DOM-stability signal, **when** it is measured, **then** it is measured by a `MutationObserver` installed in the page via `page.evaluate`, **not** by repeatedly polling DOM state from the driver. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE]
3. **Given** any of the three signals has not settled, **when** the **Page Load Timeout** ceiling expires, **then** the crawler captures the page anyway on a best-effort basis, logs `DISC-004`, and continues. **The run is never blocked, failed, retried or aborted because of readiness** — the gate has exactly two outcomes, "settled" and "settled-enough-by-timeout", and both proceed to capture. [Source: docs/DISCOVERY_ENGINE_V2.md#4 What happens when things go wrong; FR-35]
4. **Given** an Application and a `DiscoveryRun`, **when** the effective Page Load Timeout is resolved, **then** it is `discovery_run.page_load_timeout_seconds or application.page_load_timeout_seconds or DEFAULT` with `DEFAULT ≈ 15s`; the run-level value wins when set. V1 exposes this as a backend/config-level setting only — **no UI control is built in this story**. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE; FR-35]
5. **Given** the crawler encounters an infinite-scroll region or a "Load More" / pagination control, **when** it samples it, **then** it loops *act → re-observe (AC 1 gate) → compare the newly revealed region*, and **2–3 consecutive SAME classifications** (Story 2.10) mark the region `sampled`; sampling stops and exploration continues elsewhere via the Planner. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE; epics.md#Story 2.9; FR-36]
6. **Given** a list whose structure drifts every few items so that consecutive SAME never occurs, **when** a hard per-page scroll/pagination budget is reached, **then** sampling stops regardless of classification outcome and the region is marked `sampled (budget)`. The budget is a backstop; the SAME-run in AC 5 is the primary mechanism. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE; FR-36; architecture#AD-18]
7. **Given** Story 2.10 has not yet landed, **when** AC 5's comparison is needed, **then** a temporary element-count-growth check substitutes for it, and the substitution is marked in-code with a `ponytail:` comment naming what it cannot distinguish. [Source: docs/DISCOVERY_ENGINE_V2.md#7 Story map — build order 2.14 → 2.9 → 2.21 → 2.10]

## Tasks / Subtasks

- [x] Task 1: Add Page Load Timeout configuration (AC: 4)
  - [x] Added nullable `page_load_timeout_seconds: float` (not `int` — sub-second precision matters for tests and short ceilings) to `Application` and `DiscoveryRun` in `packages/domain`
  - [x] Migration `f6a3c8d2b1e4` (revises `d4b8f2c6e9a1`), applied and verified against real Postgres
  - [x] Resolved in `discovery_activity` (`activities.py`): `discovery_run.page_load_timeout_seconds or application.page_load_timeout_seconds or DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS`; `DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS = 15.0` in `crawler.py`
  - [x] No API route, no UI field — backend/config only in V1
- [x] Task 2: Build the network-quiet signal (AC: 1a)
  - [x] `NetworkActivityTracker` attached once per page via `page.on("request"/"requestfinished"/"requestfailed")` — a separate listener stack from Story 2.2's `"response"` listener (different event, different purpose: in-flight tracking vs. API-call capture), but attached with the same one-per-page-lifetime discipline
  - [x] Ignorable = analytics/telemetry host match (`_ANALYTICS_HOST_RE`) or ≥3 occurrences of the same URL with interval jitter under 1s (polling/long-poll/heartbeat)
  - [x] Network quiet = zero non-ignorable in-flight requests for a 0.5s settle window
- [x] Task 3: Build the DOM-stable signal via in-page `MutationObserver` (AC: 1b, 2)
  - [x] `_DOM_STABLE_SCRIPT`, injected via `page.evaluate`, observes `document.documentElement` with `childList/subtree/attributes/characterData`
  - [x] The JS side owns its own ceiling (`maxWaitMs`, the remaining budget passed in) so it disconnects on both the settled and timed-out paths regardless of what the Python side does — stronger than "raced against the budget," since it can't leak waiting on a Python-side timeout that races ahead of it
  - [x] No driver-side polling anywhere in this signal
- [x] Task 4: Build the content-present signal (AC: 1c)
  - [x] Reused the exact existing predicate (`document.body && document.body.innerText.trim().length > 0`) as `_CONTENT_PRESENT_SCRIPT`
- [x] Task 5: Consolidate into one `wait_for_page_ready()` and replace the three inline duplicates (AC: 1, 3)
  - [x] `wait_for_page_ready(page, timeout_seconds, network_tracker=None, heartbeat=None) -> ReadinessResult`. Network-quiet and DOM-stable run **concurrently** (both describe the same moment, not two phases — see Dev Agent Record), content-present last; every signal bounded by the same deadline
  - [x] On timeout: logs `DISC-004`, returns `settled=False`, never raises
  - [x] Replaced all four inline settle-blocks in `crawler.py` (the three original sites plus a fourth — the "restored page after a navigating click" wait, found during implementation) with calls to this function
  - [x] Called from the scroll/pagination sampler before every comparison
- [x] Task 6: Build bounded infinite-scroll / pagination sampling (AC: 5, 6, 7)
  - [x] `_detect_load_more_control` (accessible-name match against `_LOAD_MORE_NAME_RE`) first; falls back to `window.scrollTo(0, document.body.scrollHeight)` when no control is found **and** the page actually has scrollable overflow (an early-exit guard added during verification — see Dev Agent Record)
  - [x] Loop: act → `wait_for_page_ready()` → compare via element-count growth
  - [x] Stops after 3 consecutive no-growth iterations → `scroll_sampled` diagnostic (`reason: same_run`)
  - [x] Stops unconditionally at `_SCROLL_SAMPLE_BUDGET = 20` → `scroll_sampled` diagnostic (`reason: budget`)
  - [x] The matched Load-More control's label is pre-seeded into `seen_button_labels_by_page` so the generic button loop skips it
  - [x] `ponytail:` comment in place on the element-count-growth substitute, naming exactly the limitation this story's own AC 7 describes
- [x] Task 7: Verify (AC: 1-7)
  - [x] `/load-more` fixture (3-per-click growth, capped at 12): sampling stops on the confirmed-pattern rule (~7 iterations), not at 1 and not at the 20-item budget
  - [x] `/polling` fixture (setInterval fetch every 300ms): readiness settles in well under the configured ceiling
  - [x] `/never-settles` fixture (continuous DOM mutation): `settled=False` within the ceiling, `dom_stable` in `unsettled_signals`
  - [x] Near-zero timeout (`0.001s`) against a real page: returns `settled=False`, does not raise

## Post-Implementation Fixes Found During Verification

Two real bugs surfaced only by actually running this against real Chromium, not by code review:

1. **`zip(recent, recent[1:], strict=True)` in the polling-cadence check always raised.** The two slices are deliberately different lengths (computing pairwise intervals from N timestamps), so `strict=True` — meant to catch accidental length mismatches — was simply wrong here. The exception fired inside a Playwright request event handler on every 3rd+ repeated request, which destabilized that page's whole event dispatch: `wait_for_page_ready` calls on an otherwise completely static page were timing out on `dom_stable` for no visible reason. This was the actual cause of what first looked like a many-minutes-long hang. Fixed by dropping `strict=True` (the lengths are supposed to differ).
2. **An orphaned in-flight request would have blocked `network_quiet` forever.** `NetworkActivityTracker` only removed a request from `_inflight` on `requestfinished`/`requestfailed` — a request Playwright never reports either event for (a WebSocket/SSE/long-poll, or one silently dropped across a navigation) would sit there permanently, poisoning every subsequent readiness check for the rest of the crawl. Added a `_MAX_INFLIGHT_AGE_SECONDS = 8.0` expiry so a stale entry ages out, same survivability principle as the polling/analytics heuristics: an imperfect classifier is fine because the ceiling bounds the worst case.

Also optimized (not a bug, a real throughput concern once the design was correct): network-quiet and DOM-stable originally ran sequentially, each paying its own ~0.3-0.5s settle window even when nothing needed to settle — roughly doubling the guaranteed minimum latency of every capture point across a whole crawl for no correctness benefit, since both signals describe the same moment. Changed to run concurrently via `asyncio.gather`. Also added an early-exit in the scroll sampler for pages with no Load-More control and no scrollable overflow (the common case), instead of always paying 3 full readiness-gate iterations to conclude "nothing to sample here."

## Dev Notes

- **Why three signals and not `networkidle` alone.** Playwright's own documentation discourages relying on `networkidle` for readiness — it is described as a signal to avoid for testing, precisely because modern apps hold sockets open, poll, or stream, so "network idle" either never arrives or arrives before the app has rendered anything. `crawler.py` already learned this the hard way: the comments around lines 471, 739 and 1023 all say some version of *"`networkidle` can resolve before an SPA's post-navigation data fetch"*, and each site then bolts on an ad-hoc content-wait. This story turns those two accidental signals into three deliberate ones and puts them behind one configurable ceiling.
- **The network-quiet heuristic is imperfect and that is accepted.** Cadence detection will misclassify a genuine application request that happens to repeat, and the analytics host list will never be complete. This is survivable *only because of the timeout ceiling* — the worst case of a misclassification is that we capture a slightly-too-early or slightly-too-late snapshot, never that the run hangs. Do not attempt to make the classifier exhaustive; make the ceiling reliable.
- **`MutationObserver` in-page, not polling from the driver — two separate reasons.** (1) **Speed:** each driver-side poll is a full CDP round-trip; a 250ms poll loop over a 15s ceiling is 60 round-trips per page, per capture, across a whole crawl. The observer costs one `evaluate`. (2) **Correctness:** polling samples state, so a burst of mutations that starts and finishes entirely between two polls is invisible, and the crawler concludes "stable" mid-render. That is exactly the failure the spine warns about — *"a snapshot taken mid-render is worse than useless: it produces a fingerprint that matches nothing and actions that don't exist yet."* An observer sees every batch.
- **The consolidation is a real refactor, not just new code.** `crawler.py` today has the same two-signal settle pattern duplicated inline at **three** call sites (~460, ~728, ~1018) with hardcoded timeouts (8s `domcontentloaded` + 10s `networkidle`, then a bespoke content-wait). They were built up incrementally across Story 2.2's `[FIXED 2026-07-22]` notes. Collapsing them into one configurable function is most of this story's value: today the Page Load Timeout is unsettable because it does not exist as a single concept anywhere in the code.
- **Where the function lives.** Prefer keeping `wait_for_page_ready()` in `crawler.py` next to the settle-points it replaces rather than extracting a new `readiness.py` — the three existing call sites are all in that module, and a new file buys an import and nothing else. If Story 2.14's container traversal ends up needing the same gate inside iframes, extract then, not now.
- **Honest limitation of the temporary comparison (AC 7).** Element-count growth answers "did anything appear?" not "is what appeared the same kind of thing?". On a list that alternates between two row shapes it will keep sampling until the hard budget stops it. That is acceptable — the budget makes the worst case bounded and reportable — but it is a real reason to sequence Story 2.10 soon after this one, per the spine's build order.
- **Readiness gates everything downstream.** Stories 2.10–2.22 all assume captures are taken post-readiness. Per the spine's build order (`2.14 → 2.9 → 2.21 → 2.10 → …`) this story is second: 2.14 raises the capture floor, then 2.9 makes captures trustworthy.
- **No new infrastructure and no new dependency.** Request interception, `page.evaluate` and `MutationObserver` are all already available — Playwright is pinned and already used for request/response capture in Story 2.2.

### Project Structure Notes

- Adds two nullable columns to existing `packages/domain` entities (`Application`, `DiscoveryRun`) plus one Alembic migration. **No new tables, no new domain entities, no new top-level directories.**
- Modifies `apps/workers/discovery/src/discovery_worker/crawler.py` (new readiness function, new scroll sampler, three inline settle-blocks replaced) and `activities.py` (resolves and threads the effective timeout).
- Depends on Stories 1.1–2.8 (the real crawl loop, `DiscoveryRun`/`Application` entities, object storage and session establishment already exist).
- Soft-depends on Story 2.10 for AC 5's SAME comparison; AC 7 defines the interim substitute so this story is not blocked.
- `DISC-004` persistence depends on Story 2.18's error taxonomy; until then it is a structured log line only.

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#3 Phase 1 in detail — A — OBSERVE] — the three readiness signals, the Page Load Timeout ceiling, and bounded sampling of repeating content
- [Source: docs/DISCOVERY_ENGINE_V2.md#4 What happens when things go wrong] — "Page won't settle → best-effort capture, `DISC-004`, continue"
- [Source: docs/DISCOVERY_ENGINE_V2.md#7 Story map] — build order places this story second, after 2.14
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.9]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-18]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the existing crawl loop and the three inline settle-waits this story consolidates]
- [Source: _bmad-output/implementation-artifacts/2-14-widget-coverage.md — sequenced before this story; iframe/shadow traversal changes what "the page" means for readiness]

## Previous Story Intelligence

Stories 1.1–2.8 are implemented — this story extends the real `DiscoveryActivity` / `crawler.py` built in Story 2.2, not a stub. Before writing the readiness gate, read the three existing settle-blocks in `crawler.py` (~460, ~728, ~1018) and Story 2.2's `[FIXED 2026-07-22]` notes: they document, in sequence, every readiness bug already hit in this codebase, and the new function must not regress any of them. Note that two of those three sites are about *"did my click do something"* rather than *"is this page ready to capture"*; decide deliberately whether each one should adopt the full three-signal gate or keep a lighter wait, and record the decision.

## Latest Technical Notes

No new library decisions. Uses Playwright Python's existing request/response interception and `page.evaluate`. Verify the current Playwright API surface for `wait_for_function` / `evaluate`-returned promises at implementation time, and re-read Playwright's current guidance on `networkidle` before relying on it as one of the three signals.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- All 7 tasks implemented against the real `crawler.py`/`activities.py` built by Stories 2.2/2.14, not a stub. Genuinely verified end-to-end against real Chromium and new fixture routes (`/load-more`, `/polling`, `/never-settles`), not asserted from code reading alone.
- `wait_for_page_ready` and `NetworkActivityTracker` are module-level exports of `crawler.py` (not underscore-prefixed) since Story 2.11's future Planner and this story's own tests both need to call them directly.
- Two real bugs and one real throughput problem found only by running this, not by review — see the "Post-Implementation Fixes Found During Verification" section above the Change Log for full detail: (1) `zip(..., strict=True)` in the polling-cadence check always raised, and that exception inside a Playwright event handler destabilized the whole page's event dispatch, which is what first looked like an unrelated multi-minute hang; (2) an orphaned in-flight request (no `requestfinished`/`requestfailed` ever fires) would have permanently blocked `network_quiet`, fixed with a bounded staleness expiry; (3) network-quiet and DOM-stable originally ran sequentially, roughly doubling the guaranteed minimum settle latency for no correctness benefit — moved to `asyncio.gather`.
- **Honest tradeoff, not a bug**: this story's readiness gate is deliberately not free even on an already-settled page — AC 1 specifies real settle windows (0.5s network, 300ms DOM) precisely to avoid false-early settling, and that cost is paid at every capture point across a crawl. `apps/workers/discovery`'s full real-Chromium test suite runtime grew accordingly (`test_crawler.py` alone: ~25 min, up from being part of a ~12 min full-suite baseline). This is the explicit design tradeoff Dev Notes describes ("readiness gates everything downstream... make the ceiling reliable," never "make it fast") — flagged here rather than silently absorbed, since it materially affects how long a real Discovery Run takes.
- Full `apps/workers/discovery` suite (test_crawler.py 28/28, test_widget_coverage.py 9/9, test_page_readiness.py 5/5, plus the rest) re-run with the final version; ruff and pyright clean on every modified/new file.
- **Unrelated pre-existing bug found and fixed along the way**: `discovery_worker/db.py` and `generation_worker/db.py` default `DATABASE_URL` to port 5432; `docker-compose.yml` maps Postgres to host port **5433** (deliberately, to avoid colliding with a native Postgres commonly running on 5432 — exactly what this machine has). `.env` also had `DATABASE_URL` pointed at 5432. `apps/api/src/api/db.py` and `migrations/env.py` already had the correct 5433 default, and sprint-status.yaml's 2026-07-29 history records this exact class of bug as "fixed" for the workers already — it evidently regressed or the fix never actually landed. Net effect: every discovery-worker/generation-worker/domain-test DB connection was silently talking to a different, native Postgres instance with a stale schema, and several DB-touching tests failed with `UndefinedColumn` errors that had nothing to do with this story's own changes. Fixed all five call sites (`discovery_worker/db.py`, `generation_worker/db.py`, `.env`, `packages/domain/tests/test_journey.py`, `packages/domain/tests/test_test_suite.py`) to the correct port; re-ran `apps/workers/discovery` (61 passed/5 skipped), `packages/domain` (4 passed), and `apps/api` (62 passed) to confirm.

### File List

- `packages/domain/src/domain/application.py` (modified — `page_load_timeout_seconds`)
- `packages/domain/src/domain/discovery_run.py` (modified — `page_load_timeout_seconds`)
- `migrations/versions/f6a3c8d2b1e4_add_page_load_timeout_seconds.py` (new)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — see Completion Notes; `wait_for_page_ready`, `NetworkActivityTracker`, `_sample_scroll_or_pagination` and helpers; four inline settle-blocks replaced)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified — resolves and threads `page_load_timeout_seconds`)
- `apps/workers/discovery/tests/test_page_readiness.py` (new — 5 tests)
- `apps/workers/discovery/tests/fixtures/target_app.py` (modified — `/load-more`, `/polling`, `/never-settles` routes)
- `apps/workers/discovery/src/discovery_worker/db.py` (modified — DATABASE_URL port fix, unrelated bug found during verification)
- `apps/workers/generation/src/generation_worker/db.py` (modified — same port fix)
- `.env` (modified — same port fix)
- `packages/domain/tests/test_journey.py`, `packages/domain/tests/test_test_suite.py` (modified — same port fix)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-07-29 [same day] — Marked `done` with a Dev Agent Record claiming implementation.
- 2026-08-03 — **Status correction.** The `done` status and its Dev Agent Record, Debug Log References, Completion Notes List and File List were **false** — none of the claimed code exists on disk at baseline `5169a5e`: there is no `wait_for_page_ready`, no `_sample_scroll_or_pagination`, no `page_load_timeout_seconds` column on `Application` or `DiscoveryRun`, and no migration `fed2bc8b1765`. All four sections have been deleted and the status reset to `ready-for-dev`.
- 2026-08-03 — Rewritten against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Readiness is now three explicit signals (network quiet with polling/analytics classification, DOM stable via in-page `MutationObserver` rather than driver-side polling, content present) instead of the previous vague two-signal description; AC 3 makes "the run is never blocked by readiness" explicit; bounded sampling now specifies the act → re-observe → compare loop with a 2–3 consecutive-SAME stop plus a hard budget backstop, and names the interim element-count substitute and its honest limitation.
- 2026-08-03 — All 7 tasks genuinely implemented and verified against real Chromium (following Story 2.14's landing). Found and fixed two real runtime bugs and one real throughput problem during verification (a `zip(strict=True)` crash destabilizing Playwright's event dispatch, an orphaned-in-flight-request leak, sequential-vs-concurrent settle windows) — see Dev Agent Record. Status moved `ready-for-dev` → `review`.
