---
last_updated: 2026-10-27
---

# Story 2.7: Business-Oriented Discovery Progress Display

Status: done

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user who has just started Discovery,
I want plain-language progress that updates by itself,
so that I understand what's happening without needing to know how Discovery works inside.

## What it does today

- While Discovery is running and no journeys exist yet, the Journeys tab shows:
  - a progress panel titled "Mapping journeys…", with the line "Vantage is exploring the deployed URL and grouping discovered pages into journeys in <application name>."
  - an animated checklist: Exploring pages, Grouping flows, Capturing screenshots
  - the note "Discovery runs in the background — this list updates automatically."
- There is no percentage bar. The backend has no reliable per-stage percentage, so a number would suggest more precision than really exists.
- The screen checks for updates on its own; no reload is needed. It keeps showing progress until journey grouping has actually finished, not just until exploring stops.
- No technical words ("crawl", "queue", raw page addresses) appear.
- Members and admins see **Pause Discovery** / **Resume Discovery** buttons (Story 2.17). Viewers don't.
- Status messages replace or sit beside the panel:
  - Paused: "Discovery paused. Resume to continue exploring from where it left off."
  - Recovered after a worker restart: "Recovered from a worker restart — resuming from where it left off."
  - Session expired: the re-authentication message (Story 2.4).
  - Discovery service down: a service-unavailable note.
  - Any other failure: "Discovery Run failed."
- When journeys are ready, the progress panel is replaced by the journey cards.
- For an application discovered by Explorer, the Journeys tab (hidden from its sidebar anyway) shows none of this. It says "Explorer is finding this app's journeys. They appear here when it has finished." with an **Open Explorer** button, and has no Pause/Resume. Explorer shows its own live progress on the Explorer tab (Story 8.1).

## Acceptance criteria

1. **Given** a running Discovery run with no journeys yet, **when** the Journeys tab is open, **then** the business-language progress panel is shown and updates without a reload.
2. **Given** any progress view, **then** no technical terms or raw page addresses are shown.
3. **Given** exploring has finished but journey grouping is still running, **then** progress keeps showing until the journeys appear.
4. **Given** the run is paused, recovered after a restart, failed because of an expired session, failed for another reason, or the service is down, **then** the matching plain-language message is shown.
5. **Given** a viewer, **then** the Pause and Resume buttons are hidden.
