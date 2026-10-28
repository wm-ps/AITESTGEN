---
last_updated: 2026-10-27
---

# Story 8.3: Answer Explorer's questions

Status: done

## Story

As a member or admin,
I want Explorer to ask me when it is unsure or about to do something risky, and to remember my answers,
so that it gets past things only I know without guessing, and never asks me the same thing twice.

## What it does today

- **Where questions show.** The **Questions** button in the Explorer header shows a count and pulses when Explorer is waiting. It opens the **"Questions for you"** panel. The first open blocking question also appears in the Live tab's "Waiting for you" box with **Answer now**.
- **Blocking questions** cover things like "I need this to continue" (for example test data), "May I press Send?" (risky actions) and clarifications. Only the mission that asked waits, and only for **10 minutes by default**; after that it carries on without the answer. Everything else keeps running.
- **"Is this a bug?" questions never block.** They don't count as "Waiting for you" and sit with the finding they are about (Story 8.4).
- **Answers become trusted knowledge** for the application, for this run and every later one. Explorer checks what it already knows before asking, so the same question isn't asked twice, and similar open questions are merged. A question can also be dismissed.
- **Email.** The person who started the run is emailed when Explorer asks a blocking question.

## Acceptance criteria

1. **Given** Explorer needs information or permission, **when** it asks, **then** the Questions count goes up, the button pulses and the question appears in the panel and the "Waiting for you" box.
2. **Given** a blocking question, **when** nobody answers within the wait time, **then** the asking mission carries on without the answer; other missions are never held up.
3. **Given** the user answers a question, **when** Explorer later meets the same need in this run or a future one, **then** it uses the answer instead of asking again.
4. **Given** two open questions ask for the same thing, **when** they are shown, **then** they are merged into one.
5. **Given** an "is this a bug?" question, **when** it is open, **then** it doesn't block anything or count as waiting.
6. **Given** a risky action (deleting data, moving money, a business decision, signing out), **when** Explorer reaches it, **then** it asks before doing it.

## Gaps / not built

- Viewers see the answer buttons, but the platform refuses their answers.
- Without mail settings on the server, the question email is not sent (it is only logged).
- The wait time is a server setting only operations can change.
