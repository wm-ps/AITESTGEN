---
last_updated: 2026-10-27
---

# Story 2.15: Blocked Items — One Combined Request per Missing Thing

Status: in-progress

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want every part of Discovery blocked on the same missing thing combined into one request,
so that I answer once instead of once per page, even when the request was worded slightly differently each time.

## What it does today

- An action can be put aside for two reasons:
  - It needs a business-specific value Vantage doesn't have (Story 2.13).
  - It needs approval to run (Story 2.12, "production" caution level).
  Either way, Vantage records a blocked item and **immediately carries on elsewhere**. A blocked area never stops, pauses or slows the run.
- Blocked items are grouped by a normalised version of the field name (lower-case, punctuation dropped, word order ignored), together with the kind of input and the kind of page. "Active Policy Number" and "Policy Number (Active)" therefore become one blocked item, not two. Each item counts how many paths are waiting on it.
- Missing data and missing approval are recorded the same way. One item can need both.
- The route Vantage took to reach the blocked point is saved with the item (Story 2.16).
- Blocked items are listed, one per missing thing with the number of waiting paths, in the coverage report (Story 2.22).
- If the application's test data pool (Story 2.20) already holds a value under the same normalised name, that value is used and nothing is blocked.

## Acceptance criteria

1. **Given** an action is put aside, **then** a blocked item is recorded under the normalised field name, input kind and page kind, and a matching open item is added to rather than duplicated.
2. **Given** two requests worded differently that normalise to the same name, **then** there is exactly one open blocked item.
3. **Given** a request for data and a request for approval, **then** both use the same record, and one item can carry both.
4. **Given** any block, **then** Vantage continues exploring elsewhere straight away.
5. **Given** a test data pool value with the same normalised name, **then** the field is filled from the pool and not blocked.
6. **Given** a finished run, **then** the coverage report lists one entry per blocked item with the number of paths waiting on it.

## Gaps / not built

- Blocked items aren't shown anywhere in the product. They appear only in the coverage report, which has no screen (Story 2.22).
- A user can't supply the missing value or give approval, and there is no "finish without it" option. Supplying values and resuming is Story 2.16 and is not wired up.
