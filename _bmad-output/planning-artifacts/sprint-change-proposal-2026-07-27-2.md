---
title: "Change record — Download a generated test project (2026-07-27, follow-up)"
status: approved
created: 2026-07-27
last updated: 2026-10-27
---

# Change record: Download a generated test project (2026-07-27, follow-up)

## What was proposed and why

Generated tests could only be viewed one at a time in a pop-up. The request was a single **Download** action that produces a complete, runnable Playwright project, with one folder of tests per journey plus the usual project files and a README. This was deliberately framed as an export to the user's computer, not as pushing tests into a customer's code repository or CI pipeline (that remained cut).

## What was decided

- Approved as a new story: "Download a generated test project".
- When the story was written up, it turned out the tests were being generated in Python at the time. So the download was first specified as a Python project, with the user's agreement.

## Where it stands today (2026-10-27)

**Shipped, now in TypeScript.**

- Two days later, on 2026-07-29, test generation switched to TypeScript, and the download followed. The Python version is history.
- The application's **Download project** tab:
  - shows the project layout (tests per journey, shared fixtures and helpers, Playwright configuration, README);
  - downloads a runnable TypeScript Playwright project as a .zip.
- The tab appears once at least one test exists. Viewers can't see it or download.
- CI/CD delivery is still not built.
