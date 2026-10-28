---
last_updated: 2026-10-27
---

# Story 7.2: Settings

Status: done

## Story

As an organization admin,
I want to set limits for discovery, generation and self-healing, choose what evidence is kept, and manage saved application credentials,
so that Vantage's work stays within the time, size and storage we're comfortable with.

## What it does today

The **Settings** page is for admins. Members see the link but get "Access denied"; viewers don't see it. Changes are saved with **Save settings** (or abandoned with Cancel), and each change is recorded in Activity with its before and after values. One set of settings applies to the whole Vantage installation.

**Discovery limits:**

| Setting | Choices | Default |
|---|---|---|
| Maximum discovery time | 2, 5, 10, 15, 30 or 60 minutes, or Unlimited | 30 minutes |
| Maximum pages | 5 to 1,000 | 500 |
| Maximum journeys | any number, or blank for unlimited | Unlimited |
| Navigation timeout | 10 seconds to 5 minutes | 15 seconds |
| Interaction level | Passive, Normal, Aggressive | Normal |
| Maximum scenarios per journey | any number, or blank for unlimited | Unlimited |
| Maximum test cases per application | any number, or blank for unlimited | Unlimited |
| Maximum self-heal attempts (for a manual Retry) | 0, 1, 2, 3, 5 or 10 | 3 |
| Screenshot capture | Failed test cases, Passed test cases, All | Failed test cases |

**Auto-clean up removed projects** is always on. The admin chooses when a deleted application's data (discovery data, test cases, screenshots and run history) is purged: after 1 day, 1 week or 1 month (default 1 month).

**Saved credentials** lists username-and-password applications and applications with no login (application, environment, username or "No login", hidden password).
- **Reveal** shows a password; every reveal is recorded in Activity.
- **Add credentials** sets or replaces the username and password for an application. They are not re-checked against the live application. Saving them for a no-login application turns its sign-in on.
- A **Sign-in** on/off switch per application. Turning it off makes the application a no-login application (its saved login is replaced with an empty session; discovery, Explorer and test runs open it directly). It can only be turned back on by saving a username and password (Story 1.4).

## Acceptance criteria

1. Given an admin, when they open Settings, then they see the current limits, screenshot capture, clean-up period and saved credentials; a member sees "Access denied" and a viewer has no link.
2. Given an admin changes a limit and saves, when the next discovery, generation or retry starts, then it uses the new value, and Activity shows the change with before and after values.
3. Given a discovery-time or page limit, when discovery reaches it, then discovery stops.
4. Given a screenshot capture choice, when tests run, then final-screen screenshots are kept only for the chosen results; traces are always kept for non-passing results only.
5. Given a clean-up period, when an application has been deleted for that long, then its data is purged automatically.
6. Given an admin reveals a saved password, when it is shown, then the reveal is recorded in Activity; credential values are never shown in Activity.
7. Given an admin saves new credentials for an application, when later work signs in to it, then it uses them.
8. Given an admin turns an application's Sign-in switch off, when discovery, Explorer or a test run opens it, then it opens directly without logging in.

## Gaps / not built

- Settings can't be set per application or per run, even though the section note says "unless overridden per run".
- The page subtitle mentions schedules, but schedules are managed in each application's Schedules tab, not here.
- The credential save button still shows a static "Saving…" label instead of the standard busy indicator.
- The discovery limits (time, pages, journeys, navigation timeout, interaction level) apply only to the classic discovery engine. Explorer (Epic 8) uses its own fixed limits and ignores them.
- Changes to the Sign-in switch are not recorded in Activity.
