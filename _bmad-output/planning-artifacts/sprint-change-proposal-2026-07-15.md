---
title: "Change record — UX redesign ripple (2026-07-15)"
status: approved
created: 2026-07-15
approved: 2026-07-15
last updated: 2026-10-27
---

# Change record: UX redesign ripple (2026-07-15)

## What was proposed and why

A second interactive prototype ("v2") replaced the first one before any code had been written. It wasn't a visual refresh; it described a different product shape:

- The planned 11-screen, multi-application product with a permanent left-hand menu became a 6-screen guided path for one application: Sign in, Home, Connect app, Discover journeys, Review scenarios, Generate suite.
- Reviewers could now rename, edit and remove journeys and scenarios. Earlier plans had allowed only approve/reject/rename/delete on journeys and had made scenarios read-only.
- Six planned screens had no place in the new design: the multi-application list, the capability map, coverage analytics, the executive dashboard, the CI/CD connection screen and Settings.
- The prototype showed three run choices: "Run immediately", "Schedule for later" and "Save without running". These were confirmed as placeholders only. No decision had been made on whether the product would run tests itself.

## What was decided

- The plan was rewritten to match the guided six-screen path.
- CI/CD delivery, the capability map, coverage analytics and the executive dashboard were cut from the first release.
- The "journey explorer" idea was kept, folded into the Discover Journeys detail view.
- Two judgment calls were settled as full cuts rather than "kept but deferred": the on-premises/bring-your-own-AI requirement, and the executive's dashboard user journey.
- Test execution stayed undecided on purpose.

## Where it stands today (2026-10-27)

Much of this decision was later reversed as the product grew:

- **Guided path: reversed.** In September the step-by-step wizard was replaced by a left sidebar shell. Tabs can be opened in any order. It covers Overview, Applications, Add application, Team members, Activity and Settings, plus per-application tabs.
- **Multi-application list and dashboard: reversed (rebuilt in a different form).** There is now an Applications list with health status and an org-wide Overview dashboard (pass rate, failure rate, run duration, active pipelines, charts). It is not the planned executive dashboard, but it covers the same need.
- **Settings: reversed.** Settings exists, admin only. It holds discovery limits, self-heal attempts, screenshot capture, clean-up timing and saved credentials. It has no AI-provider switch.
- **Test execution: built.** The "placeholder" run choices became real features: run all or a named selection, cancel, self-healing, reports, emails and scheduled runs.
- **Reviewer editing: partly as decided.** Journeys can be renamed and deleted (no wider edit). Scenarios can be renamed and deleted, and their test data can be edited.
- **Still never built:** CI/CD delivery, on-premises or bring-your-own AI, the capability map, and a coverage-analytics screen.
