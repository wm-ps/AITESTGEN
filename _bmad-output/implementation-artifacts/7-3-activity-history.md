---
last_updated: 2026-10-27
---

# Story 7.3: Activity history

Status: done

## Story

As an organization admin,
I want one timeline of everything that happened across my organization,
so that I can see what ran, what failed and why, and who changed what.

## What it does today

The **Activity** page (admins only, in the Configuration group) shows an organization-wide timeline with the columns **Time, Event, By, Result**.

**What it records:**
- Discovery runs and test runs. Each is a single row that updates in place as it progresses (running, then done, failed or stopped). For an application discovered by Explorer, its Discovery row follows the Explorer run (running, paused, failed, then complete after the hand-off).
- Scenario drafting and test case generation.
- Changes to settings, credentials (including password reveals), the team (invites and role changes), applications and schedules.

**Finding things:**
- Filters by type (Discovery, Scenarios, Test cases, Test runs, Settings & team), application, result and time range (last 24 hours, 7, 30 or 90 days), plus a search box.
- Sort newest or oldest first.

**Detail drawer** (click a row):
- What happened, "Why it could not run" for failures, and a suggested next step.
- Before and after values for settings changes. Credentials are never shown.
- For failed tests: screenshot, trace, the exact error and the error log.
- **Open application** (or **Open run** for a test run) jumps to the related tab or run.

History is kept for **90 days** and then deleted automatically.

## Acceptance criteria

1. Given an admin, when they open Activity, then they see the organization's events newest first; members and viewers can't open it.
2. Given a discovery or test run, when it progresses, then its single Activity row updates rather than new rows being added.
3. Given a settings, credential, team, application or schedule change, when it is made, then an Activity entry records who made it and, for settings, the before and after values — never credential values.
4. Given filters, a time range or a search term, when the admin applies them, then only matching events are shown.
5. Given a failed event, when the admin opens it, then the drawer explains why and suggests a next step, with screenshot, trace and error details for failed tests.
6. Given an event linked to an application, when the admin clicks Open application, then the related tab or run opens.
7. Given an event older than 90 days, when clean-up runs, then it is removed.

## Gaps / not built

- Search is applied after a page of results is loaded, so a searched page can show fewer rows than expected.
- The counts next to filter options are approximate for very large histories.
- **Explorer's own actions are not recorded** (Epic 8): starting, pausing, stopping or resuming a run, confirming the App Summary, answering questions, judging possible bugs, adding or deleting knowledge, and adding other kinds of users with their passwords.
- Turning an application's Sign-in switch on or off in Settings is not recorded.
