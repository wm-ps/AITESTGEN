---
last updated: 2026-10-27
---

# Story 6.8: Scheduled test runs

Status: done

## Story

As a member or admin,
I want my tests to run automatically on a regular schedule,
so that regressions are caught overnight or weekly without anyone having to remember to start a run.

## What it does today

- **Schedules tab.** A table with Schedule, Cadence, Next run and an **Enabled** toggle. Each row has a ⋮ menu with **Run now**, **Edit** and **Delete**.
- **Ready-made schedules.** Every new application gets three schedules, all turned off:
  - Nightly Regression: daily at 02:00;
  - Weekly Regression: Mondays at 02:00;
  - Monthly Regression: the 1st of the month at 02:00.
  A team can switch one on without configuring anything.
- **New / Edit schedule dialog:**
  - **Name** ("Enter a name for this schedule").
  - **Cadence:**
    - **Daily**;
    - **Weekly**, choosing days of the week;
    - **Monthly**, day 1–28 only, so every month has that day;
    - **Custom**, a 5-field cron expression (example placeholder `0 2 * * 1-5`).
  - Daily, weekly and monthly use hour and minute pickers in 15-minute steps.
  - All times use the server's configured time zone.
- **What a scheduled run does:**
  - It runs **all** test cases of the application.
  - It appears in Test runs as "Scheduled run — <schedule name>".
  - It gets the same self-healing, report and email as a manual run. The email goes to the schedule's creator.
- **Never piles up.** If a run is already in progress for the application when a schedule fires, that scheduled run is skipped, not queued. **Run now** in the same situation says "A test run for this application is already in progress — try again once it finishes."
- **Delete** removes the schedule immediately. Deleting the application stops its schedules.
- **Viewers** can see schedules but cannot create, edit, enable, disable, delete or run them.

## Acceptance criteria

1. **Given** a new application is added, **when** its Schedules tab is opened, **then** Nightly, Weekly and Monthly Regression schedules exist, all disabled.
2. **Given** a member or admin, **when** they create or edit a schedule with a name and a daily, weekly, monthly or custom cron cadence, **then** it is saved and its next run time is shown.
3. **Given** a monthly cadence, **when** choosing the day, **then** only days 1–28 are offered.
4. **Given** an enabled schedule, **when** its time arrives and no run is in progress, **then** a run of all test cases starts, labelled "Scheduled run — <name>".
5. **Given** a run is already in progress, **when** a schedule fires, **then** that scheduled run is skipped. **When** the user clicks **Run now**, **then** they are told a run is already in progress.
6. **Given** a schedule, **when** the user toggles Enabled off, **then** it stops firing until switched back on.
7. **Given** a scheduled run finishes normally, **when** it completes, **then** the schedule's creator receives the run-completed email.
8. **Given** the application is deleted, **when** its schedules would next fire, **then** they don't run.
9. **Given** a viewer, **when** they open Schedules, **then** they have no controls to change or run schedules.

## Gaps / not built

- Only test runs can be scheduled. The dialog's description ("Run discovery or test cases automatically on a cadence") overstates this; Discovery can't be scheduled.
- A schedule always runs every test case. It can't be limited to selected journeys or test cases.
- The time zone can't be chosen per schedule. The dialog never names the time zone; only the custom cron field mentions that times use the server's time zone.
- Delete has no confirmation step.
- Schedules may be lost if the scheduling service restarts, and may need to be recreated.
