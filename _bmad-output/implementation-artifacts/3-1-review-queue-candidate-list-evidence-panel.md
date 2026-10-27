---
last_updated: 2026-10-27
---

# Story 3.1: Discover Journeys — candidate list & detail panel

Status: done

## Story

As a QA engineer,
I want to see every journey Vantage discovered in my application, with what each one looks like and the steps it takes,
so that I can judge whether discovery understood the application before scenarios are drafted.

## What it does today

The **Journeys** tab (only for applications added with discovery on, and only for applications discovered by the classic engine).

For an application **discovered by Explorer** (Epic 8) this tab is hidden from the sidebar, and links to it open Explorer instead. Its journeys still exist behind the scenes, because test generation reads them: Explorer creates one journey per screen it tested (with that screen's screenshot as the step) and one per whole-journey scenario, from proven scenarios only. If the page is reached anyway, it shows "Explorer is finding this app's journeys. They appear here when it has finished." with an **Open Explorer** button and no Pause/Resume.

The rest of this story describes the tab for classic-engine applications.

**While discovery runs:**
- A "Mapping journeys…" progress panel lists Exploring pages, Grouping flows and Capturing screenshots, with the note "Discovery runs in the background — this list updates automatically". The journeys appear, without a reload, once grouping has finished.
- **Pause Discovery** and **Resume Discovery** buttons for members and admins. Resume continues from where it stopped.
- Banners cover: session expired mid-discovery, discovery failed, discovery paused, and "Recovered from a worker restart — resuming from where it left off."

**Journey cards.** Each journey is one numbered card, 5 cards per page. There is no separate side panel: each card holds the detail itself.
- The journey's name and, when available, a one-line description.
- A screenshot of the journey's final page; clicking it opens it enlarged (Escape closes it). A placeholder shows while it loads.
- The journey's flow as a sequence of business steps (for example Login → Cart → Checkout); consecutive steps on the same page or stage are collapsed into one.
- A ⋮ menu with Rename and Delete for members and admins (Story 3.4).
- No confidence, risk or importance score appears anywhere.

**Search** filters journeys by name, showing "No journeys found — No journeys match your search." when nothing matches.

**Review scenarios** starts scenario drafting for all journeys and moves to the Scenarios tab. It is available once at least one journey exists; if the drafting service is unavailable, a message says so.

## Acceptance criteria

1. Given discovery is running, when the user opens Journeys, then they see the progress stages and journeys appear without reloading.
2. Given a member or admin, when they pause discovery, then it stops and a paused banner appears; when they resume, then it continues from where it stopped. Viewers do not get these controls.
3. Given discovered journeys, when the tab is shown, then each journey appears as a card with its name, description (if any), final-page screenshot and collapsed business-step flow, 5 cards per page.
4. Given a screenshot, when the user clicks it, then it opens enlarged and closes with Escape.
5. Given a search term, when the user types it, then only journeys whose names match are shown.
6. Given at least one journey, when the user clicks Review scenarios, then scenario drafting starts and the Scenarios tab opens.
7. Given any journey, when it is shown, then no confidence, risk or importance score is displayed.

## Gaps / not built

- A discovery coverage report (what was reached, blocked or skipped) exists on the platform but has no screen.
- When discovery needs data it doesn't have (a "blocked" step), there is no screen to supply it. (Explorer asks for missing data as a question instead, Story 8.3.)
- Starting Explorer on a classic-engine application hides this tab for good, even though Explorer's start card says "Your current Journeys are not affected".
