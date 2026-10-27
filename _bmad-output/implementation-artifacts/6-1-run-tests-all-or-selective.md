---
last updated: 2026-10-27
---

# Story 6.1: Run tests — run all or a named selective run

Status: done

## Story

As a member or admin,
I want to run all of an application's tests, or a named subset of them, from inside Vantage,
so that I can check the application's health whenever I need to, without setting anything up.

## What it does today

- **Run tests button** (Test runs tab, and **Run Test Cases** after generation). It offers two choices:
  - **All test cases:** "Run every test case in this application." The run is labelled as a full suite run.
  - **Selective run:** "Choose specific journeys or test cases to run." This opens a dialog with:
    - a required **Run Name** ("Enter a name for this run");
    - a searchable list of journeys that have test cases, with **Select all / Clear**;
    - each journey can be expanded to tick individual test cases. If no journey has tests yet: "No journeys with test cases yet."
- **Every run is new.** Each run gets its own **Run #** within the application.
  - Manual runs are not blocked from overlapping each other. Scheduled runs are different: they are skipped if one is already going (Story 6.8).
  - No setup is needed: there is no allow-list or "safe actions" policy to configure before running.
- **How tests run.** Tests run in a real browser, 5 at a time within a run. The exception is an application that keeps progress per login (saved drafts, a cart, "resume where you left off"): Explorer guesses this from screen names and marks the scenarios it hands over, and a run containing any such test runs **all** its tests one at a time. The application's saved login is used for tests that need sign-in and is never exposed in results. Results stream into the run as each test finishes.
- **Runs list:**
  - Summary tiles: latest pass rate, average pass rate, median duration and open failures (failures in the latest run).
  - Each row shows Run #, triggered by ("Manual run by X" or "Scheduled run — X"), date, duration, results and pass rate.
  - The list pages with plain Prev/Next.
  - When empty: "No test runs yet".
- **Run detail:**
  - a status pill (pulsing with trailing dots while running);
  - a "Results by journey" chart;
  - results grouped as **Passed / Self-healed / Flaky / Failed**;
  - one row per test case with its status. A test deliberately skipped in its code (for example one recording a known bug) shows as **Skipped** (amber), with its reason (for example "Known bug — should: … The app currently: …"), not as an error.
  - Failure details, healing, flaky flags and the report are covered in Stories 6.3–6.6.
- **Stuck runs.** A run that stops reporting progress is closed out automatically by a background sweep every 15 minutes.
- **Viewers** can see runs and results but cannot start a run.

## Acceptance criteria

1. **Given** an application with test cases, **when** a member or admin picks **All test cases**, **then** a new run with the next Run # starts, covering every test case.
2. **Given** **Selective run**, **when** the dialog opens, **then** the user must enter a Run Name and can select journeys (search, Select all, Clear) or individual test cases within a journey.
3. **Given** no test case is selected, **when** the user looks at the start button, **then** it is disabled. **Given** the Run Name is empty, **when** the user tries to start, **then** "Enter a run name to continue" is shown and the run doesn't start.
4. **Given** a run is already in progress, **when** a member starts another manual run, **then** it starts as a separate run with its own Run #.
5. **Given** a run is in progress, **when** the user watches the run detail, **then** results appear as each test finishes, and the status pill pulses until the run ends.
6. **Given** finished runs, **when** the user opens Test runs, **then** the summary tiles and run list (Run #, triggered by, date, duration, results, pass rate) are shown, paged with Prev/Next.
7. **Given** a run stops reporting progress, **when** the background sweep runs, **then** the run is closed out instead of staying "running" forever.
8. **Given** a viewer, **when** they open Test runs, **then** they can view runs but have no Run tests control.

## Gaps / not built

- The summary tiles are calculated from the page of runs currently loaded, not from the full history.
- Blocking destructive actions during runs (an execution safety policy) was deliberately removed; tests run whatever they contain.
- No hand-off to an external CI/CD system to trigger runs.
- "Keeps progress per login" is a keyword guess. A wrong guess either slows a run (everything runs one at a time) or lets tests that share saved progress run together.
- Skipped tests are not counted in any of the Passed / Self-healed / Flaky / Failed groups.
