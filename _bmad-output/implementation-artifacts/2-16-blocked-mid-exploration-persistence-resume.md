---
last_updated: 2026-10-27
---

# Story 2.16: Remembering the Route to a Blocked Area & Resuming It

Status: in-progress

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want the route to a blocked area remembered, and the area explored once I supply what was missing,
so that answering the question actually unblocks Discovery, without Vantage blindly re-submitting forms and creating duplicate records in my application.

## What it does today

- When an action is put aside (Story 2.15), Vantage saves the ordered steps it took to get there: each page, the action taken and the values typed. Each step points at the already-recorded page rather than copying it.
- The saved steps are a readable record of how Vantage reached the blocked point. They are **not** a script to replay.
- If the same route blocks again further along, the existing blocked item is extended rather than a new one being created.
- The resume behaviour is built but nothing in the product triggers it. It would:
  - save the supplied value into the test data pool under the blocked item's name
  - open a fresh browser session
  - re-explore from the nearest page on the saved route that can be opened directly by its address, following normal rules (no stored step is blindly repeated)
  - mark the item resolved once the value gets through
  - fall back to the application's start page, and say so, if no page on the route can be opened directly

## Acceptance criteria

1. **Given** a block after several successful steps, **then** those steps are saved in order, each pointing at its recorded page with the action and values used.
2. **Given** saved steps, **then** they are kept as a readable record, not a replay script.
3. **Given** a resumed route blocks again further along, **then** the same blocked item is extended.
4. *(Not reachable today)* **Given** a user supplies the missing value, **then** it is saved to the test data pool, Vantage re-explores from the nearest directly openable page on the route, and the item is marked resolved when the value gets through.
5. *(Not reachable today)* **Given** no page on the route can be opened directly, **then** re-exploring starts from the application's start page and this is reported.

## Gaps / not built

- There is no screen or action for supplying a missing value or approving a blocked action, and nothing starts the resume behaviour. Blocked areas therefore stay unexplored.
- The saved route isn't shown to users. The coverage report doesn't include it yet.
