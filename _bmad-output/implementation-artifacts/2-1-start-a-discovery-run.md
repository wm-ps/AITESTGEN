---
last_updated: 2026-10-27
---

# Story 2.1: Start a Discovery Run

Status: done

## Story

As a member or admin,
I want Discovery to start automatically as soon as I add an application with autonomous discovery turned on,
so that Vantage begins mapping the application's business journeys without an extra step.

## What it does today

- Submitting the Add application form with "Autonomous discovery" checked (button label "Start discovery") creates the application and starts its first Discovery run in the same step. That run is an **Explorer** run (Epic 8). Only if operations have switched new applications back to the classic engine is it a classic Discovery run, as described in the rest of this story.
- A classic Discovery run can't be started anywhere else. Explorer can also be started by hand from the Explorer tab ("Start exploring"), and started again at any time with "New run" (Story 8.1).
- If the application needs sign-in, Vantage first proves the credentials work in a real browser (Story 2.23). Discovery never starts on an unproven login.
- Discovery runs in the background. The user lands on the application's Explorer tab (Story 8.1), or on the Journeys tab with its progress panel for a classic run (Story 2.7). On the Applications list the application shows a "Discovery in Progress" status with trailing bouncing dots.
- Behind the scenes each classic run moves through stages: getting ready, signing in, exploring, then analysing (grouping pages into journeys). The Journeys screen uses these stages to decide what to show.
- If Explorer's background service is unavailable when the user submits, the application is still created but its discovery is marked failed; the user can start Explorer later from the Explorer tab. For a classic run, the user instead gets a plain "service unavailable" message rather than a run that never moves.
- A classic Discovery run happens once per application, when it is created. It can be paused and resumed (Story 2.17), but there is no "run discovery again" action for it.
- Viewers can't add applications, so they can never start Discovery that way. Explorer's Start button is shown to them, but the platform refuses it.
- If "Autonomous discovery" is unchecked when the application is added, no run is ever started for it (Story 2.24).

## Acceptance criteria

1. **Given** a member or admin submits Add application with autonomous discovery on (and, if sign-in is required, the credentials have been validated), **when** the application is created, **then** an Explorer run (or, if operations have switched back, a classic Discovery run) is created and starts straight away in the background.
2. **Given** a run has just been created, **then** it is shown as running (on the Applications list, a pulsing status with trailing bouncing dots) even before any exploring has begun.
3. **Given** the discovery service is down, **when** the user submits, **then** nothing is left looking stuck in a running state: with Explorer the application is created with its discovery marked failed; with the classic engine a plain "service unavailable" message is shown.
4. **Given** a viewer, **then** the Add application entry points are hidden and the server refuses the request.

## Gaps / not built

- There is no way to start a fresh classic Discovery run for an application that has already been discovered. (Explorer's "New run" covers this for Explorer.)
- The schedule dialog's wording suggests Discovery can be scheduled, but only test runs can be.
