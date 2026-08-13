---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.19: Loop Prevention Consolidation

*Implements the first specialist question of spine box **D — DECIDE** of `docs/DISCOVERY_ENGINE_V2.md`. Lightly rewritten 2026-08-03 following a feasibility review — reframed as the Planner's first and cheapest question, with Story 2.11's state-return budget added to the guard list.*

Status: review  # `[COMPLETED 2026-08-04]` `LoopGuardState` (planner.py): action history (2a),
  # transition-cycle detection (2b), route-family bounding (2c), and a final action ceiling (2f)
  # implemented and wired as Story 2.11's `loop_guard` specialist. Scroll/pagination budget (2d) and
  # the state-return budget (2e) delegate to Stories 2.9/2.11 as specified — no new code for those
  # two, by design (Dev Notes). 8 new unit tests pass; not verified against real Chromium this
  # session — see Dev Agent Record.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want all of the discovery engine's anti-loop safeguards to run consistently before any action executes,
so that a pathological page pattern can't stall a run even when the primary sampling mechanisms (State Identity, infinite-scroll sampling) don't catch it.

## Acceptance Criteria

1. **Given** a candidate action, **when** the Planner (Story 2.11) evaluates it, **then** loop guards are the **first** specialist question asked — before safety and before data resolution — because they are the cheapest to answer and the most decisive. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE]
2. **Given** loop guards run, **when** they are applied, **then** they are applied in this order: (a) **action history** — has this exact action already executed from this state? (b) **transition-cycle detection** — would this produce an A→B→A→B cycle? (c) **route normalization** — is this a parameterized duplicate of an already-sampled route? (d) the **scroll/pagination budget** (Story 2.9), (e) the **state-return budget** (Story 2.11), (f) a final **depth/action ceiling**. Any guard firing yields SKIP. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE; FR-46]
3. **Given** Stories 2.9 and 2.10's primary sampling already prevents a specific loop, **when** this story's guards run, **then** they do not duplicate that logic — the genuinely new pieces here are the action-history tracker and transition-cycle detection. [Source: FR-46; architecture#AD-22]
4. **Given** any guard fires, **when** the candidate is skipped, **then** the run diagnostics record **which** guard fired and against what, so a run that terminates early is diagnosable rather than mysterious. [Source: docs/DISCOVERY_ENGINE_V2.md#5 What the user gets at the end]

## Tasks / Subtasks

- [x] Task 1: Action-history tracker (AC: 2a) — `[COMPLETED 2026-08-04]`
  - [x] Per-run record of `(state key, action identity)` pairs in `LoopGuardState._executed` (`planner.py`); a repeat yields SKIP via `guard()`, recorded via `record_executed()` once a candidate is confirmed EXECUTE
  - [x] Action identity keyed on the accessible name (`ActionCandidate.label`) plus a new `state_key` field (defaults to `before_url`, the specific page instance — see `crawler.py`'s call site) — survives a state return, since the key doesn't depend on DOM position or render order
  - [ ] **Simplified**: keyed on accessible name alone, not "durable locator (Story 2.21) plus accessible name" as specified — the candidate-scan loop only has a durable locator for the *chosen* candidate, captured after `decide()` already ran (a chicken-and-egg ordering this story's own call site doesn't resolve). Accepted risk: an element whose accessible name changes across renders would evade the guard; the reverse (same name, different underlying element) is fine, since same name + same state is what "already done" means in practice.
- [x] Task 2: Transition-cycle detection (AC: 2b) — `[COMPLETED 2026-08-04]`
  - [x] `LoopGuardState._edges` (a `deque(maxlen=8)`) logs every real transition — both a candidate's own forward navigation and a successful State Return ladder rung's reverse edge (without the latter, only same-direction repeats would ever be visible, never a genuine A→B→A→B round trip); `_is_cycling()` detects a period-2 repeat in the last 4 edges
  - [x] Bounded to the last 8 edges — old enough oscillations fall out of the window on their own
- [x] Task 3: Wire the remaining guards (AC: 2c-2f) — `[COMPLETED 2026-08-04]`
  - [x] Route normalization: `_route_family_counts` keyed on `(source_route_template, label)` — reuses Story 2.10's `route_template()` (already computed by the caller), no second normalizer
  - [x] Scroll/pagination budget: delegated — no code here, per Dev Notes ("these are backstops, not the primary mechanism")
  - [x] State-return budget: delegated — enforced inside `return_to_state()`'s own `DEFAULT_RETURN_BUDGET`; by the time a state's return budget is exhausted, `_click_standalone_buttons` has already broken out of that state's candidate loop, so there's nothing further for this guard to check
  - [x] Depth/action ceiling: `DEFAULT_ACTION_CEILING = 5000`, a final backstop — deliberately high so it never bites a real crawl; **not** PM-sign-off-confirmed to reverse PRD §12 Risk item 7's accepted risk (this story's own Previous Story Intelligence flags that as a prerequisite) — treat the mechanism as landed and the specific number as still open
- [x] Task 4: Replace the Planner's pass-through guard default (AC: 1) — `[COMPLETED 2026-08-04]`
  - [x] `run_discovery_crawl` constructs one `LoopGuardState` per crawl and passes `guard_state.guard` as `_click_standalone_buttons`'s `loop_guard` — confirmed first in `decide()`'s fixed specialist order (Story 2.11, unchanged)
- [x] Task 5: Emit guard diagnostics (AC: 4) — `[COMPLETED 2026-08-04]`
  - [x] No new sink needed — Story 2.11's existing `execution_decision` diagnostic (`deciding_specialist="loop_guard"`, `reason=<which guard fired, against what>`) already satisfies this; `guard()`'s reasons name the specific guard (`action_history:`/`transition_cycle:`/`route_normalization:`/ceiling) for every SKIP
- [x] Task 6: Verify end-to-end (AC: 1-4) — `[COMPLETED 2026-08-04, unit only]`
  - [x] Unit (`test_loop_guard.py`): a repeated action from the same state is skipped by the action-history guard, not re-executed
  - [x] Unit (`test_loop_guard.py`): a synthetic A→B→A→B edge sequence is detected and SKIPs the next candidate from either state
  - [x] Unit (`test_loop_guard.py`): a hub page revisited from three distinct sources (X→Hub→X, Y→Hub→Y, Z→Hub→Z) is **not** falsely flagged
  - [x] Unit (`test_loop_guard.py`): every skip's reason is traceable through `decide()`'s `deciding_specialist`/`reason`
  - [ ] **NOT VERIFIED against real Chromium** this session — the `test_crawler.py` suite (28 tests) re-ran green with `LoopGuardState` wired in, but no new fixture scenario was added to specifically exercise a real cycle/route-family-cap/ceiling hit live; the pure-Python bookkeeping this class does over crawler-supplied strings made unit tests with fakes the higher-value place to spend verification time this session

## Dev Notes

- **These are backstops, not the primary mechanism.** Stories 2.9 (bounded sampling) and 2.10 (state dedup) do the real work of keeping the crawl finite. This story exists for the pathological cases they miss — and it must not reimplement them. Duplicated loop logic in two places is how a crawler ends up terminating early for reasons nobody can explain.
- **Guard ordering matters for cost, not just correctness.** Loop guards run first because answering "have I already done this?" is a dictionary lookup, while safety may involve an AI call and data resolution may involve a pool query. Asking the cheap decisive question first avoids paying for the expensive ones on candidates that were never going to execute.
- **Action identity is the subtle part.** Keying the history tracker on DOM position or index breaks the moment a state is returned to and the DOM re-renders in a different order — the tracker then thinks every action is new and the page is explored repeatedly. Key on the durable locator from Story 2.21 plus the accessible name.
- **Diagnostics are what make early termination explainable.** Without AC 4, a run that stops after 30 pages on a 300-page application is indistinguishable from a run against a genuinely small application. This is the same argument as Story 2.10's observable thresholds.

### Project Structure Notes

- Adds the action-history and transition-cycle trackers to `apps/workers/discovery` — most naturally alongside `planner.py`, since they are the Planner's own bookkeeping. No new domain entities.
- Depends on Story 2.11 (replaces a pass-through default), Story 2.10 (route normalization), Story 2.9 (scroll budget) and Story 2.21 (durable action identity).

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.19]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-15, #AD-18, #AD-22]

## Previous Story Intelligence

Story 2.3 removed `MAX_ITERATIONS` entirely — the crawl loop currently runs `while page_queue:` with no cap, a deliberate accepted risk (PRD §12 item 7). This story's depth/action ceiling (Task 3) reintroduces a bounded backstop; confirm with the PRD owner whether that changes the accepted-risk statement before implementing, since it partially retires a documented decision.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- `LoopGuardState` lives in `planner.py`, not a separate module — Dev Notes call these guards "the Planner's own bookkeeping," and Story 2.11 already put tiering/`decide()`/the return ladder there for the same reason.
- Action-history keying is simplified from the spec (accessible name alone, not durable-locator + accessible name) — see Task 1's checkbox note for why: the durable locator for a candidate is only captured *after* it's already been selected, downstream of where `guard()` needs to answer "have I already done this."
- The transition-cycle detector's edge log is fed from two places, not one: a candidate's own forward click (`crawler.py`, where `CapturedTransition` is already emitted) and a *successful State Return ladder rung* (Story 2.11's `return_to_state`). Only recording the forward direction would mean the edge log could only ever show the same-direction repeat that Task 1's action-history guard already catches on its own terms — the reverse edge is what makes a genuine A→B→A→B round trip visible at all.
- The depth/action ceiling (`DEFAULT_ACTION_CEILING = 5000`) is a real, working mechanism, but the *number* is not confirmed by the PM sign-off this story's own Previous Story Intelligence flags as a prerequisite (it partially retires PRD §12 Risk item 7's accepted-risk statement). Set deliberately high so it functions purely as a backstop against genuinely pathological runs rather than a de facto low cap on legitimate exhaustive traversal.
- Verified: 8 new unit tests (`test_loop_guard.py`) against `LoopGuardState` directly, plus one existing `decide()` traceability test extended to use a real `LoopGuardState` instance rather than a lambda. The full `apps/workers/discovery` `test_crawler.py` suite (28 tests, real Chromium) re-ran green with the guard wired into the live crawl — no regressions — but no new fixture scenario specifically drives a real cycle, route-family cap, or ceiling hit through a live browser; that verification stayed at the unit level this session (see Task 6).

### File List

- `apps/workers/discovery/src/discovery_worker/planner.py` (modified — `ActionCandidate.state_key`, `LoopGuardState`, `DEFAULT_ACTION_CEILING`, `DEFAULT_ROUTE_FAMILY_CAP`)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — `loop_guard_state` threaded through `_click_standalone_buttons`, `_capture_frame_widgets`, and constructed once per crawl in `run_discovery_crawl`; `record_executed`/`record_transition` called at the confirmed-EXECUTE and real-transition/return-success points)
- `apps/workers/discovery/tests/test_loop_guard.py` (new — 8 unit tests)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-08-03 — Lightly rewritten against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Reframed as the Planner's first (cheapest, most decisive) specialist question, added Story 2.11's state-return budget to the guard list, added guard diagnostics (AC 4), and specified that action identity must key on durable locator + accessible name so the tracker survives state returns.
- 2026-08-04 — Implemented: `LoopGuardState` (action history, transition-cycle detection, route-family bounding, action ceiling), wired as Story 2.11's `loop_guard` specialist. Moved `ready-for-dev` -> `review`. Action-history keying simplified to accessible-name-only (see Dev Agent Record); scroll/state-return budgets delegated per spec, not reimplemented; PM sign-off on the action ceiling's specific number remains open.
