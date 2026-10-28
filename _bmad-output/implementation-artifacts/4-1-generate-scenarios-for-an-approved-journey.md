---
last updated: 2026-10-27
---

# Story 4.1: Generate scenarios for a journey

Status: done

## Story

As a member or admin,
I want Vantage to draft test scenarios for every journey it discovered, and let me tidy them up and fill in their test data,
so that the journey map turns into concrete test coverage that I control before any test code is written.

## What it does today

- **Explorer applications.** For an application discovered by Explorer (Epic 8), scenarios are not drafted here. Explorer writes and proves its own scenarios and hands over only the proven ones; possible bugs are sent on only when the user marks them "Not a bug" (Story 8.5). The Journeys and Scenarios tabs are hidden for these applications, and the user presses **Generate tests** on Explorer's own Scenarios tab. If the Scenarios page is reached anyway, it keeps **Generate test cases** and adds "Explorer worked these out by using the app. Generate test cases to turn them into tests." Generation uses the test Explorer already wrote and proved, as-is, when it is valid code; the AI writes a new one only when it isn't. The rest of this story describes classic-engine applications.
- **The user starts it; it is never automatic.** When Discovery finishes, nothing is generated on its own. On the Journeys tab the user clicks **Review scenarios**. That starts scenario drafting for every remaining (not deleted) journey of the application and moves the user to the Scenarios tab.
- There is no approve/reject step for journeys. Every journey the user has not deleted is included.
- **Progress.** While scenarios are being drafted, the Scenarios tab shows the stages Reading journeys → Drafting scenarios → Deriving test data, and fills in as each journey finishes.
- **What a scenario contains.** Scenarios are grouped by journey. Each shows:
  - its test steps,
  - its test data fields, and
  - its expected result.
  The AI covers the normal (happy) path plus negative and edge cases. The type is tracked but the type badge is hidden in the UI on request.
- **Test data fields.** The AI decides which inputs a scenario needs (for example a username, an amount, a search term) but does not invent the values. Each field is marked either "Required for this scenario" or "Optional — auto-filled if left blank". A required field that is still empty shows "Required to generate this test".
- **What the user can do with a scenario:**
  - rename it,
  - delete it,
  - edit test data values inline (saved automatically),
  - **Auto-generate** sensible default values for its fields (no AI involved),
  - **Clear** all its values.
- **Admin limit.** The number of scenarios per journey is capped by the "Maximum scenarios / journey" setting.
- **Failures are contained.** If drafting fails for one journey, the others carry on. Each journey is retried automatically (up to 3 attempts); if it still fails, it is listed on the Scenarios tab with the reason. There is no way to retry it from the screen. If the drafting service itself is not available, the tab shows a service error with a "Go back and retry" link to the Journeys tab.
- **Next step.** **Generate test cases** is enabled as soon as at least one scenario exists. Any test data field still blank at that point (required or optional) is filled with a default value during generation, so empty fields never block it.
- **Viewers** can see scenarios but cannot start drafting or change anything.

## Acceptance criteria

1. **Given** Discovery has finished and journeys are listed, **when** the user clicks **Review scenarios**, **then** scenario drafting starts for every journey that has not been deleted, and the user is taken to the Scenarios tab.
2. **Given** Discovery has just finished, **when** the user does nothing, **then** no scenarios are drafted.
3. **Given** drafting is in progress, **when** the user views the Scenarios tab, **then** progress shows Reading journeys → Drafting scenarios → Deriving test data, and scenarios appear grouped by journey as they are ready.
4. **Given** a scenario has been drafted, **when** the user opens it, **then** it shows test steps, test data fields (each marked required or optional, with no AI-invented values), and the expected result.
5. **Given** a scenario, **when** the user renames it, deletes it, edits a test data value, uses Auto-generate, or uses Clear, **then** the change is saved and shown straight away.
6. **Given** drafting fails for one journey, **when** the others finish, **then** their scenarios are shown, and the failed journey is listed with the reason.
7. **Given** at least one scenario exists, **when** the user views the Scenarios tab, **then** **Generate test cases** is enabled, even if some required fields are still blank (blank fields get default values during generation).
8. **Given** a viewer, **when** they open the Scenarios tab, **then** they can read scenarios but get no controls to change them or to start generation.

## Gaps / not built

- The happy / negative / edge type badge is hidden in the UI (kept for later use).
- There is no approve/reject status per scenario; review means renaming, deleting and editing test data only.
- Re-drafting scenarios for a journey from scratch ("regenerate") was dropped from scope.
- A journey whose drafting failed cannot be retried; it stays listed with its reason.
- Explorer's Generate tests button is shown to viewers as well; the platform refuses it when pressed.
- When Explorer is started on an application the classic engine already discovered, the classic journeys stay in place alongside Explorer's. Generating tests would likely cover both sets (inferred, not confirmed by running it).
- The **Auto-generate** button shows a static "Generating…" while busy instead of the standard trailing bouncing dots.
