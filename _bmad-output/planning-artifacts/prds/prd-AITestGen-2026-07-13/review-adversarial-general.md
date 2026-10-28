---
title: "Adversarial review of the July PRD, with current status"
reviewed: 2026-07-13
last updated: 2026-10-27
---

# Adversarial review of the July PRD, with current status

> **Note:** This review was written against the **July 2026 draft** of the PRD. The product has changed a lot since then: it now runs tests, self-heals them, schedules runs, and lets users author or record tests. CI/CD delivery, analytics dashboards and on-premises AI were dropped. Each finding below keeps its original point in short form, followed by its status against the product as of 2026-10-27.
>
> Status key: **Resolved** (the product now addresses it), **Obsolete** (the feature it criticised no longer exists or no longer works that way), **Still open** (the concern still applies).

The reviewer took the stance of a sceptical staff engineer. Four issues the PRD had already flagged itself were left out: non-production targeting isn't enforced, confidence scoring was cut, direct commits could overwrite, and SSO/MFA handoff was undefined.

## 1. Reviewers could only moderate journeys, not correct them
Reviewers could approve, reject, rename or delete journeys. They couldn't create a journey the AI missed, or merge, split or re-shape one, so "correct" in the vision overstated it.
**Status: Still open (partly eased).**
- Approve/reject no longer exist; journeys can be renamed or deleted.
- Merging, splitting and editing what a journey contains are still not possible.
- The gap is eased by two ways to add what Discovery missed: **Author a test case** (describe a test in plain English, against an existing or a new journey) and **Record and play**.

## 2. "Passing tests" coverage promised data the platform couldn't get
The PRD claimed coverage of passing tests, but tests were to run only in the customer's own CI, with no way to read results back.
**Status: Resolved.** Vantage now runs tests itself, on demand or on a schedule. Pass rate, failures, flaky flags and self-healing results are real data shown in the product.

## 3. No guard against destructive actions during Discovery
Discovery would click and submit anything, including "Delete account" or "Send to all customers", even in a correctly isolated test environment.
**Status: Resolved for Discovery; still open for test runs.**
- Discovery now never performs clearly destructive actions (delete, pay, transfer) and sets aside ambiguous ones (submit, approve) according to the application's safety setting.
- Test runs have no such guard. An earlier run-time restriction was removed on purpose so "Run tests" works with no setup. A generated, authored or recorded test does whatever it was written to do.

## 4. The target application's own defences may treat the crawler as an attacker
Fast, exhaustive clicking and form-filling can trip rate limits, firewalls or account lockout on shared test environments.
**Status: Still open.**
- Discovery has admin limits (time, pages, interaction level), and tests run five at a time.
- Nothing detects or backs off from throttling or lockout.
- The one related feature is Discovery's own: it logs back in when a session expires partway through.

## 5. "Nobody has to remember to document it": someone still has to re-run Discovery
Discovery is a point-in-time crawl with no automatic re-run, so the map goes stale silently.
**Status: Still open.** Schedules exist, but they run **tests only**. Discovery can't be scheduled, and the schedule dialog's wording that suggests otherwise is misleading.

## 6. Flagging "new" journeys across runs quietly needs the change detection the PRD ruled out
**Status: Obsolete.** The product does not flag journeys as "newly discovered" across runs, and change detection inside a journey is still not offered.

## 7. "Negative and edge-case coverage" can't be tested as written
There was no bar for how many or which negative cases are enough.
**Status: Still open.** Scenarios are drafted per journey with steps, test data and an expected result. The scenario-type badges (happy / negative / edge) are hidden, and there is still no measure of whether negative coverage is sufficient.

## 8. No human ever reviews the actual test logic
Approval happened at the journey label, one level above the code that runs.
**Status: Resolved (largely).**
- Before generation, reviewers see each scenario's steps, test data and expected result.
- After generation, any test's code can be viewed, and its test data edited (which rewrites that one test).
- Real runs show what each test actually does, with screenshots and traces of failures.
- Code can't be hand-edited inside Vantage.
- Self-healing is barred from changing what a test checks.

## 9. Four CI/CD providers presented as one equal effort
**Status: Obsolete.** CI/CD delivery was cut and never built. The downloadable project is the export route.

## 10. No rules for handling the sensitive application content Discovery captures
Only credentials had handling rules; screenshots and page content from apps containing customer data had none.
**Status: Still open (partly addressed).**
- All data is scoped to one organization.
- Credentials are stored encrypted and never shown in activity history.
- Deleted applications are purged automatically after the admin-set clean-up period, and activity history is deleted after 90 days.
- Admins choose which test-run screenshots are kept.
- There is still no written policy for how long Discovery screenshots and page content are kept or how they are protected.

## 11. On-premises AI quality was assumed to match hosted quality
**Status: Obsolete.** On-premises and bring-your-own AI were never built. Vantage uses one hosted AI service.

## 12. The glossary stated a guarantee ("must never run against production") that later sections walked back
**Status: Obsolete as a wording issue; the underlying risk is still open.**
- The current PRD no longer makes that claim.
- Users can still add an application with the environment set to "production", and nothing prevents Discovery or test runs against it.

## 13. The release-readiness user journey overstated what coverage analytics could show
**Status: Obsolete.** The executive dashboard and its user journey were cut. The current Overview shows pass rate, failures and test counts across applications. It makes no claim about functionality Discovery never found.

## 14. A multi-application executive dashboard built for a secondary persona
**Status: Obsolete.** That dashboard was cut. The org-wide Overview and Applications list that exist now are lightweight day-to-day views for the QA team, not an executive rollup.
