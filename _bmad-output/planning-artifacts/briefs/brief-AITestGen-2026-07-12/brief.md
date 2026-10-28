---
title: "Product Brief: Vantage (AITestGen)"
status: approved
created: 2026-07-12
updated: 2026-10-27
---

# Product Brief: Vantage (AITestGen)

## Executive Summary

Vantage is a web app for QA and engineering teams. It turns a deployed web application into a working, maintained Playwright test suite, with very little hand-writing of tests.

A team adds an application: its URL and, if it needs one, a test login. Vantage can then explore the application by itself in a real browser ("Discovery"). The default discovery engine, **Explorer**, learns the application the way a new QA engineer would: it writes a one-page App Summary for a person to confirm, asks questions when it is unsure, works through goals ("missions"), and writes and proves test scenarios. Only proven scenarios are handed on, and Vantage writes Playwright tests for them. Teams run those tests on demand or on a schedule. When a test fails, AI can repair it ("self-healing"), but the AI is never allowed to change what a test checks. Results show the pass rate, flaky tests and plain-language explanations of each failure. A branded HTML report and a "run finished" email go with every completed run.

Discovery is optional. Teams can add tests in two other ways. They can describe a test in plain English and let an AI agent explore the live application and write it, or they can click through a flow once in a remote browser and save it as a test. The whole generated project can be downloaded and run outside Vantage.

The longer-term ambition is still to be the place a team goes to understand what its application does and what a release puts at risk. That ambition has to be earned through real use; the product today is a test-coverage and test-maintenance product built on runtime discovery.

## The Problem

Enterprise web applications build up years of shared logic and cross-team dependencies. The people who built a journey move on, and documentation goes stale within a release or two. A small change in one place can quietly break a workflow nobody knew was connected, and the cost shows up as a production incident, not as a failed test.

QA teams carry most of this. They discover journeys by hand, through tribal knowledge and exploratory testing, then write and maintain tests for what they find. They are always one step behind an application that keeps changing. Even once tests exist, maintenance is a treadmill: a renamed button or a moved field breaks tests that were testing the right thing, and someone has to fix them by hand.

Most test-automation tools help once someone already knows a journey exists. They do not answer the question that comes first, "what does this application actually do, as built?", and they do not take the maintenance burden off the team without risking tests that quietly stop checking anything.

## The Solution

A team member adds an application to Vantage: a name, an environment, the URL and, if the application needs it, a test username and password. Vantage checks that the URL is reachable and, before it explores anything, logs in once in a real browser to prove the credentials work. No source code access, repository access or installed agent is needed.

**Discovery with Explorer (the default).** Adding an application with Autonomous discovery on starts Explorer. It signs in, reads each screen and names it by what it means, and notes health problems such as broken screens, server errors, slow pages and wording mistakes. It then writes an **App Summary** and waits for a person to check and confirm it. After that it plans missions (goals such as "file a claim") and works through up to three at a time. It also hunts for screens that only appear sometimes. When it is unsure, needs test data, or is about to do something risky, it asks a question; only the mission that asked waits, and every answer becomes knowledge it keeps for that application. Explorer never deletes data, moves money, makes a business decision or signs out on its own. It finally writes scenarios in seven kinds and **proves** each one: a proven scenario replays the same way every time and fails when its key step is removed. When the application behaves differently from what should happen, the scenario is kept as a "possible bug" for a person to judge rather than passed off as correct. Explorer has its own tab with a live view, what it learned, the screens it found, and its scenarios, plus a Questions panel. Explorer can be paused, stopped and resumed from that tab.

**Classic discovery.** The earlier discovery engine still runs for applications discovered before Explorer became the default, and for new applications if operations switch Explorer off. It explores the application like a thorough tester. It moves through pages breadth-first, opens tabs inside pages, re-logs in if the session expires and avoids clicking the same thing forever or taking risky, destructive actions. It stops when nothing new is left, or when it reaches the page limit (500 by default) or the time limit (30 minutes by default). Admins can change both limits. The result is a set of business journeys, each with a screenshot and its page-by-page steps. Discovery can be paused and resumed, and it survives a restart of its own service.

**From journeys to tests.** With Explorer, only proven scenarios are handed on; the user presses **Generate tests**, and a test Explorer already proved is reused as-is when it compiles. With classic discovery, finishing Discovery does not start generation by itself. The team reviews the journeys, renames or deletes any that are wrong, then asks Vantage for scenarios. Each scenario has test steps, test data and an expected result. The team edits or auto-fills the test data, then asks Vantage to write the Playwright tests. A progress screen shows each journey's status and lets the team stop or retry generation.

**Other ways to add tests.** Without any Discovery, a team member can:
- describe a test in plain English and let an AI agent explore the live application and write it, or
- record a flow by clicking through it in a remote browser streamed into the page, then save it as a test.

Every test, whatever its source, lands in one test case library with filters by source.

**Running and maintaining tests.** Tests run all at once or as a named selection of journeys and test cases. Runs can be cancelled. A failing test is repaired automatically within limits. The repair may fix how a test finds the page, but it never touches what the test asserts. Each run shows passed, self-healed, flaky and failed tests, a plain-language explanation of every failure with a screenshot and trace, a branded HTML report and an email to the person who started it. Schedules run the tests daily, weekly, monthly or on a custom cron expression.

**Running the workspace.** An org-wide Overview shows pass rate over time, the latest run outcomes and what is running right now. Admins manage team members and their roles (admin, member, viewer), adjust settings such as discovery limits and screenshot retention, manage saved credentials and see an Activity history of everything that happened.

## What Makes This Different

URL-only autonomous discovery is not unique; several vendors claim it, and Playwright now ships free agents that explore an app and write tests. Vantage does not sell on a proprietary discovery algorithm.

What Vantage offers is the complete loop in one place, with guardrails a QA team can trust:
- **Three ways in, one library.** Discovery, plain-English authoring and record-and-play all produce the same kind of test, using the same locators, the same self-healing and the same reporting.
- **Self-healing that never cheats.** Healing repairs how a test finds things on the page. It refuses any fix that changes an assertion and never heals a failed assertion, so a healed test still checks what it checked before.
- **Plain-language results.** Failures are explained in plain words. Known errors are explained by fixed rules, unknown ones by AI with a clear "may not be exact" label. Flaky tests are flagged from their recent history.
- **Low-friction start.** A URL and a test login are enough. The credentials are proven to work before any exploration starts.
- **An exit door.** The whole project downloads as a runnable Playwright project, so the team is never locked in.

## Who This Serves

**QA leads and QA teams** are the daily users. They add applications, curate journeys and scenarios, author and record tests, run suites, read failures and keep schedules running.

**Engineering leaders** use the Overview and the Applications list to see health across applications (Healthy, Needs attention, Critical), pass rate over time and what is running now.

**Workspace admins** manage the team, roles, settings, saved credentials and the Activity history.

Accounts are invite-only and belong to one organization. There are three roles:
- **Admin** can do everything, including team management, settings, saved credentials, the Activity page and renaming or deleting applications.
- **Member** can add applications, run discovery, curate, generate, author, record, run and schedule tests, and download the project.
- **Viewer** can see everything in the organization but cannot change anything, open reports or download the project.

## Success Criteria

Success is measured by real use, not by a customer-count or revenue target. No numeric coverage or time-saved target is set yet. Inventing one before there is real usage data would be a made-up claim, not a criterion.

The signals that matter:
- **Coverage.** How many of an application's journeys end up backed by running tests.
- **Time saved.** Compared with finding journeys and writing tests by hand.
- **Trust.** Teams keep using Vantage into a second and third release cycle without being pushed to. Discovered journeys need light correction rather than heavy rework. Generated tests are trusted enough to go into the team's real regression process.
- **Maintenance relief.** Failures are healed or clearly explained, and flaky tests are visible rather than ignored.

## Scope

**Built today:**
- Invite-only sign-in, password reset, organization-scoped workspaces and three roles.
- Adding an application with a URL check, an optional login that is proven in a real browser before Discovery, and optional Discovery.
- Explorer as the default discovery engine: a live view, an App Summary the user confirms, questions and answers that become app knowledge, missions, a screens gallery, health findings, proven scenarios with proof videos, and hand-off of proven scenarios to test generation.
- Classic autonomous Discovery of journeys (for earlier applications), with pause and resume, recovery after a restart, limits set by admins and safe handling of risky actions.
- Journey curation (rename, delete), scenario review with editable test data, and Playwright test generation with per-journey progress, stop and retry.
- Plain-English test authoring and record-and-play.
- A test case library with source filters, a code view and test data editing.
- Test runs (all or selective), cancel, automatic and manual self-healing, flaky flags, failure explanations with screenshots and traces, a branded HTML report and a run-completed email.
- Scheduled test runs.
- Download of the whole project as a runnable Playwright project.
- An org-wide Overview dashboard, team management, settings and an Activity history.

**Not built / deferred:**
- Delivery into a customer's CI/CD pipeline or repository.
- Bring-your-own or on-premise AI models, and an on-premise deployment option.
- A business capability map, risk scorecard or change-impact analysis.
- Reading source code to inform discovery.
- Scheduling Discovery. Only test runs can be scheduled.
- Single sign-on session reuse and MFA codes for the application under test, which work on the server but have no screen. API-key and OAuth sign-in for the application under test.
- For classic discovery: a screen for the coverage report, and a way to answer its "I need data to continue" requests. (Explorer asks and takes answers.)
- Explorer features that work behind the scenes but have no screen yet: adding your own mission, per-mission recordings, a shareable highlight video, the run report, downloading Explorer's proven tests, and re-writing scenarios without exploring again.
- Tighter roles in Explorer: viewers can't change anything there, but any member can manage its other user types and knowledge, and viewers can download its results.
- Re-generating a journey's scenarios from scratch.
- Mobile and native applications, and test frameworks other than Playwright.
- Dark mode, which was explicitly dropped.

## Open Questions

- **Time to first map.** How long Discovery takes on a typical enterprise application has not been measured across real customers. Confirm before quoting it externally.
- **Proof threshold.** What usage evidence counts as "the product has proven itself" is still not defined.
- **Production safety.** Whether Vantage should technically stop someone pointing Discovery at a production environment. Today that is the customer's responsibility, softened by the safe handling of risky actions.

## Vision

The arc is unchanged: **coverage intelligence → application intelligence → change intelligence.** Vantage today proves that an application's journeys can be found and turned into running, self-maintaining regression coverage. The next steps are to connect journeys to the code that implements them, and then to tell a team which journeys and tests a given change puts at risk before it ships.

That is the destination, not a promise about the product as it stands.
