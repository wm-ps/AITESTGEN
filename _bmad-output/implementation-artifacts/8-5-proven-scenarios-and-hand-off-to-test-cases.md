---
last_updated: 2026-10-27
---

# Story 8.5: Proven scenarios and hand-off to test cases

Status: done

## Story

As a member or admin,
I want Explorer to write scenarios, prove each one works, and pass only the proven ones on to test generation,
so that my test cases start from behaviour that has actually been shown to work, and possible bugs are judged by a person instead of being baked into tests.

## What it does today

- **Seven kinds of scenario.** Five are planned by AI: Getting around, Input rules, Error handling, Data shown, Saving a form. Two more are built in: **Whole journey** (an end-to-end business flow from a completed mission, built first, up to 8) and **Page quality** (checks the browser measures on each screen; skipped for applications that keep progress per login).
- **How many.** Up to 150 scenarios per run, scaled to the application's size (15 per screen, at least 10).
- **Proving.** A scenario is **proven** when it replays the same way every time and fails when its key step is removed on purpose. When the application does something different from what should happen, the scenario is kept as a **possible bug** for a person to judge. Others are dropped (with a reason) and hidden. Each scenario records where "what should happen" came from: the user or their documents, common sense, or the application itself.
- **Scenarios sub-tab.**
  - Counts: "work as they should", "possible bugs to check", "still being tried" and "from what you told Explorer".
  - Kind filter chips; scenarios grouped with "Whole journeys" first, then one group per screen.
  - Each scenario can open a **proof video**.
  - A possible bug offers **"Not a bug, keep as a test"** or **Ignore**.
- **Hand-off.** When a run finishes testing, **only proven scenarios** are passed on to the rest of the product. Each screen tested becomes a journey (with its screenshot as the step), and each whole-journey scenario becomes its own journey. Possible bugs are never passed on unless the user says "Not a bug", which sends that one on its own; "Ignore" leaves it out.
- **Generate tests.** A pulsing **Generate tests** button appears once testing has finished and at least one scenario works. It uses the same test generation as before (Story 4.2). The test Explorer already wrote and proved is used as-is if it compiles; AI writes a new one only if it doesn't.
- **Running Explorer again** replaces its own earlier results. Older results are kept for run history but are no longer current.
- **Test runs.** Scenarios for an application that keeps progress per login (saved drafts, a cart, "resume where you left off") are marked so that any run containing them runs its tests one at a time (Story 6.1).

## Acceptance criteria

1. **Given** a run reaches the testing stage, **when** scenarios are written, **then** they cover the seven kinds, within the size limits above.
2. **Given** a scenario, **when** it replays consistently and fails without its key step, **then** it is marked as working; **when** the application behaves differently from what should happen, **then** it is marked a possible bug.
3. **Given** testing has finished, **when** results are handed over, **then** only proven scenarios become journeys and scenarios in the rest of the product; possible bugs are not.
4. **Given** a possible bug, **when** the user chooses "Not a bug, keep as a test", **then** it is handed over on its own. **When** they choose Ignore, **then** it is left out.
5. **Given** at least one working scenario and testing finished, **when** the user presses Generate tests, **then** test cases are generated, reusing Explorer's proven test wherever it compiles.
6. **Given** Explorer runs again, **when** it hands over, **then** its earlier results stop being current.

## Gaps / not built

- These are produced but have no screen: the run report and its download, downloading Explorer's proven tests as a ready-to-run project, and re-writing the scenarios without exploring again.
- Whether an application "keeps progress per login" is a keyword guess from screen names; a wrong guess either slows runs or lets parallel tests interfere.
- For an application first discovered by the classic engine, the classic journeys stay active, so Generate tests would likely produce tests for both the classic journeys and Explorer's (inferred, not yet confirmed).
- Viewers see the judge and Generate tests buttons, but the platform refuses them. Viewers can, however, download Explorer's tests, run report and highlight video, which are refused to them elsewhere in the product.
