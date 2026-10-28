---
title: "Change record — UX v3 reconciliation (2026-07-27)"
status: approved
created: 2026-07-27
last updated: 2026-10-27
---

# Change record: UX v3 reconciliation (2026-07-27)

## What was proposed and why

A third prototype ("v3") was folded into the design guidelines. Several parts of it clashed with screens that were already built, so the plan had to be adjusted.

**Adopted at the time:**
- A new look: blue accent, Inter font, soft shadows and two permitted gradient surfaces.
- Dark mode dropped. The half-built dark theme was to be removed rather than left stale.
- A Home screen that shows an empty state until an application exists, then a lasting card for that application that resumes where the user left off.
- Exactly three sign-in options for the app under test: username & password, API key, OAuth client credentials.
- A Ready / Needs Data filter on Review Scenarios, based on whether required test data is filled in.
- A "Suite generated" screen after test generation, with summary figures, the list of generated tests and a download action.

**Rejected as prototype drift:**
- Journey-level editing.
- A raw scrolling Discovery feed.
- A single-file test download.
- A "Discovery attention" approve/skip gate.
- A multi-tab "Workspace" home with live pass/fail results.

## What was decided

- Four already-built stories were reopened for behaviour changes, and seven more for a visual restyle.
- The new look was applied through the shared design tokens.

## Where it stands today (2026-10-27)

- **Visual identity: reversed.** Today's look is a teal accent with Instrument Sans for interface text and IBM Plex Mono for code. Soft-shadow cards and light mode only were kept.
- **Dark mode dropped: still true.** Vantage is light mode only.
- **Home screen with an application card: replaced.** Signing in lands on an org-wide **Overview** dashboard. There is also a paginated **Applications** list showing health status.
- **Three sign-in options: not built.** The app under test can be added with a username and password, or with no sign-in. API key and OAuth were never built. Saved-session and MFA support exist on the server only, with no screen.
- **Ready / Needs Data filter: not built.** Scenarios mark each test data field "Required" or "Optional — auto-filled if left blank" and offer Auto-generate, but there is no readiness filter.
- **Post-generation screen: shipped in a different form.** A one-time "Test Cases Generated" progress screen shows stages, counts (test cases, journeys covered, estimated runtime) and per-journey status. It has Terminate, Retry Generation, Download and Run buttons.
- **Rejected items, as they stand today:**
  - Journey editing is still rename and delete only.
  - The raw feed is still not shown.
  - The Discovery attention gate is still not built.
  - **Reversed:** a per-application workspace with tabs, including live test-run results, is now the core of the product.
  - The download is a full project, not a single file.
