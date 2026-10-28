---
last_updated: 2026-10-27
---

# Story 8.1: Start Explorer and watch it live

Status: in-progress

## Story

As a member or admin,
I want Explorer to start learning my application as soon as I add it, and to watch what it is doing as it happens,
so that I know discovery is under way and can step in, pause or stop it when I need to.

## What it does today

- **Explorer is the default way the product learns an application.** Adding an application with **Autonomous discovery** ticked starts Explorer, not the classic discovery engine (Epic 2). That is the only place discovery starts on its own. A server setting only operations can change switches new applications back to the classic engine.
- **Starting by hand.** The **Explorer** tab (compass icon) sits after Journeys in the sidebar for every application that has discovery on. Before the first run, or after **New run**, it shows a start card that explains the six things Explorer does, plus an **"Other kinds of users"** panel where the user can add another user type with its username and password. **Start exploring** begins the run. Only one Explorer run can be active per application.
- **If Explorer's background service isn't running** when an application is added, the application's discovery is marked failed ("worker unavailable"). The user can start Explorer later from the Explorer tab.
- **Where the application opens.** Right after it is added with discovery, the application opens on Explorer. An application Explorer discovered also opens on Explorer later, unless test cases are being generated for the first time (Test cases) or a test suite already exists (Overview).
- **The header** shows the application name, a one-line status of what Explorer is doing right now ("Reading the Quotes screen") and these buttons:
  - **Questions**, with a count; it pulses when Explorer is waiting on the user (Story 8.3).
  - **Pause** and **Stop** while a run is going.
  - **Resume** for a run that was paused, stopped or failed. It carries on from the step it reached and doesn't redo finished work.
  - **New run** otherwise.
- **The Live sub-tab** (the default of four: Live, What it learned, Screens, Scenarios):
  - A pulsing **"Waiting for you"** box when Explorer needs the user: either "Check the summary" (Story 8.2) or the first open blocking question with **Answer now** (Story 8.3).
  - A **live frame** with the latest screenshot and a trail of the last 6; clicking one pins it.
  - An **Activity log** of the last 80 things Explorer did or thought.
  - A **Progress** panel with four stages: Learning the app → Your check → Trying every path → Writing scenarios, plus the missions list (Story 8.4).
- **The application's discovery status follows Explorer:** running, paused, or failed ("Explorer was stopped before it finished"). It shows complete once proven scenarios have been handed over (Story 8.5).
- **Classic Pause/Resume is refused** for any application that has ever had an Explorer run: "Explorer discovers this application: pause or resume it from the Explorer tab."
- **Existing applications discovered by the classic engine** keep their Journeys and Scenarios pages and old Pause/Resume, and also get the Explorer tab. Once someone starts Explorer on one, it counts as an Explorer application from then on: Journeys and Scenarios leave its sidebar and classic Pause/Resume is refused.
- **Safety.** Explorer never deletes data, moves money, makes a business decision or signs out on its own, in any environment; it asks first. It presses a final Save, Submit or Create by itself only when the application is marked as a test (non-production) environment, and never presses Send twice.

## Acceptance criteria

1. **Given** an application is added with Autonomous discovery ticked and Explorer is on, **when** it is created, **then** an Explorer run starts and the application opens on the Explorer tab.
2. **Given** Explorer's background service isn't running, **when** the application is added, **then** its discovery is marked failed with "worker unavailable", and Explorer can be started later from the Explorer tab.
3. **Given** no run is active, **when** the user presses Start exploring (or New run), **then** a new run starts. **Given** a run is already active, **then** a second one can't be started.
4. **Given** a running run, **when** the Live tab is open, **then** it shows the current status line, the latest screenshot with a trail of 6, the last 80 activity entries and the four-stage progress.
5. **Given** a running run, **when** the user presses Pause or Stop, **then** the run halts. **When** they later press Resume, **then** it carries on from the step it reached without redoing finished work.
6. **Given** an application that has had an Explorer run, **when** classic Pause or Resume is attempted, **then** it is refused with a message pointing to the Explorer tab.
7. **Given** operations have switched Explorer off, **when** an application is added with discovery, **then** the classic discovery engine runs instead.

## Gaps / not built

- **No deployment setup for Explorer's background service.** It runs in local development only. In a deployed environment with Explorer on (the default), adding an application with discovery marks discovery failed.
- **Role gaps.** Viewers can't change anything in Explorer: its buttons are shown to them, but the platform refuses each change. However, members (not just admins) can add or delete other user types with their passwords, and viewers can download Explorer's tests, run report, mission recordings and highlight video (no screen offers these yet).
- Explorer actions are not recorded in the Activity history.
- The start card says "Your current Journeys are not affected", which is only partly true for an application discovered by the classic engine (see above).
- The Explorer tab's first loading state uses a spinner instead of the trailing bouncing dots used everywhere else.
- Per-mission screen recordings and the shareable highlight video are made but have no screen.
