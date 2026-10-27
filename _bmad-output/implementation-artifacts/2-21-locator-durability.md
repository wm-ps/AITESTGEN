---
last_updated: 2026-10-27
---

# Story 2.21: Durable Element Finding — Ranked Locators & Fragility Detection

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to record the most durable way to find each element, and to tell me when it couldn't find a durable one,
so that generated tests keep passing after my application's next release, and I know in advance where they might not.

## What it does today

- For every interactive element it captures, Vantage keeps a ranked list of ways to find it again, most durable first:
  1. A dedicated test ID that developers put on the element.
  2. Its accessibility role and name (for example, the "Submit" button).
  3. Its visible text.
  4. The label attached to a form field.
  5. A short, scoped path through the page structure.
  6. A full path through the page structure (last resort).
- Names that were clearly machine-generated are pushed below every human-readable option. This covers auto-generated style class names, framework-generated IDs, long random hex or ID fragments, and "the 3rd div inside the 7th div" style paths. Placeholder-text-based ways of finding a field are also treated as fragile.
- Elements inside frames or embedded components (Story 2.14) remember the containers they sit in, so they can still be found from the top-level page.
- Each saved way of finding an element gets a durability score, and machine-generated ones are flagged as fragile. The coverage report (Story 2.22) then gives the share of the application's saved locators that are fragile.
- Generated tests (Epic 4) use these ranked options, with backups, rather than a single guess. Self-healing (Epic 6) repairs tests whose elements later move.

## Acceptance criteria

1. **Given** an interactive element is captured, **then** a ranked list of ways to find it is saved, in the order above.
2. **Given** an option contains a machine-generated name or a position-only path, **then** it is ranked below every human-readable option.
3. **Given** an element inside a frame or embedded component, **then** its saved locator includes the containers needed to reach it from the page.
4. **Given** locators are captured, **then** a durability score and a fragile flag are saved per locator, and the share of fragile locators can be reported.
5. **Given** the application model is built (Story 2.5), **then** each component uses the ranked list as its preferred and backup locators.
