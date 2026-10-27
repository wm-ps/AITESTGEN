---
last_updated: 2026-10-27
---

# Story 3.4: Rename & delete a journey

Status: done

## Story

As a QA engineer,
I want to rename a discovered journey or remove one that doesn't belong,
so that journey names make sense to my team and irrelevant flows don't get tests.

## What it does today

Every discovered journey is trusted and used for scenarios and tests by default; there is no approve/reject step. Rename and Delete are the only ways to curate. Both are in the journey card's ⋮ menu on the Journeys tab, for members and admins (viewers don't see the menu).

**Rename.** The name becomes an inline text box. Enter or clicking away saves it; Escape cancels; an empty name is ignored. The new name shows everywhere the journey appears (Journeys, Scenarios, Test cases, runs and the downloaded project).

**Delete.** A confirmation asks "Delete this Journey? It will be excluded from the Trusted Knowledge Model." On confirming, the card disappears and the journey is left out of:
- scenario drafting and the Scenarios tab,
- test case generation and the Test cases list,
- test runs,
- the downloaded project.

There is no undo or "show deleted" view. A journey that has already been deleted can't be renamed or deleted again. Deleting does not stop work that is already running for that journey.

## Acceptance criteria

1. Given a member or admin, when they choose Rename on a journey and enter a new name, then it is saved and shown everywhere the journey appears.
2. Given the rename box, when the user presses Escape or leaves it empty, then the name is unchanged.
3. Given a member or admin, when they choose Delete and confirm, then the journey disappears and is excluded from scenarios, test cases, runs and downloads.
4. Given the user cancels the confirmation, when the dialog closes, then nothing changes.
5. Given a viewer, when they look at a journey, then no Rename or Delete option is offered and the platform refuses such changes.

## Gaps / not built

- No undo or restore for a deleted journey.
- Editing a journey's steps is not supported.
