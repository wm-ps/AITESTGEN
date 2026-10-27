---
last updated: 2026-10-27
---

# Story 6.4: Flaky test flags

Status: done

## Story

As a QA lead,
I want tests that sometimes pass and sometimes fail to be clearly flagged,
so that I can tell unreliable tests apart from real, consistent failures and fix them first.

## What it does today

- **Rule.** A test is **flaky** if its last 10 finished results, including the current run, contain at least one pass and at least one failure. Timeouts and errors count as failures.
- **What doesn't count:**
  - cancelled runs;
  - the internal check runs Vantage does while authoring or verifying tests;
  - a test's very first run, which is never flaky.
- **Where it shows:**
  - In run detail, a flaky test shows a purple **Flaky** chip ("Inconsistent results across this test's recent runs — it has both passed and failed.").
  - Flaky tests are counted in their own **Flaky** group alongside Passed / Self-healed / Failed.
  - A test that was **Self-healed** in this run shows that chip instead; the two are never shown together.
- **Always up to date.** The flag is worked out fresh every time a run is viewed, so it reflects the latest history.
- Everyone, including viewers, can see the flag.

## Acceptance criteria

1. **Given** a test whose last 10 finished results include at least one pass and one failure, **when** a run containing it is viewed, **then** the test shows the **Flaky** chip.
2. **Given** a test that has only passed, or only failed, in its last 10 finished results, **when** the run is viewed, **then** it is not flagged.
3. **Given** a test's first ever run, **when** it is viewed, **then** it is not flagged as flaky.
4. **Given** cancelled runs or internal check runs, **when** flakiness is worked out, **then** they are ignored.
5. **Given** a test was self-healed in this run, **when** the run is viewed, **then** it shows Self-healed rather than Flaky.
6. **Given** a run with flaky tests, **when** the results summary is shown, **then** flaky tests are counted in the Flaky group.

## Gaps / not built

- The 10-result window is fixed and not configurable.
- Flaky tests are not called out in the run-completed email, the HTML report or the Overview dashboard.
- There is no list of flaky tests across runs; the flag is only visible inside a run.
