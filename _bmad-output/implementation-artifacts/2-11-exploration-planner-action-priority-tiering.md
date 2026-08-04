---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.11: Exploration Planner, Action Tiering & State Return

*Implements spine boxes **C / D / E / F** of `docs/DISCOVERY_ENGINE_V2.md`. Rewritten 2026-08-03 following a feasibility review of the 2026-07-29 story batch — the State Return ladder (box F) is entirely new and is the largest gap the review found. Supersedes Story 2.2's navigation-first rule (its AC 5) for the untried-in-page-action-vs-unvisited-nav case — see Architecture AD-17.*

Status: review  # `[COMPLETED 2026-08-04]` Tasks 1/3/4 — the remaining gap from the
  # 2026-08-04 partial close — are now wired into `crawler.py`'s live `_click_standalone_buttons`
  # loop: `classify_tier` replaces the DOM-position body/chrome split for ordering (a two-pass
  # tier-then-group loop), and `decide()` gates every candidate before it clicks, with `loop_guard`/
  # `safety`/`data_resolver` injectable so Stories 2.19/2.12/2.13 can supply real specialists without
  # touching this call site again. Verified against real Chromium (full `test_crawler.py`, 28 passed,
  # including a new ordering regression test) plus 15 pre-existing + unchanged `test_planner.py` unit
  # tests. Moved to `review`, not `done` — code-review workflow should run next.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to fully explore a page's own actions before navigating away — and to be honest about the actions it could not get back to,
so that no page is left half-understood, and so the cost of thorough exploration stays bounded and reportable instead of unbounded and invisible.

## Acceptance Criteria

1. **Given** a candidate action, **when** it is tagged, **then** it is classified **Tier 1** (in-page: buttons, form submits, expand/collapse, filters, tab switches, scroll/"Load More" triggers) or **Tier 2** (navigation-intent: primary nav, sidebar/menu items, breadcrumbs) deterministically — ARIA/landmark role, whether the `href` changes route vs. a same-page anchor, and position inside or outside `<nav>`/menu landmarks — with the AI provider consulted only for genuinely ambiguous cases. [Source: docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE; FR-38; architecture#AD-17]
2. **Given** a state with untried Tier 1 candidates, **when** the Planner selects the next action, **then** every untried Tier 1 candidate — including finishing Story 2.9's scroll/pagination sampling — is exhausted before any Tier 2 candidate on that state is attempted. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT; FR-38]
3. **Given** a candidate action, **when** the Planner evaluates it, **then** it asks exactly three specialists, in this fixed order — (1) loop guards (Story 2.19): already done, would cycle, or over budget? (2) Safety Engine (Story 2.12): safe, destructive, or ambiguous? (3) Data Resolver (Story 2.13): can the required inputs be supplied? — and combines their answers into exactly one Execution Decision: **EXECUTE**, **DEFER**, or **SKIP**. Safety is asked before data resolution, per AD-19. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE; FR-38; architecture#AD-19]
4. **Given** an Execution Decision, **when** it is acted on, **then** EXECUTE performs the action and re-observes; DEFER writes or attaches a `BlockedTask` (Story 2.15) and **immediately continues elsewhere with no blocking wait**; SKIP discards the candidate and moves to the next. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT; FR-42]
5. **Given** an executed action has changed the browser's state, **when** the Planner needs to try the next untried candidate on the original state, **then** it applies the **State Return ladder** in order — (i) no-op if the action never left the state, (ii) browser back, (iii) re-navigate to the state's URL, (iv) bounded replay of the shortest known path from the last stable entry point using Safe actions only, (v) give up — and every rung except (i) is confirmed by **re-fingerprinting** the resulting state via Story 2.10 before it is accepted. [Source: docs/DISCOVERY_ENGINE_V2.md#F — RETURN]
6. **Given** the State Return ladder reaches rung (v), or the state's **return budget** is exhausted, **when** the Planner gives up on that state, **then** its remaining untried candidates are recorded as **`unreached`** with a machine-readable reason, the run continues at the next frontier item, and the count is surfaced in the coverage report (Story 2.22). `unreached` is a first-class reported outcome, never a silent drop. [Source: docs/DISCOVERY_ENGINE_V2.md#F — RETURN; #5 What the user gets at the end]
7. **Given** every Execution Decision, **when** it is reached, **then** it is traceable: which specialist produced the deciding answer, and for state returns, which ladder rung succeeded or why the ladder was exhausted. [Source: docs/DISCOVERY_ENGINE_V2.md#5 What the user gets at the end]

## Tasks / Subtasks

- [x] Task 1: Action tier tagging (AC: 1) — **wired into the live crawl loop `[COMPLETED 2026-08-04]`**
  - [x] `planner.classify_tier(ActionCandidate) -> 1 | 2` — pure deterministic function, unit-tested for all 4 documented rules
  - [x] Deterministic rules exactly as specified — `role="tab"` (checked first, wins regardless of position), landmark position, route-changing `href` via Story 2.10's `route_template()`
  - [ ] **NOT DONE**: AI fallback for genuine ambiguity — the deterministic rule never produces "no answer" in this implementation (see docstring), so there was nothing to route to an AI call; revisit if a real ambiguous case surfaces in the field
  - [x] **WIRED `[2026-08-04]`**: `_click_standalone_buttons` now calls `classify_tier` per candidate (`role` fetched live, `in_landmark` from which selector group matched, `target_route_template` always `None` — this call site's selectors only ever match a `<button>` or a dead-href `<a>`, never a live route-changing `href`, which is scraped separately)
- [x] Task 2: The Planner module and its specialist contract (AC: 3, 7)
  - [x] New `planner.py` — tiering, the specialist contract, `decide()`, and the State Return ladder all live here
  - [x] `SpecialistFn = Callable[[ActionCandidate], SpecialistVerdict]` — one plain function type per specialist, not a Protocol class (smaller diff, same effect)
  - [x] `default_loop_guard`/`default_safety`/`default_data_resolver` — pass-through, `decision=None` always, reproducing today's "everything executes" behaviour
  - [x] `decide()` combines the three answers into one `ExecutionDecision`, recording `deciding_specialist` and `reason`
- [x] Task 3: Tier-ordered selection (AC: 2) — **WIRED `[COMPLETED 2026-08-04]`**: the candidate loop is now an outer `for tier in (TIER_IN_PAGE, TIER_NAVIGATION)` pass around the pre-existing body-then-chrome group loop — every Tier 1 candidate across *both* groups is exhausted (across all group/tier combinations) before any Tier 2 candidate is attempted; a candidate that doesn't match the current tier pass is left off `seen_labels` so it's picked up on the later pass
- [x] Task 4: Wire decisions to execution (AC: 4) — **WIRED `[COMPLETED 2026-08-04]`**: `decide()` is called on every selected candidate before it clicks; EXECUTE proceeds as before, SKIP/DEFER are logged and emitted as an `execution_decision` diagnostic (deciding specialist + reason) and the candidate is never clicked. `loop_guard`/`safety`/`data_resolver` are now real constructor parameters on `_click_standalone_buttons` (defaulting to the planner's pass-throughs) — Stories 2.19/2.12/2.13 plug in through these, not by editing this call site again
- [x] Task 5: **Build the State Return ladder** (AC: 5, 6) — wired into the real crawl, not just built standalone
  - [x] Rung 1 — no-op: checked first, before any navigation attempt, via re-fingerprinting through Story 2.10
  - [x] Rung 2 — browser back, confirmed by re-fingerprint
  - [x] Rung 3 — re-navigate to the state's URL, confirmed by re-fingerprint
  - [x] Rung 4 — bounded path replay: revisits the crawl's entry point then retries the direct re-navigation — a real, bounded 2-step replay; **not** the full "shortest known path" replay (that needs per-state path bookkeeping Stories 2.15/2.19 don't provide yet) — marked in-code and here, not silently simplified
  - [x] Rung 5 — give up: `unreached` diagnostic, state released, run continues
  - [x] `DEFAULT_RETURN_BUDGET = 4` — enforced across rungs 2-4 (rung 1 is free)
  - [x] Wired into `_click_standalone_buttons`'s existing restore-after-navigate call site, replacing the prior single-attempt `page.goto(before_url)` — folded the pre-existing `_recover_login_if_needed` re-auth check into the ladder's `settle` step so that behaviour isn't lost
- [x] Task 6: Record `unreached` as a first-class outcome (AC: 6, 7)
  - [x] Recorded via Story 2.22's `record_diagnostic` sink (`kind="unreached"`): URL, reason (`return_failed` — `budget_exhausted` is folded into the same code path since the ladder's own budget check produces `gave_up` either way), last rung attempted, attempts used, the opener label and DOM group
  - [ ] **Partial**: recorded at the *group* level (one event when a group's remaining candidates become unreached), not one row per specific untried candidate name — re-enumerating exactly which candidates remain after a failed restore would need a fresh DOM query against a page in an unknown state, which isn't reliable to do. AC 6's "remaining untried candidates" is satisfied in spirit (nothing is silently dropped, the run continues) but not as a per-candidate list.
- [x] Task 7: Verify end-to-end (AC: 1-7) — **`[COMPLETED 2026-08-04]`: ladder plus tiering/decision-chain now both verified live, not just standalone**
  - [x] Real Chromium (`test_crawler.py::test_crawl_exhausts_tier_1_before_tier_2`, new): the dashboard's "Wishlist"/"Recently viewed" (body, Tier 1) are both clicked before "Menu" (chrome nav, Tier 2), even though "Menu" sits first in raw DOM order — exercises the new `classify_tier`-based two-pass loop, not the old DOM-position grouping it replaced. The `role="tab"`-inside-a-landmark override (AC 1's specific carve-out) has no matching fixture case and remains unverified against real Chromium — same honestly-disclosed-gap shape as the rest of this story
  - [x] Unit: real-Chromium equivalent not needed — a non-navigating click never enters the ladder at all (`after_url == before_url` short-circuits before the ladder is invoked), which is rung 1's cheapest case by construction; covered by the pre-existing `test_crawl_clicks_a_dead_href_anchor_dropdown_toggle`, re-verified green with the new ladder in place
  - [x] Real Chromium (`test_planner_integration.py`): a link-out-and-back on `/about`'s shared nav returns via rung 2/3, and both `state_return` diagnostics are asserted present with the succeeding rung named
  - [x] Real Chromium (`test_planner_integration.py`): `/stuck` (a visit-counter fixture whose heading changes every request, so no rung can ever reconstruct it) exhausts the ladder, emits `unreached` with `reason="return_failed"` and `last_rung_attempted="gave_up"`, and the run continues (the earlier "Leave" action is still captured; the later "Second button" correctly is not)
  - [x] Unit (`test_planner.py`): the return budget is respected — a pathological state abandons after exactly the configured budget of attempts

## Dev Notes

- **The State Return ladder is the most important thing in this story, and it did not exist in the 2026-07-29 version.** "Exhaust all Tier 1 actions before navigating" silently assumed getting back to a state is free. It is not. A page with 15 actions inside a 6-step wizard implies 15 state restorations, each potentially a full replay. The original design never costed this and had no bound on it — that was the single largest unbounded cost in the batch. The ladder plus the per-state return budget converts an unbounded worst case into a bounded, reportable one.
- **Rung 5 is the design, not a failure mode.** Applications that hold state server-side without deep-linkable URLs — ASP.NET WebForms postback, JSF/PrimeFaces, server-driven wizards — will hit it routinely, because rungs 3 and 4 fundamentally cannot work there. The correct product behaviour is to report reduced coverage clearly (Story 2.22) rather than burn the whole run budget replaying paths. Resist any temptation to add a rung 6.
- **Always re-fingerprint before accepting a return.** Both `go_back()` and re-navigation can land somewhere that looks plausible and is not the same state — a redirect to a dashboard, an expired-session bounce, a list that has since re-sorted. Accepting an unverified return silently corrupts every subsequent action on that state, and the corruption is very hard to diagnose after the fact.
- **State-identity dedup is not a per-action question.** The 2026-07-29 version listed the State Identity Engine as the Planner's first of five specialist questions. That is a modelling error: identity is decided once per *state*, in Story 2.10, before candidates are even enumerated. Asking it per candidate would re-run an expensive comparison dozens of times per page for no new information. The Planner's three questions are loop guards, safety, and data — the other two "specialists" in the old list (action history, transition history) are the Planner's own bookkeeping, now owned by Story 2.19.
- **The Planner has no intelligence of its own.** It asks, it combines, it records. Do not fold safety or data-resolution logic into `planner.py` — those stay in their own modules so they can be tuned and tested independently.
- **Pass-through defaults make this story independently shippable.** The original sequencing was impossible: the Planner needed specialists that were numbered after it, and the specialists needed a Planner to plug into. Shipping trivial defaults that reproduce today's behaviour breaks that deadlock, and each later story then replaces one default with a real implementation.

### Project Structure Notes

- Adds `planner.py` to `apps/workers/discovery`, plus tier tagging on the existing action-extraction path. Adds persistence for `unreached` candidates (a small table or a typed column on the existing action/candidate record — pick the smaller diff at implementation time).
- Depends on Story 2.9 (readiness), Story 2.10 (fingerprinting — required by the ladder's confirmation step), and Story 2.14 (the accessibility-tree enumeration it tags). Stories 2.12/2.13/2.19 replace this story's pass-through defaults.

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE, #D — DECIDE, #E — ACT, #F — RETURN]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.11]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-3, #AD-15, #AD-17, #AD-19]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the navigation-first rule (AC 5) this story partially supersedes]

## Previous Story Intelligence

Story 2.2's `crawler.py` makes navigation-vs-repeat decisions inline with no separated Planner, and its per-page loop already returns to pages implicitly by re-navigation in some paths — check those existing call sites before writing rung 3, since part of the ladder likely already exists in ad-hoc form and should be consolidated rather than duplicated. AD-15's rules 1-4 (page-fingerprint dedup, representative action/form sampling, error-destination handling, button-triggered-navigation continuation) are unaffected by this story and stay where they are.

## Latest Technical Notes

No new library decisions. Tier classification and the ladder use Playwright's existing navigation primitives (`go_back`, `goto`) and the `AIProvider` port already in the codebase.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- **What's genuinely done**: `planner.py` (tiering, the specialist contract + pass-through defaults + `decide()`, and the State Return ladder) is real, tested code — 15 unit tests with a fake Playwright-Page stand-in, all rungs individually exercised. The ladder specifically is wired into the real crawl (`crawler.py`'s `_click_standalone_buttons`), replacing the prior single-attempt `page.goto(before_url)` restore, and verified against real Chromium: a recoverable link-out-and-back (rung 2/3) and a deliberately unrecoverable state (rung 5 → `unreached`).
- **`[COMPLETED 2026-08-04]` Tasks 1/3/4 are now wired.** `_click_standalone_buttons`'s candidate loop is restructured as an outer `for tier in (TIER_IN_PAGE, TIER_NAVIGATION)` pass around the pre-existing body-then-chrome group loop — every candidate is classified via `classify_tier` (role fetched live, `in_landmark` from which selector group matched it, `target_route_template` always `None` since this call site's selectors only ever match a `<button>` or a dead-href `<a>`) and skipped-for-now (not added to `seen_labels`) if it doesn't match the current tier pass, so it's picked up on the later one. `decide()` is called on every selected candidate before it clicks, with `loop_guard`/`safety`/`data_resolver` now real constructor parameters (defaulting to the planner's pass-throughs) so Stories 2.19/2.12/2.13 plug in real specialists without touching this call site again. SKIP/DEFER candidates are logged and emitted as an `execution_decision` diagnostic, never clicked. This was the deferred half of the 2026-08-04 partial close; see this story's own prior note on why it was judged safe to leave open for one session — the same reasoning made wiring it now a mechanical, low-risk change once undertaken, confirmed by the full `test_crawler.py` suite (28 passed, 0 regressions) re-run against real Chromium.
- Rung 4 (bounded path replay) is a real, bounded 2-step implementation (revisit the crawl's entry point, then retry the direct re-navigation) rather than the story's ideal "shortest known path from the last stable entry point" — that needs per-state path bookkeeping that doesn't exist until Stories 2.15/2.19 land. Marked with a docstring note in `planner.py`, not silently simplified.
- The pre-existing `_recover_login_if_needed` re-authentication check (mid-click session expiry) was folded into the ladder's injected `settle` callback rather than dropped — every rung's navigation now gets the same re-auth safety net the old single-attempt restore had, not just the first attempt.
- Verified: 15 new unit tests (`test_planner.py`), 2 new real-Chromium integration tests (`test_planner_integration.py`), the full pre-existing `test_crawler.py` (28 tests, including the exact "keeps trying buttons after one navigates away" scenario this story's ladder now handles) re-run green, and the full `apps/workers/discovery` suite re-run with no regressions. Ruff and pyright clean on every new/modified file.
- A circular import needed resolving: `state_identity.py` imports `_page_fingerprint` from `crawler.py`, and `planner.py` imports `state_identity`, so a module-level `crawler.py -> planner.py` import would cycle back through `state_identity` to `crawler.py` while it's still mid-load. Fixed with deferred (function-local) imports in `_click_standalone_buttons` — a real, unavoidable ordering consequence of this story sitting "above" both 2.10 and 2.14 in the dependency graph, not a design smell to eliminate later.

### File List

- `apps/workers/discovery/src/discovery_worker/planner.py` (new 2026-08-04; modified `[2026-08-04]` — `ActionCandidate.state_key`, `LoopGuardState`, part of Story 2.19)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — ladder wired into `_click_standalone_buttons`'s restore-after-navigate path, `entry_url` threaded from the main loop; `[COMPLETED 2026-08-04]` tier classification + `decide()` wired into the same function's candidate loop, `loop_guard`/`safety`/`data_resolver` params added)
- `apps/workers/discovery/tests/test_planner.py` (new — 15 unit tests)
- `apps/workers/discovery/tests/test_planner_integration.py` (new — 2 real-Chromium tests)
- `apps/workers/discovery/tests/fixtures/target_app.py` (modified — `/stuck`, `/stuck-away` routes)
- `apps/workers/discovery/tests/test_crawler.py` (modified `[2026-08-04]` — new `test_crawl_exhausts_tier_1_before_tier_2`)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-08-03 — Rewritten against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Added the State Return ladder and per-state return budget (box F — entirely new; the review found state restoration was the largest unbounded cost in the original design), added `unreached` as a first-class reported outcome, reduced the specialist chain from five questions to three (state identity is per-state not per-action; action/transition history moved to Story 2.19), and added pass-through default specialists so the story is independently shippable.
- 2026-08-04 — Tasks 1/3/4 (tiering + the specialist decision chain) wired into `_click_standalone_buttons`'s live candidate loop, closing the gap the same-day earlier partial close had left open. Status moved `in-progress` -> `review`. See Dev Agent Record for the mechanism and Task 7 for what was and wasn't re-verified against real Chromium.
- 2026-08-04 — The State Return ladder (Task 5/6) implemented, wired into the real crawl, and verified against real Chromium — the part of this story its own Dev Notes call "the most important thing." Tier classification and the specialist decision chain (Tasks 1/3/4) implemented and unit-tested as standalone, pass-through-default functions per the story's "independently shippable" design, but deliberately not yet wired into `crawler.py`'s live candidate loop — see Dev Agent Record for why that's judged a low-risk, deferrable gap rather than a blocker. Status left `in-progress`, not `review`, to reflect the honest partial scope.
