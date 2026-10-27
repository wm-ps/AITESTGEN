---
last_updated: 2026-10-27
---

# Story 2.5: Application Model Builder

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to merge duplicate captures into one clean, reusable model of my application,
so that journeys and tests are built from reliable, de-duplicated information.

## What it does today

- After exploring finishes, and before journeys are grouped, Vantage tidies up what it captured:
  - Pages, forms and data calls that are really the same thing are merged, leaving one official copy of each. The duplicates point to it.
  - From the actions on each page, it works out the reusable "components" a test can interact with. Each one gets a preferred way of finding it on the page plus backup ways (Story 2.21 covers how durable these are).
  - From what happened after actions (the page changed, a data call was made), it works out expected outcomes that tests can check.
- The tidy-up is safe to repeat: running it again doesn't create new duplicates.
- Journey grouping and test generation only ever use the official copies.
- While this is happening, the user still sees Discovery as in progress.

## Acceptance criteria

1. **Given** exploring has finished, **when** the model is built, **then** captures that represent the same page, form or data call are merged into one official copy per application.
2. **Given** the official pages, **then** reusable components are worked out from their actions, each with a preferred and a backup way of finding it.
3. **Given** the official pages, **then** expected outcomes are worked out from the page changes and data calls that followed actions.
4. **Given** the build runs more than once, **then** the result is the same and no new duplicates appear.
5. **Given** journey grouping or test generation runs later, **then** it reads only the official copies.
