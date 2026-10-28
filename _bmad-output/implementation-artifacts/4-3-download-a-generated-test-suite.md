---
last updated: 2026-10-27
---

# Story 4.3: Download a generated test project

Status: done

## Story

As a member or admin,
I want to download all of an application's tests as a ready-to-run Playwright project,
so that my team can run, keep and change the tests outside Vantage, for example in our own pipeline.

## What it does today

- **Download project tab.** Shows the structure of the project to be downloaded:
  - one folder per journey containing its TypeScript Playwright test files;
  - shared fixtures and helpers;
  - the Playwright configuration file;
  - a README.
- **Download project** gives a .zip of a complete, runnable **TypeScript** Playwright project. It includes every current test case in the application, whatever its source: from Discovery, authored by prompt, or recorded.
- **No secrets in the download.** The application's saved login is never included. The README explains how to supply a username and password when running the tests. If the tests need sign-in but no login form was ever recorded (for example, apps discovered by Explorer), the project gets a generic sign-in step that opens the application's login address and fills the password field.
- **Other places to download.** The test-generation progress screen also has a **Download Test Cases** button.
- **When it's available:**
  - The tab is always listed (except for viewers). If no tests exist yet, it says "No test cases generated yet".
  - Viewers don't see the tab, and the server refuses the download for them.
- **Always current.** The download always reflects the latest version of each test, including fixes made by self-healing and edits to test data.

## Acceptance criteria

1. **Given** an application with at least one test case, **when** a member or admin opens Download project, **then** the project structure is shown (journey folders with test files, fixtures, helpers, configuration and README).
2. **Given** the user clicks **Download project**, **when** the download completes, **then** they get a .zip containing a runnable TypeScript Playwright project with every current test case.
3. **Given** the application signs in with a saved login, **when** the project is downloaded, **then** no username or password is inside it, and the README explains how to supply them at run time.
4. **Given** a test was healed or its test data was edited, **when** the project is downloaded afterwards, **then** the updated version of that test is included.
5. **Given** an application has no test cases, **when** the user looks at the sidebar, **then** the Download project tab is not shown.
6. **Given** a viewer, **when** they use the application, **then** the Download project tab is hidden and the download is refused.

## Gaps / not built

- Only TypeScript output exists. Generated code switched from Python to TypeScript, and any older description of a Python download is out of date.
- No direct delivery into a customer's CI/CD system; the .zip is the only hand-off.
- The **Download project** button shows a static "Downloading…" while busy instead of the standard trailing bouncing dots.
