---
last_updated: 2026-10-27
---

# Story 8.2: Review and confirm the App Summary

Status: done

## Story

As a member or admin,
I want Explorer to tell me what it thinks my application is for and wait for me to confirm it,
so that everything it tests afterwards is based on an understanding I have checked.

## What it does today

- **Learning the app.** Explorer signs in and reads each screen the way a person would. It names screens by what they mean, so a thousand customer pages count as one "Customer details" screen.
- **The App Summary.** When it has learned enough, Explorer writes a one-page summary and **stops and waits** for a person. The summary has the application name, a one-liner, key tasks, questions for the user with answer options, an optional "Goal for this run", and screens to leave out.
- **Where to check it.** The Live tab's "Waiting for you" box says "Explorer has learned the app. Check its summary and confirm…" with a **Check the summary** button. The summary sits on the **What it learned** sub-tab.
- **Editing and confirming.** While the summary is waiting, the user can **Edit** it, **Save changes**, and press **"Looks right — confirm"**. Confirm stays disabled until every question in the summary is answered. Answers become trusted knowledge for the application (Story 8.3).
- **Email.** The person who started the run gets an email when the summary is ready.
- **Knowledge panel** on the same sub-tab: the user can add a fact or test data, upload a document (PDF, Word, plain text, Markdown or CSV; 15 MB maximum), or forget an item. Knowledge belongs to the application and carries over to every later run. Explorer judges what it sees against common sense, these answers and documents; it doesn't treat the application itself as the source of truth, and it never confirms anything on the user's behalf.
- **Expiry.** If the summary isn't confirmed within **14 days**, the run ends for good and can't be resumed. A banner says so, and "Start a new run" begins from what was already learned, keeping the user's answers.

## Acceptance criteria

1. **Given** Explorer has learned the application, **when** the summary is ready, **then** the run waits, the "Waiting for you" box offers Check the summary, and the starter is emailed.
2. **Given** a waiting summary, **when** the user edits it and saves, **then** the changes are kept.
3. **Given** a summary with unanswered questions, **when** it is shown, **then** "Looks right — confirm" is disabled.
4. **Given** every question is answered, **when** the user confirms, **then** the answers become knowledge for the application and Explorer moves on to missions (Story 8.4).
5. **Given** a summary left unconfirmed for 14 days, **when** the time is up, **then** the run is expired, can't be resumed, and a new run can start from what was learned.
6. **Given** a document or fact is added in the Knowledge panel, **when** a later run starts, **then** Explorer uses it.

## Gaps / not built

- Members, not just admins, can add or delete knowledge and documents. (Viewers see the buttons, but the platform refuses their changes.)
- Without mail settings on the server, the "summary ready" email is not sent (it is only logged).
- A "requirements first" flag is worked out but has no screen.
- Explorer reads dates in English month names only.
