---
last_updated: 2026-10-27
---

# Story 2.17: Pause and Resume Discovery

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a member or admin,
I want to pause a running Discovery and resume it later without losing progress or re-exploring what's already confirmed,
so that I don't have to let Discovery run to the end in one go.

## What it does today

- While Discovery is running, the Journeys tab shows a **Pause Discovery** button. While it is paused, it shows **Resume Discovery** instead. The button shows trailing bouncing dots while it works. Viewers don't see either button.
- Pausing stops the run and marks it paused. Everything already found stays saved: the pages, the application model and any blocked items. The tab shows "Discovery paused. Resume to continue exploring from where it left off."
- Resuming, from the same or a later session, starts a new pass that:
  - signs in fresh
  - picks up from where exploring stopped
  - skips pages that were already confirmed rather than exploring them again
- Everything is tied to the application, so resuming works from any session.
- Pause only works on a running Discovery and resume only on a paused one. Otherwise the user gets "Could not pause discovery. Try again." or "Could not resume discovery. Try again."
- Pause and resume are refused for applications added without Discovery (Story 2.24).
- They are also refused for any application that has ever had an Explorer run: "Explorer discovers this application: pause or resume it from the Explorer tab." Explorer has its own Pause, Stop and Resume on the Explorer tab (Story 8.1).

## Acceptance criteria

1. **Given** a running Discovery, **when** a member or admin clicks Pause Discovery, **then** the run is marked paused and everything found so far is kept.
2. **Given** a paused Discovery, **when** they click Resume Discovery, **then** Vantage signs in fresh, continues from where it stopped and doesn't re-explore pages already confirmed.
3. **Given** the run isn't in the right state, or the request fails, **then** a plain "Could not pause/resume discovery. Try again." message is shown.
4. **Given** a viewer, **then** neither button is shown and the server refuses the request.
5. **Given** an application that has had an Explorer run, **when** anyone tries to pause or resume classic Discovery, **then** the server refuses and points them to the Explorer tab.

## Gaps / not built

- There is no summary screen showing confirmed / blocked / remaining counts for a paused Discovery.
- A failed run can't be resumed; only a paused one can (see Story 2.4).
