---
last updated: 2026-10-27
---

# Story 5.1: Record a test in a remote browser

Status: done

## Story

As a member or admin,
I want to click through a flow once in a real browser and have Vantage turn it into a test,
so that I can capture an exact path that I know matters, without writing code or describing it.

## What it does today

- **Where.** The **Record and play** tab in the application sidebar. It is hidden for viewers.
- **Setting up a recording:**
  - The user enters a **flow name** ("Enter a name for this flow"). It is required.
  - The user picks a mode:
    - **Record a login flow:** "Start from a logged-out browser — your login steps become part of the test."
    - **Record an authenticated flow:** "Start already signed in, using this application's stored credentials."
  - The user clicks **Record a flow**.
- **The recording window.** Vantage opens a separate browser tab showing a real browser running on Vantage's servers, streamed live into the page. The user clicks and types through the flow there.
  - The window warns: "Anything you type — including passwords — is recorded into the generated test."
  - Any checks the user adds while recording are kept in the test.
- **The original tab.** It shows "Recording in progress — Perform your flow in the recording window that just opened…", with **Stop and Save** available from either tab.
- **Edge cases:**
  - **Pop-up blocked:** a link reads "Your browser blocked the pop-up — click here to open the recording window."
  - **Connection drop:** the window shows "Reconnecting" with bouncing dots. The session waits about 90 seconds for the user to come back before it is abandoned.
  - **Connection lost for good:** "The connection to the recording browser closed unexpectedly."
- **Limits:**
  - A recording link must be used within 30 minutes of being created.
  - A single recording is stopped and saved automatically after 60 minutes.
  - Only a few recordings can run at once across the whole deployment (4 by default). When all are in use, a new one can't start.
- Saving, discarding and how recorded tests run afterwards are covered in Story 5.2.

## Acceptance criteria

1. **Given** a member or admin on Record and play, **when** they enter a flow name, pick a mode and click **Record a flow**, **then** a new tab opens with a live remote browser for the application.
2. **Given** no flow name has been entered, **when** the user looks at the start button, **then** it is disabled.
3. **Given** "Record a login flow", **when** recording starts, **then** the browser is logged out, so the login steps become part of the test.
4. **Given** "Record an authenticated flow", **when** recording starts, **then** the browser is already signed in with the application's saved login.
5. **Given** the recording window is open, **when** the user views it, **then** the warning that everything typed, including passwords, is recorded is shown.
6. **Given** the browser blocks the pop-up, **when** recording starts, **then** a link to open the recording window manually is shown.
7. **Given** the connection drops briefly, **when** it comes back within the grace period, **then** recording continues where it left off.
8. **Given** a recording runs for 60 minutes, **when** the limit is reached, **then** it is stopped and saved automatically.
9. **Given** a viewer, **when** they open the application, **then** the Record and play tab is not shown.

## Gaps / not built

- When all recording slots are busy, there is no dedicated "busy, try again later" message; the recording window shows a generic connection error.
