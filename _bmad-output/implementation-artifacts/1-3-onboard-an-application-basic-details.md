---
last_updated: 2026-10-27
---

# Story 1.3: Add an application — basic details & connection test

Status: done

## Story

As a QA engineer or lead,
I want to add the web application I want to test by giving its name, environment and address, and confirm Vantage can reach it,
so that Vantage can explore it and build tests for it.

## What it does today

Anyone except a viewer can open **Add application** from the sidebar or the top bar.

**The form asks for:**
- **Application name** ("Enter the application name").
- **Environment**: Staging, Production, QA, or Other — Other asks for a custom environment name.
- **URL**, with a **Test connection** button that reports "URL is reachable." or "URL is not reachable."
- The **sign-in** toggle and credentials (Story 1.4).
- **Autonomous discovery** checkbox, on by default (Story 2.24). The intro line and submit button follow it: "Start discovery" when on, "Add application" when off.

**Rules:**
- The URL must pass **Test connection** before the form can be submitted; trying to submit without it shows a reminder. The platform checks reachability again on submit and refuses an unreachable address.
- If discovery is on and the application needs sign-in, Vantage first proves the login works in a real browser before anything starts (Story 2.23).
- With discovery on, the new application is discovered by **Explorer** (Epic 8), unless operations have switched new applications back to the classic discovery engine.
- The new application belongs to the user's organization and is visible to everyone in it.
- Every new application automatically gets three schedules — Nightly, Weekly and Monthly Regression — all switched off (Story 6.8).
- After submitting, the form becomes a read-only "Connected application" record of what was submitted. The stored username and password are never shown there again.
- With discovery on, the user goes to the application's **Explorer** tab and Explorer starts straight away (the Journeys tab instead, when the classic engine is in use); with discovery off, they go to the Test cases tab. If Explorer's background service isn't running, the application is still created but its discovery is marked failed; the user can start Explorer later from the Explorer tab.

**Managing applications afterwards** (Applications list ⋮ menu, admins only): **Rename** inline, or **Delete** after confirmation. Delete is blocked while discovery, generation or a test run is still going, and the menu says why. A deleted application disappears at once, its schedules stop, and all its data is purged automatically after the retention period chosen in Settings (Story 7.2).

## Acceptance criteria

1. Given a member or admin, when they open Add application, then they see name, environment, URL with Test connection, the sign-in toggle and the Autonomous discovery checkbox; a viewer does not see Add application at all.
2. Given an address, when the user clicks Test connection, then they see whether it is reachable.
3. Given the URL has not passed Test connection, when the user tries to submit, then submission is blocked with a reminder.
4. Given an address that is unreachable at submit time, when the form is submitted, then the platform refuses it and no application is created.
5. Given a valid form, when it is submitted, then the application is created in the user's organization with three disabled default schedules, and the form becomes a read-only record that never shows the stored password.
6. Given discovery was on, when the application is created, then the user lands on Explorer with Explorer running (on Journeys with discovery running, when the classic engine is in use); given it was off, then they land on Test cases.
7. Given an admin, when they delete an application with nothing running, then it disappears immediately and is purged after the retention period; given something is still running, then delete is blocked with the reason.

## Gaps / not built

- The username, password and URL placeholders ("Service account email", "Password or token", "https://") don't yet follow the instructional placeholder style.
