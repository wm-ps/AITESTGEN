---
last_updated: 2026-10-27
---

# Story 8.4: Missions, screens and findings

Status: in-progress

## Story

As a member or admin,
I want Explorer to work through the real goals of my application, show me every screen it found and flag anything that looks wrong,
so that I can see how much of the application was covered and spot problems before any test is written.

## What it does today

- **Missions.** After the summary is confirmed, Explorer plans up to 15 **missions**: goals such as "file a claim" or "try the 'someone hurt' branch". It works through them up to 3 at a time. The Live tab's Progress panel lists them (first 3, then "show all"); each has a **Skip** button, and skipping the running one stops it and moves on.
- **Hidden screens.** Explorer hunts for screens that only appear sometimes: it tries each option in dropdowns and radio groups, tries small and large amounts, and fakes "the server returned nothing / an error" inside its own browser. It also looks for unlinked pages, checks which screens each extra user type (added on the start card) can reach, and measures how much of the application's code it exercised.
- **Screens sub-tab.** A searchable, paged grid of screenshots, one per screen. Clicking a screen shows its actions and where each one leads. There is no map or graph view.
- **Findings ("Things that look wrong").** While it works, Explorer notes health problems: broken screens, server errors, broken links, slow pages, wording mistakes and things that look wrong. They sit, folded, at the end of the **What it learned** sub-tab. Each shows a thumbnail; the user can mark it a false alarm or answer its "is this a bug?" question. **Download CSV** exports the list.

## Acceptance criteria

1. **Given** the summary is confirmed, **when** Explorer plans, **then** it creates up to 15 missions and runs at most 3 at once.
2. **Given** a mission, **when** the user presses Skip, **then** it is skipped (stopped if running) and Explorer moves on.
3. **Given** screens with options, amounts or server responses that change what appears, **when** Explorer hunts, **then** screens that only appear under those conditions are recorded.
4. **Given** the Screens sub-tab, **when** the user searches or pages, **then** the grid narrows or moves accordingly, and clicking a screen shows its actions and their destinations.
5. **Given** a finding, **when** the user marks it a false alarm, **then** it is no longer treated as a problem.
6. **Given** the findings list, **when** the user presses Download CSV, **then** they get the list as a file.

## Gaps / not built

- These are worked out and stored but have no screen: adding your own mission, per-mission screen recordings, which screens each extra user type can reach, unlinked pages, code-coverage results and the application health score.
- Viewers see the skip and judge buttons, but the platform refuses them. Viewers can download mission recordings (no screen offers this yet).
- Explorer's screenshots and recordings are kept in the database rather than file storage, which will grow large over time.
