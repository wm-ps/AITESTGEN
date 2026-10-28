---
last_updated: 2026-10-27
---

# Story 2.11: Exploration Planner, Action Priorities & Getting Back to a Page

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to finish exploring a page's own actions before moving on, and to be honest about any it couldn't get back to,
so that no page is left half-understood and the cost of thorough exploring stays limited and reportable.

## What it does today

- **Two kinds of action.** Vantage sorts each action on a page into one of two kinds:
  - **In-page actions:** buttons, form submits, expand/collapse, filters, tabs, "Load more".
  - **Navigation:** main menu, sidebar, breadcrumbs, links that go to a different kind of page.
  It decides this by fixed rules: tabs always count as in-page; anything inside a menu or navigation area counts as navigation; a link to a different kind of page counts as navigation; everything else is in-page.
- **Order.** It tries every in-page action on a screen, including finishing list sampling (Story 2.9), before following that screen's navigation.
- **Three checks before every action.** Vantage asks three questions in a fixed order:
  1. Have I done this already, would it send me in circles, or is it over budget? (Story 2.19)
  2. Is it safe? (Story 2.12)
  3. Do I have the data it needs? (Story 2.13)
  It also checks the admin's Interaction level setting.
- **Three possible outcomes:**
  - **Do it:** perform the action and look at the result.
  - **Put it aside:** record it as blocked (Story 2.15) and carry on elsewhere straight away, never waiting.
  - **Skip it.**
- **Getting back to a page.** After an action takes Vantage elsewhere, it needs to return to try the next action. It tries these steps in order:
  1. Nothing to do, because it never left.
  2. Press back.
  3. Reopen the page's address.
  4. Go back to the start page and then reopen the page's address.
  5. Give up.
  After each attempt it checks that it really is on the same screen (Story 2.10).
- **Giving up is reported.** If it gives up, or uses up the return budget for that screen, the remaining actions are recorded as "unreached" with a reason. The run moves on. Unreached actions are counted in the coverage report (Story 2.22), never dropped silently.
- Every decision is traceable: which check decided it and, for returns, which step worked or why it gave up.

## Acceptance criteria

1. **Given** an action, **then** it is classed as in-page or navigation by fixed rules.
2. **Given** a screen with untried in-page actions, **then** all of them are tried before any navigation on that screen.
3. **Given** an action, **then** loop guards, then safety, then data are checked in that order, giving exactly one outcome: do it, put aside, or skip.
4. **Given** "put aside", **then** a blocked item is recorded and exploring continues elsewhere without waiting.
5. **Given** Vantage needs to return to a screen, **then** it works through no-op, back, re-open, start-page-then-re-open, give up, confirming the screen after each attempt.
6. **Given** it gives up or runs out of return budget, **then** the remaining actions are recorded as unreached with a reason and counted in the coverage report.

## Gaps / not built

- Return step 4 goes back via the start page rather than replaying the shortest known path to the screen, so some deep screens are given up on sooner than necessary.
- The Interaction level setting only has a visible effect at "Passive" (look, don't click). "Aggressive" behaves the same as "Normal": its extra kinds of interaction (dialogs, drag-and-drop, multi-step flows) aren't routed through the planner yet.
- There is no AI fallback for actions that are hard to classify; the fixed rules always decide.
