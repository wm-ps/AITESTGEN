---
last_updated: 2026-10-27
---

# Story 2.18: Crash Recovery & Discovery Error Codes

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As the team running Vantage,
I want Discovery to recover by itself from a crash, and every problem with the application under test to be logged with a fixed code and a plain explanation,
so that temporary failures don't quietly corrupt or cut short a Discovery's results.

## What it does today

- **Crash recovery.** Pages are saved as they are found. If the discovery service crashes or restarts mid-run, the run is retried automatically:
  - It continues past the pages already confirmed instead of starting over.
  - Anything that was in progress at the moment of the crash is treated as unconfirmed and checked again.
  - The Journeys tab shows "Recovered from a worker restart — resuming from where it left off."
- **Problems with the application under test.** A page that keeps failing after a couple of retries (server errors, unreachable, never finishes loading) is logged as an error. Exploring continues elsewhere, and the page is never mistaken for a new screen or silently dropped.
- **Error codes.** Every logged error has one of six fixed codes plus a plain-language message, often with a suggested next step (for example "Check whether the target application was under maintenance during this run"):

  | Code | Meaning |
  |---|---|
  | DISC-001 | Vantage restarted the run after a crash |
  | DISC-002 | The application's sign-in session was lost |
  | DISC-003 | A page was unreachable or kept returning server errors |
  | DISC-004 | A page didn't finish loading in time (it was still recorded) |
  | DISC-005 | Vantage lost its place after submitting a form and couldn't get back |
  | DISC-006 | Filling a form field took too long |

- Errors are listed in the coverage report alongside blocked and skipped-for-safety items (Story 2.22).
- If a crash can't be recovered from, the run is marked failed with the reason saved, rather than staying "running" forever.

## Acceptance criteria

1. **Given** the discovery service restarts mid-run, **then** the run is retried automatically, continues past pages already confirmed, re-checks whatever was in progress, and the Journeys tab shows the recovery message.
2. **Given** a page keeps failing after a small number of retries, **then** it is logged as an error and exploring continues elsewhere.
3. **Given** any discovery error, **then** it carries one of the six fixed codes and a plain-language message.
4. **Given** a crash that can't be recovered from, **then** the run is marked failed with a saved reason.

## Gaps / not built

- Discovery errors aren't shown on any screen; they appear only in the coverage report (Story 2.22).
