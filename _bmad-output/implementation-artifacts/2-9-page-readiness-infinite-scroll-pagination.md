---
last_updated: 2026-10-27
---

# Story 2.9: Page Readiness & Bounded Sampling

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to wait until a page has really finished loading before recording it, and to sample long or endless lists instead of scrolling them to the end,
so that Discovery records complete, accurate pages and never gets stuck on endless content.

## What it does today

- **Waiting for the page.** Before recording a page, Vantage waits for three things:
  - The page has stopped loading data. Background chatter such as analytics or regular polling is ignored.
  - The page has stopped changing on screen for a short moment.
  - The page actually shows some content.
- **Never blocked by a slow page.** If a page hasn't settled by the navigation timeout, Vantage records it anyway as best it can, notes the slow page as a coded error (Story 2.18) and moves on. A slow page never stops or fails the run.
- **Timeout setting.** The default timeout is 15 seconds. Admins change it with "Navigation timeout" on the Settings page; it applies to every application.
- **Long lists and "Load more".** When Vantage finds an endless-scroll area, a "Load more" button or pagination, it loads a little more, looks at what appeared, and stops once three loads in a row only show more of the same kind of item. A hard limit of 20 loads per page stops it on lists that never settle. Then it moves on to other parts of the page.

## Acceptance criteria

1. **Given** Vantage arrives on a page, **when** it checks readiness, **then** it waits until relevant data loading has stopped, the page has stopped changing, and content is showing.
2. **Given** a page hasn't settled by the navigation timeout, **then** it is recorded anyway, a slow-page error is logged, and the run continues.
3. **Given** the admin has set a Navigation timeout in Settings, **then** that value is used; otherwise the default of 15 seconds applies.
4. **Given** an endless-scroll area, "Load more" button or pagination, **when** three loads in a row reveal only more of the same, **then** sampling stops and exploring continues elsewhere.
5. **Given** a list whose content never settles, **when** the per-page load limit is reached, **then** sampling stops anyway.
