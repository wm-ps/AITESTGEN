---
last_updated: 2026-10-27
---

# Story 2.4: Session Expiry Handling

Status: in-progress

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Discovery to sign back in by itself if the application logs it out, and to tell me plainly if it can't,
so that a short-lived login doesn't quietly cut my discovery short.

## What it does today

- If the application logs Vantage out partway through Discovery, Vantage notices (it lands back on a sign-in page), signs in again with the saved credentials and carries on.
- It tries up to three times in a row. If signing in keeps failing, the run stops and is marked failed with the reason "session expired". It is never shown as a normal, complete run.
- Each lost session is also logged as a coded discovery error (Story 2.18).
- On the Journeys tab, a session-expired run gets its own red message: "Session expired mid-discovery. Re-authenticate to continue discovery." Other failures show either a generic "Discovery Run failed." or, if the discovery service is down, a service-unavailable note.
- An admin can update the application's saved username and password on the Settings page.

## Acceptance criteria

1. **Given** a running Discovery run is logged out by the application, **when** Vantage detects it, **then** it signs in again with the saved credentials and keeps exploring.
2. **Given** signing in again fails three times in a row, **then** the run is marked failed with the reason "session expired", never complete.
3. **Given** a run failed for this reason, **then** the Journeys tab shows the session-expired message, which looks different from any other failure.

## Gaps / not built

- The message tells the user to re-authenticate "to continue discovery", but there is no way to continue. Even after the user updates the credentials in Settings, a failed run can't be restarted or resumed; resume only works for a paused run.
