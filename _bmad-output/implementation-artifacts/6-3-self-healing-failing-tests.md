---
last updated: 2026-10-27
---

# Story 6.3: Self-healing of failing tests

Status: done

## Story

As a QA lead,
I want failing tests to be repaired automatically when the cause is the test itself (for example a changed button or slow page), but never when the application is really broken,
so that my suite keeps working as the app changes, while real bugs are still reported honestly.

## What it does today

- **Automatic healing.** When a test fails during a run, Vantage tries to heal it straight away, up to a fixed limit of 2 automatic attempts.
- **How a heal works:**
  1. The AI looks at the evidence: the error, where it happened, the browser console and a screenshot.
  2. For problems finding an element, it can also inspect the live page.
  3. It makes a targeted change to the test and checks it is still valid code.
  4. It re-runs the test.
  5. It repeats until the test passes or the attempts run out.
  It stops early if the same failure keeps repeating.
- **Never hides a real bug:**
  - A failure inside a check ("assertion"), meaning the app showed the wrong result, is never healed.
  - Any proposed fix that would change what the test checks is rejected.
  - For these failures the **Retry** chip is shown disabled, with the reason.
- **Known bugs are never healed.** A test marked in its code as recording a known bug is never self-healed, because healing would rewrite away the bug it records. (Explorer does not hand its possible-bug tests over to Test cases, so in practice this is a safety net.)
- **Environment problems.** Failures caused by the environment (for example the app not loading) get one plain re-run, with no AI changes.
- **Manual retry.** On a failed test, members and admins can click **Retry** ("Retry this test with self-healing"). This uses a separate budget set by the admin's "Maximum self-heal attempts" setting (default 3), regardless of how many automatic attempts were used.
- **Status in the run:**
  - **Self-healing** pulsing status with trailing dots while a heal runs. The tooltip says whether it is an automatic or manual attempt and which attempt number.
  - **Self-healed** chip when the test failed first and then passed after healing ("Failed on first run — automatically remediated by self-healing").
  - **Heal exhausted** when the manual budget is used up ("manual triage required").
- **The fix sticks.** A successful heal becomes the test's current version. Future runs and the download use the fixed test.
- **Applies to all tests:** discovery-made (classic engine or Explorer), authored and recorded.
- **Operations can switch automatic healing off** for the whole installation (it is on by default), for example while investigating real causes. The manual **Retry** works either way.
- **Viewers** see the healing status but get no Retry.

## Acceptance criteria

1. **Given** a test fails for a non-assertion reason, **when** the run continues, **then** Vantage automatically attempts to heal it (at most 2 attempts) and re-runs it.
2. **Given** a heal makes the test pass, **when** the run detail is shown, **then** the test shows **Self-healed**, and the fixed version is used from then on.
3. **Given** a test fails inside an assertion, **when** healing is considered, **then** no heal is attempted, and Retry is shown disabled with the reason.
4. **Given** a proposed fix would change an assertion, **when** it is checked, **then** it is rejected.
5. **Given** an environment failure, **when** it is handled, **then** the test is re-run once without AI changes.
6. **Given** a failed test with manual budget left, **when** a member clicks **Retry**, **then** a manual heal runs, using the admin's maximum self-heal attempts setting.
7. **Given** the manual budget is used up, **when** the test is shown, **then** it shows **Heal exhausted**.
8. **Given** a heal is running, **when** anyone views the run, **then** the test shows a pulsing "Self-healing" status, even after a page reload.
9. **Given** a viewer, **when** they view a failed test, **then** they see status chips but no Retry.
10. **Given** a test that records a known bug, **when** it fails, **then** it is never healed.
11. **Given** operations have switched automatic healing off, **when** a test fails during a run, **then** no automatic heal is attempted, but a manual Retry still heals.

## Gaps / not built

- The automatic attempt limit (2) is fixed and not configurable.
- The automatic-healing on/off switch is a server setting only operations can change; there is no screen for it.
- When a heal is rejected, the original error message is replaced, so the run email may not show the original error for that test.
