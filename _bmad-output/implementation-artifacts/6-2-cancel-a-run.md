---
last updated: 2026-10-27
---

# Story 6.2: Cancel a run

Status: done

## Story

As a member or admin,
I want to cancel a test run that is still going,
so that I can stop a run I started by mistake or no longer need, without losing the results that already finished.

## What it does today

- **Where.** Run detail has a **Cancel run** button while the run is in progress.
- **Confirmation.** A dialog asks "Cancel run #N?" and explains: "Tests still running are stopped and every test that hasn't finished is marked cancelled. Finished tests keep their results. No report or email is sent." The choices are **Keep running** and **Cancel run**. While cancelling, the button shows "Cancelling" with bouncing dots.
- **On confirm:**
  - running tests are stopped straight away;
  - tests that haven't finished are marked cancelled;
  - finished results are kept;
  - the run is marked cancelled;
  - no HTML report is produced and no run-completed email is sent;
  - any self-heal that was under way is abandoned and does not change the test's code.
- **Edge cases:**
  - If the run is still starting, the user sees "The run is still starting — try again in a moment."
  - On failure: "Could not cancel the run. Try again."
- **Flaky flags.** Cancelled runs are ignored when deciding whether a test is flaky.
- **Viewers** cannot cancel runs.

## Acceptance criteria

1. **Given** a run in progress, **when** a member or admin clicks **Cancel run**, **then** a confirmation explains what will happen and offers Keep running / Cancel run.
2. **Given** the user confirms, **when** the cancel completes, **then** running tests are stopped, unfinished tests are marked cancelled, finished results are kept, and the run shows as cancelled.
3. **Given** a cancelled run, **when** it ends, **then** no report is generated and no email is sent.
4. **Given** a self-heal is in progress when the run is cancelled, **when** the cancel completes, **then** the test's code is left unchanged.
5. **Given** the run is still starting, **when** the user tries to cancel, **then** they are asked to try again in a moment.
6. **Given** a viewer, **when** they open a running run, **then** no Cancel run control is available.

## Gaps / not built

- The run does not record who cancelled it, and the cancel time is shown as the run's completion time.
