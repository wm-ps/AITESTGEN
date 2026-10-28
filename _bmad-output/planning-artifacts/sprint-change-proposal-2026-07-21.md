---
title: "Change record — Import experience and progress (2026-07-21)"
status: approved
created: 2026-07-21
last updated: 2026-10-27
---

# Change record: Import experience and progress (2026-07-21)

## What was proposed and why

Three improvements to adding an application came out of stakeholder review:

1. **Browser tab branding.** The browser tab would show the application's own name and favicon (fetched from its site) while someone worked on it, instead of a generic title.
2. **Business-language progress.** Discovery progress would be shown as four plain stages with fixed percentages: Initialization 10%, Authentication 25%, Discovery 75%, Analysis 100%. A raw "live feed" of crawl activity would no longer be shown to users.
3. **Reachability check.** Before an application is created, Vantage would confirm that its URL actually responds, and fail fast with a clear message if it doesn't.

## What was decided

All three were approved as small, direct adjustments to onboarding and Discovery. The progress view would check for updates periodically rather than needing live streaming.

## Where it stands today (2026-10-27)

- **Browser tab branding: reversed.** The tab always shows the Vantage title and icon. The decision was made to keep tab branding as static platform branding, unaffected by the application.
- **Business-language progress: shipped, with changed wording.** Discovery progress uses plain business language and no technical crawl terms. The stages shown today are Exploring pages, Capturing screenshots, Grouping flows and Mapping journeys. The raw live feed was never shown to users. Pause/resume and banners for an expired session, failure, pause and worker-restart recovery were added later.
- **Reachability check: shipped and strengthened.**
  - The Add application form has a **Test connection** button that must pass before the form will submit, and the server checks again.
  - Since 2026-10-26, apps that need sign-in also have their login checked in a real browser before Discovery starts.
