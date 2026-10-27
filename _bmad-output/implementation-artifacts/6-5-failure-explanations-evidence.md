---
last updated: 2026-10-27
---

# Story 6.5: Failure explanations & evidence (screenshots, traces)

Status: done

## Story

As anyone reviewing a test run,
I want each failure explained in plain language, with a screenshot and a step-by-step trace,
so that I can understand what went wrong without reading raw test errors.

## What it does today

- **Failure details.** Expanding a failed test in run detail shows two tabs:
  - **Summary:** a plain-language title and explanation of what went wrong, naming the element or step involved where possible.
    - Common, recognisable errors (an element not found, a timeout, a sign-in problem, a page that didn't load, and so on) are explained by fixed rules.
    - Anything else is explained by AI once and remembered for identical errors. AI explanations are labelled "Explained by AI — may not be exact".
    - If nothing can be worked out: "The test failed for a reason Vantage couldn't identify — See the Raw error tab for the full details."
  - **Raw error:** the full original error.
- **Privacy.** Before an error is sent to the AI, passwords, tokens, emails and similar sensitive values are removed.
- **One shared cause.** When at least 3 failed tests, making up at least 60% of the failures, share one environment-level cause, the run shows a banner: "N of M failed tests have the same cause — <cause> — fix this first." The causes are:
  - "This app's saved login details couldn't be loaded"
  - "Vantage couldn't sign in to the app"
  - "The test run couldn't be set up"
  - "A problem in Vantage stopped the tests"
  - "The app's pages didn't load"
  Test-specific failures (a wrong value on the page, an element not found) never produce this banner.
- **Evidence.** Each failure links to a **Screenshot** and a **Playwright trace**, with their sizes, to open in a new tab.
  - Traces are kept for failed tests only.
  - Screenshots follow the admin **Screenshot capture** setting: failed tests (default), passed tests, or all.
  - If nothing was captured: "No screenshot or trace was captured for this failure."
- **Elsewhere.** The same plain-language explanations appear in the run-completed email. Admins also see screenshot, trace, exact error and error log for failed tests in the Activity page's detail drawer.
- **Skipped tests.** A test deliberately skipped in its code (for example one recording a known bug) is shown as **Skipped** with its reason, rather than as a failure with an explanation.
- Everyone, including viewers, can read explanations and open evidence.

## Acceptance criteria

1. **Given** a failed test with a recognisable error, **when** the user opens its details, **then** the Summary tab shows a plain-language explanation from the fixed rules.
2. **Given** an error the rules don't recognise, **when** the details are opened, **then** an AI explanation is shown, labelled "Explained by AI — may not be exact", and reused for identical errors later.
3. **Given** any failure, **when** the user switches to **Raw error**, **then** the full original error is shown.
4. **Given** an error is sent to the AI, **when** it is prepared, **then** sensitive values are removed first.
5. **Given** at least 3 failures and at least 60% of them share one environment-level cause, **when** the run is viewed, **then** a banner names that cause and says to fix it first.
6. **Given** a failed test, **when** its details are opened, **then** links to its screenshot and Playwright trace are shown, subject to the Screenshot capture setting.
7. **Given** no evidence was captured, **when** details are opened, **then** "No screenshot or trace was captured for this failure." is shown.

## Gaps / not built

- The fixed rules only recognise English error wording.
- Video recordings of test runs are not offered.
