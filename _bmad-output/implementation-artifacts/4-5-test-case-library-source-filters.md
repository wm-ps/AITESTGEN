---
last updated: 2026-10-27
---

# Story 4.5: Test case library & source filters

Status: done

## Story

As anyone in the workspace,
I want one place that lists every test case for an application, however it was created, with filters and search,
so that I can find a test quickly, see where it came from, and check or adjust it.

## What it does today

- **One list.** The Test cases tab lists every test case of the application, 10 per page. Each row shows:
  - the test case number,
  - the name,
  - the journey,
  - a source badge: **From discovery**, **Authored by prompt** or **Recorded**. Recorded tests are grouped under a journey called "Recorded tests".
- **Filter chips:** **All**, **Author test cases** and **Record-and-play test cases**, each with a count.
- **Search** by test case number, name or journey ("Search test cases"). If nothing matches: "No test cases match this search."
- **Expanding a row shows:**
  - the expected result;
  - **View code**, which opens the TypeScript Playwright test in a read-only pop-up;
  - **Test data** (members and admins), an inline form for the test's data fields.
    - Saving changed values makes the AI update just that one test to use them.
    - If the update fails, the user sees "Could not update this test's code — the previous version is still in use".
    - A test with no data fields says so.
- **Highlighting.** A test that was just recorded is highlighted when the user arrives from Record and play.
- **Empty states:**
  - Applications with Discovery: "Test cases appear here once discovery finds journeys and test cases are generated."
  - Applications without Discovery: "Author a test case in plain language or record a flow to add your first test case."
- **Viewers** can browse, search, filter and view code, but cannot edit test data.

## Acceptance criteria

1. **Given** an application with test cases, **when** a user opens Test cases, **then** every test case is listed with its number, name, journey and source badge, 10 per page.
2. **Given** the filter chips, **when** the user picks All, Author test cases or Record-and-play test cases, **then** only matching tests are shown, and each chip shows its count.
3. **Given** a search term, **when** the user types a test case number, name or journey, **then** the list narrows to matches, or says none match.
4. **Given** a test case row, **when** the user clicks **View code**, **then** its TypeScript Playwright code opens read-only.
5. **Given** a member or admin edits and saves a test's data, **when** the update succeeds, **then** that one test is rewritten to use the new values. **When** it fails, the previous version stays in use and the user is told.
6. **Given** the user has just saved a recording, **when** Test cases opens, **then** the new test is highlighted.
7. **Given** a viewer, **when** they expand a row, **then** they can view code but cannot change test data.

## Gaps / not built

- There is no "From discovery" filter chip; discovery-made tests are only reachable through All.
- Individual test cases can't be deleted, renamed or code-edited from this list. Renaming and deleting happen at the scenario level for discovery tests only.
- A "Notes" feature mentioned in history is not in the current product.
