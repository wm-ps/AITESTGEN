---
last updated: 2026-10-27
---

# Story 4.4: Author a test case in plain English

Status: done

## Story

As a member or admin,
I want to describe a test in plain language and have Vantage explore the live application and write it for me,
so that I can add exactly the test I need without waiting for Discovery and without writing code.

## What it does today

- **Where.** The Test cases tab has an **Author a test case** panel. It works for every application, including ones added without Discovery: "No prior discovery is needed — a live agent explores the application itself."
- **Input:**
  - **Journey.** The user either picks an existing journey or chooses to create a new one and enters its name.
  - **Description.** The user describes in plain language what should happen: the steps to take and what to check.
  - The user then clicks **Explore and generate**.
- **What happens.** Vantage first checks that the request really is a test case for this application. If it isn't, the user sees "That doesn't look like a test case request for this application" (or a more specific reason) and can try again.
  - An AI agent then opens the real application in a browser, signing in with the application's saved login if it has one, and works through the described steps.
  - Progress reads "Exploring the live application…" and then "Generating the test case…".
  - The test is written from the path the agent actually took. Vantage runs it once as a check, and repairs it if needed. That check run does not appear in Test runs.
- **Result:**
  - Shows the journey the tests were added to and "N test cases added", with the reminder to run them from the Test cases tab. One description can produce more than one test case.
  - If the agent couldn't do some steps in the application, they are listed under "Not generated — Vantage couldn't do these in the application".
  - On an error the message is shown, with **Try again**.
  - **+ Explore another** starts a new request; **Close** closes the panel.
- **After it's added.** New tests carry the source badge **Authored by prompt**. They behave like any other test: they get a test case number, can be run, are self-healed when they fail, are included in the download and appear under the "Author test cases" filter.
- **Leaving mid-request.** If the user leaves the page while a request is running, its progress is picked up again on return.
- **Viewers** cannot author test cases.

## Acceptance criteria

1. **Given** any application (with or without Discovery), **when** a member or admin opens Author a test case, **then** they can choose an existing journey or name a new one, and enter a plain-language description.
2. **Given** the description isn't a sensible test request for the application, **when** it is submitted, **then** it is rejected with a reason and the user can try again.
3. **Given** a valid request, **when** it is submitted, **then** a live agent explores the running application (signed in if a login is saved), and progress shows "Exploring the live application…" then "Generating the test case…".
4. **Given** exploration succeeds, **when** generation finishes, **then** the new test case(s) are added to the chosen journey, the count is shown, and the tests appear in the list as **Authored by prompt**.
5. **Given** some requested steps couldn't be performed in the app, **when** the result is shown, **then** those steps are listed under "Not generated — Vantage couldn't do these in the application".
6. **Given** the request fails, **when** the result is shown, **then** the error is displayed with **Try again**.
7. **Given** the user leaves and returns while a request is running, **when** the Test cases tab reloads, **then** the request's progress is shown again.
8. **Given** a viewer, **when** they open Test cases, **then** they cannot author a test case.

## Gaps / not built

- The submit button shows a static "Submitting…" while busy instead of the standard trailing bouncing dots.
