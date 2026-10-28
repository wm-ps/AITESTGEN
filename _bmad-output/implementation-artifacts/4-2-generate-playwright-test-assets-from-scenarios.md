---
last updated: 2026-10-27
---

# Story 4.2: Generate Playwright test cases from scenarios

Status: done

## Story

As a member or admin,
I want Vantage to turn my reviewed scenarios into runnable Playwright tests,
so that I get a working automated test suite without writing scripts by hand.

## What it does today

- **Trigger.** On the Scenarios tab the user clicks **Generate test cases**. Vantage writes one Playwright test (TypeScript) per scenario, for every journey of the application, and moves the user to the Test cases tab.
- **Grounded in what Discovery saw.** Each test is written using the pages and on-screen elements Discovery actually captured. This keeps element lookups realistic instead of guessed.
- **Quality checks before a test is kept:**
  - Every test is checked to make sure it is valid code. If not, the AI repairs it automatically.
  - A second check looks for risky patterns. It only flags the test for review; it never blocks it.
- **Test data.** Values the user entered on the Scenarios tab are used. Any blank field gets a sensible default, which is saved back to the scenario.
- **Progress screen ("Test Cases Generated").** Shown once, right after generation starts:
  - stages: Resolving locators → Writing test cases → Generating fixtures;
  - counts: test cases, journeys covered and an estimated runtime;
  - status per journey.
- **When some tests can't be written.** Each scenario is retried several times. If some still fail, the journey is marked **Incomplete** ("Some scenarios in this Journey couldn't be generated after several retries"), and a line says how many test cases failed to generate.
  - **Retry Generation** tries again for the missing ones only. Tests already written are kept.
  - **Terminate** closes an incomplete journey for good, and it shows **Terminated**. Later retries leave it alone.
- **Finishing.** When generation is done, the screen offers **Download Test Cases** and **Run Test Cases**.
- **Numbering.** Every test case gets a permanent test case number within the application.
- **Admin limit.** "Maximum test cases / application" caps the total. Scenarios beyond the cap are not turned into tests.
- **After generation**, all tests live in the Test cases tab (see Story 4.5). There, a test's data can be edited, which rewrites just that one test.
- **Viewers** can see the results but cannot start, retry or terminate generation.

## Acceptance criteria

1. **Given** at least one scenario exists, **when** the user clicks **Generate test cases**, **then** a TypeScript Playwright test is generated for each scenario across all journeys, and the progress screen is shown.
2. **Given** generation is running, **when** the user watches the progress screen, **then** it shows the stages, the test case / journey / estimated-runtime counts and a status for each journey.
3. **Given** a generated test is not valid code, **when** it is checked, **then** the AI repairs it before it is saved.
4. **Given** a scenario has blank test data fields, **when** its test is generated, **then** default values are filled in, used and saved on the scenario.
5. **Given** some scenarios in a journey still fail after retries, **when** generation finishes, **then** the journey shows **Incomplete** and a count of test cases that failed to generate is shown.
6. **Given** an incomplete journey, **when** the user clicks **Retry Generation**, **then** only the missing tests are attempted again.
7. **Given** an incomplete journey, **when** the user clicks **Terminate**, **then** it shows **Terminated** and is not retried again later.
8. **Given** the per-application test case limit has been reached, **when** more scenarios are generated, **then** no further tests are created.
9. **Given** generation has finished, **when** the user views the progress screen, **then** **Download Test Cases** and **Run Test Cases** are offered.
10. **Given** a viewer, **when** they view the progress screen, **then** Retry and Terminate are not available.

## Gaps / not built

- Tests flagged by the risky-pattern check are marked for review on the server, but the Test cases list does not show that flag.
- The happy / negative / edge type badge is hidden in the UI.
- The Terminate button shows a static "Terminating…" while busy instead of the standard trailing bouncing dots.
