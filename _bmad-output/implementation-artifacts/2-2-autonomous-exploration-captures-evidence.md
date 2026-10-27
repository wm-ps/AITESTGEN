---
last_updated: 2026-10-27
---

# Story 2.2: Autonomous Exploration Captures the Application Model

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to explore my application on its own in a real browser and record what it finds,
so that there is a structured picture of the application to build journeys and tests from.

## What it does today

- Vantage opens the application in a real browser, signs in if needed, and explores it on its own, working outward from the start page.
- For every page it records:
  - the page itself (heading, screenshot, layout)
  - its forms, their fields and their validation rules
  - its buttons and other actions
  - the background data calls the page made
  - how pages lead to one another
- It avoids repeating itself:
  - The same screen reached by different routes is explored once.
  - When a page repeats the same action many times (for example an "Edit" button on every row of a table), it tries one representative instead of every copy. Every distinct action on the page is still tried; there is no per-page cap. Actions in the page's main content are tried before shared header, footer and menu items.
  - An identical form that appears on many pages is captured once.
- Pages that can only be reached by clicking a button (not a plain link) are still followed and explored.
- Pages that fail to load or return an error page are skipped and not recorded as business pages.
- Screenshots are kept in cloud file storage (Story 2.8), not in the database.
- The user doesn't see a raw activity feed; they see a plain-language progress panel instead (Story 2.7).
- Stories 2.9 to 2.21 cover how Vantage decides what to try next, what is safe to click and what to type into fields.

## Acceptance criteria

1. **Given** a running Discovery run, **when** Vantage visits pages, uses actions and fills forms, **then** each page, form, field, action, data call and page-to-page link is recorded against the application and that run as it happens.
2. **Given** the same screen is reachable by several routes, **then** it is explored and recorded once.
3. **Given** a page repeats the same action many times, **then** one representative is tried (every distinct action is still tried), with main-content actions before shared menu items.
4. **Given** a button click leads to a new page in the same application, **then** that page is explored like any linked page.
5. **Given** an identical form appears on several pages, **then** it is captured once; any visible or hidden difference means both versions are captured.
6. **Given** a page fails to load or returns an error, **then** it is skipped and never treated as a business page.
7. **Given** a screenshot is taken, **then** it is stored as a file in cloud storage and linked to its page.
