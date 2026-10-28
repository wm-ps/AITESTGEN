---
title: "Change record — Cut full regeneration on request (2026-07-27)"
status: approved
created: 2026-07-27
last updated: 2026-10-27
---

# Change record: Cut full regeneration on request (2026-07-27)

## What was proposed and why

The plan included a "regenerate" action. A user could ask Vantage to throw away a journey's scenarios and tests and write them again from scratch. Product chose not to offer it in the first release. This was a scope decision, not a technical blocker.

Investigation found the feature had never been built, although progress tracking claimed it was done. That work had actually been the "generate tests" story. Nothing user-facing needed removing. The internal versioning that protects against double-clicks and repeat requests stayed, because test generation relies on it.

## What was decided

- Regeneration on request was cut in full, not deferred.
- The only way left to change a journey's generated content was to delete the journey.
- The story slot was later reused for "Download a generated test project" (see the 2026-07-27 follow-up record).

## Where it stands today (2026-10-27)

**Still cut. There is no "regenerate this journey from scratch" action.** Narrower ways to redo work have been added since:

- **Retry Generation.** On the test-case progress screen, journeys whose generation failed or was terminated can be retried. Journeys whose scenario writing failed are listed with the reason, but cannot be retried.
- **Edit test data.** Changing a scenario's or test's test data rewrites that one test to match.
- **Self-healing.** Failing tests are repaired automatically, or on request with Retry, without ever changing what the test checks.
