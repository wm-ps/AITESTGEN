---
last_updated: 2026-10-27
---

# Story 2.3: Discovery Completion and Stop Limits

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want a Discovery run to finish when there is nothing new left to explore, or when it reaches the limits my admin set,
so that Discovery always ends and I know its result is final.

## What it does today

- A run finishes in one of three ways:
  - **Everything explored:** there are no new pages left to visit.
  - **Page limit reached:** the admin's "Maximum pages" setting (default 500).
  - **Time limit reached:** the admin's "Maximum discovery time" setting (default 30 minutes). The limit is checked between pages and also partway through a page.
- In all three cases the run is marked complete, and Vantage records which of the three reasons ended it.
- Vantage then builds the application model (Story 2.5) and groups pages into journeys (Story 2.6). Journeys appear on the Journeys tab once that is done.
- Finishing Discovery does **not** start scenario or test generation. The user starts that by clicking "Review scenarios" on the Journeys tab.
- A run that ends because sign-in was lost, or because of a crash it couldn't recover from, is marked failed, never complete (Stories 2.4 and 2.18).
- A paused run stays paused until it is resumed (Story 2.17).
- Admins set the limits on the Settings page. They apply to every application.

## Acceptance criteria

1. **Given** a running Discovery run, **when** no new pages remain, **then** the run is marked complete with the reason "everything explored".
2. **Given** the number of pages explored passes the Maximum pages setting, **then** the run stops and is marked complete with the reason "page limit".
3. **Given** the run time passes the Maximum discovery time setting, **then** exploring stops, even partway through a page, and the run is marked complete with the reason "time limit".
4. **Given** a run is complete, **then** journey grouping runs and journeys appear on the Journeys tab; no scenario or test generation starts until the user asks for it.
5. **Given** a run ended because sign-in was lost or because of an unrecoverable crash, **then** it is marked failed, never complete.
6. Wherever the run's state is shown, it comes from the run's own recorded status, never from guessing based on whether journeys exist.

## Gaps / not built

- The stop reason is recorded but not shown on any screen, so a user can't tell a run that hit a limit from one that explored everything (see Story 2.22).
