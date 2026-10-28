---
last_updated: 2026-10-27
---

# Story 2.19: Loop Prevention

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to check for loops before every action it takes,
so that a strange page pattern can't stall a Discovery run, even when the main sampling rules don't catch it.

## What it does today

- Loop checks are the first and cheapest question Vantage asks before any action, ahead of safety and data (Story 2.11). If any check fires, the action is skipped.
- The checks are:
  1. **Already done:** has this exact action already been performed from this screen?
  2. **Going in circles:** would it bounce between the same screens (A → B → A → B)?
  3. **Same thing, different ID:** is this the same action on the same kind of page, already tried a few times with only an ID changed? A few are sampled; the rest are skipped.
  4. **List sampling budget:** reuses the per-page limit from Story 2.9.
  5. **Return budget:** reuses the per-screen limit for getting back to a page, from Story 2.11.
  6. **Overall ceiling:** a very high cap on total actions per run, as a last resort for runaway cases. It is set high enough that it shouldn't affect a normal run.
- Where Stories 2.9 and 2.10 already prevent a loop, these checks reuse their limits instead of duplicating them.
- Whenever a check fires, the diagnostics record which one fired and on what action, so a run that ended early can be explained.
- The admin's page and time limits (Story 2.3) also guarantee every run ends.

## Acceptance criteria

1. **Given** any action, **then** loop checks are asked before safety and data checks.
2. **Given** loop checks run, **then** already done, going in circles, same-thing-different-ID, list budget, return budget and overall ceiling are applied in that order, and any one firing skips the action.
3. **Given** Stories 2.9 or 2.10 already cover a loop, **then** their limits are reused, not duplicated.
4. **Given** a check fires, **then** diagnostics record which check fired and on what action.

## Gaps / not built

- The overall action ceiling hasn't had product sign-off on its exact value; only the number may change, not the mechanism.
