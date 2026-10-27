---
last updated: 2026-10-27
---

# Story 5.2: Save, cancel and replay recorded tests

Status: done

## Story

As a member or admin,
I want to save my recording as a test or throw it away, and then run it like any other test,
so that recorded flows become a real, maintained part of my test suite.

## What it does today

- **Stop and Save** (from the recording window or the original tab):
  - Vantage stops the browser, tidies the recording into a Playwright test (TypeScript), checks that it is valid code, and saves it.
  - The saved test gets the flow's name and a test case number, and goes under the journey "Recorded tests".
  - The recording window shows "Recording saved — This tab will close automatically."
  - The original tab jumps to Test cases and highlights the new row.
- **Discard** (in the recording window):
  - Throws the recording away.
  - The window shows "Recording cancelled — Nothing was saved to your test cases".
  - The original tab confirms "Recording cancelled successfully."
  - If the service doesn't answer: "The recording service didn't respond. Try again."
- **Save failure.** If the recording can't be saved (for example nothing was recorded, or the result isn't valid code), both tabs show "The recording could not be saved", and the user can **Try again** from Vantage. Nothing half-saved is left in the test list.
- **Replay = run like any other test.** Recorded tests:
  - carry the **Recorded** source badge,
  - appear under the "Record-and-play test cases" filter,
  - run in full or selective runs and on schedules,
  - are self-healed when they fail,
  - are included in the project download.
  - There is no separate "play" button; replay happens through Test runs.
- **Viewers** can see recorded tests and their run results but cannot record, save or discard.

## Acceptance criteria

1. **Given** an active recording with at least one action, **when** the user clicks **Stop and Save**, **then** a valid Playwright test is saved under "Recorded tests" with the flow's name and a test case number.
2. **Given** the save succeeds, **when** the original tab updates, **then** it moves to Test cases with the new test highlighted, and the recording tab closes itself.
3. **Given** an active recording, **when** the user clicks **Discard**, **then** nothing is saved and both tabs confirm the cancellation.
4. **Given** nothing was recorded, or the recording can't be made into valid code, **when** the user saves, **then** "The recording could not be saved" is shown and no test is added.
5. **Given** a saved recorded test, **when** the user runs tests (all, selective or scheduled), **then** it runs like any other test, including self-healing on failure.
6. **Given** a saved recorded test, **when** the user downloads the project, **then** it is included.
7. **Given** the Test cases list, **when** the user picks the "Record-and-play test cases" filter, **then** only recorded tests are shown.

## Gaps / not built

- Recorded tests can't be renamed or deleted after saving.
- A recording can't be resumed or edited; the flow has to be recorded again.
