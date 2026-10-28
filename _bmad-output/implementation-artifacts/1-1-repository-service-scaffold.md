---
last_updated: 2026-10-27
---

# Story 1.1: Platform foundation (repository & services)

Status: done

## Story

As the team building Vantage (AITestGen),
I want one shared foundation that every feature is built on,
so that each new capability fits into the same structure, data and background-work model instead of inventing its own.

## What it does today

Vantage is made of a small set of cooperating parts, all kept in one repository:

- **The web app** — the screens people use in the browser (sign-in, Overview, Applications, the per-application tabs, Team members, Activity, Settings).
- **The platform service** — the single place the web app talks to. It handles sign-in, enforces organization boundaries and roles, stores and returns data, and hands long-running work to the background workers.
- **Background workers** — separate processes for slow, long-running jobs, so the web app never waits on them:
  - an **Explorer worker** that learns an application the way a new tester would: it reads screens, asks a person when unsure, and writes and proves scenarios (Epic 8). It is the default way new applications are discovered;
  - a **discovery worker** that runs the classic discovery engine (exploring an application in a real browser and mapping journeys) for applications discovered before Explorer, and checks login credentials before any discovery starts;
  - a **generation worker** that drafts scenarios, writes Playwright tests and powers "Author a test case" (an AI agent working against the live application);
  - an **execution worker** that runs tests, self-heals failures, builds the HTML report, sends the run-completed email, fires scheduled runs, purges deleted applications and tidies up runs that got stuck.
- **A recording service** — hosts the remote browser used by Record and play and turns a recording into a test.
- **A background-job engine** — keeps long jobs reliable: they can be paused, resumed or cancelled and report progress that the screens show live. It also drives schedules.
- **A database** — holds every organization's applications, journeys, scenarios, test cases, runs, results, schedules, settings, team and activity history.
- **A secrets vault** — the only place the target applications' passwords and saved sessions are kept. They never sit in the database or in logs.
- **File storage** — holds screenshots, traces, videos and HTML reports.
- **An AI gateway** — every AI request (journey mapping, scenario drafting, test writing, self-healing, failure explanations) goes through one connection to a hosted AI model service, so the model can be changed in one place. Explorer is the exception: it reaches the same gateway through its own connection, with its own model settings that operations change separately.
- **Email** — invitations, password resets, run-completed emails, and Explorer's "App Summary ready" and "Explorer has a question" emails.

Supporting the build:
- The web app's picture of the platform service's data is generated from the service's own description, so the two can't silently drift apart; the automated checks fail if they do.
- Automated checks (lint, type checks, database migrations and tests for both the service side and the web app) are available but are started by hand; they no longer run automatically on every push. Pushes do trigger each part's build-and-deploy pipeline.
- Each part is packaged and deployed on its own to a hosted cloud environment, with one copy of each part running.
- For local development, the database, job engine, secrets vault and recording service start together with one command.

## Acceptance criteria

1. Given the repository, when a developer looks at its layout, then the web app, the platform service, each background worker, the recording service and the shared building blocks (data model, workflows, AI access, secrets, file storage, email, test-project assembly) each live in their own clearly separated area.
2. Given the platform service is running, when the web app needs data, then it gets it only through the platform service, whose self-description is used to generate the web app's data types.
3. Given a long-running job (discovery, generation, a test run, a schedule), when it is started, then it runs in a background worker through the job engine and the user can keep working.
4. Given a target application's credentials, when they are stored, then they go only to the secrets vault.
5. Given the automated checks are started, when they run, then lint, type checks, migrations and tests run for both the service side and the web app, and a mismatch between the web app's types and the service's interface fails the build.

## Gaps / not built

- **Delivery to customers' own CI/CD pipelines** — placeholders were set up on day one; the feature was never built.
- **Bring-your-own or on-premises AI model** — named as a future option; not built.
- **Explorer has no deployment setup yet.** Its worker is started only in local development. In a deployed environment, adding an application with discovery on marks its discovery as failed until the Explorer worker is deployed or operations switch new applications back to the classic engine.
- **Explorer keeps its screenshots and videos in the database** rather than in file storage, so the database grows with every run.
- **Production hardening** — the job engine runs in a lightweight mode that does not keep job history across restarts, and every part runs as a single copy.
