---
title: "Reconciliation: Brief vs. PRD + Addendum — Vantage (AITestGen)"
created: 2026-07-13
updated: 2026-10-27
---

# Reconciliation: Product Brief vs. PRD + Addendum

**Documents compared:**
- the product brief and its addendum,
- the PRD,
- the PRD addendum.

All are dated 2026-10-27 and describe the product as built today.

**Result:** the brief, PRD and addendum agree. Earlier gaps between the original July brief and the July PRD were resolved when all of these documents were rewritten to describe the current product. Each item below records how it was settled.

## Former Gaps and How They Stand

1. **Merging duplicate journeys.** The brief and the PRD now both say merging, splitting and editing a journey's steps are not supported. Reviewers rename or delete journeys. Both list this under not built.
2. **Confidence and risk scoring.** The brief, the PRD and the addendum all list it as not built. The addendum explains which cheap signals exist today (health tier, scenario coverage, pass and flaky history, the server-side coverage report) and how a lightweight risk view could be added.
3. **Marking business importance.** Both documents list it as not built.
4. **Running tests automatically.** The original brief promised delivery into the customer's CI/CD pipeline. That is still not built. Automatic running is now provided inside Vantage through scheduled test runs (daily, weekly, monthly or custom), plus a downloadable project for teams who want to run tests elsewhere. Both documents agree.
5. **"Human approval before generation."** The original brief framed review as a gate. The product has no approval step: journeys and scenarios are curated by renaming, deleting and editing test data, and generation is started by the user. Both documents describe it that way.
6. **Scope beyond the original brief.** Plain-English authoring, record-and-play, test execution, self-healing, flaky flags, failure explanations, reports, emails, schedules, roles and Activity history were not in the July brief. They are now in the brief's scope and in PRD Epics 4 to 7.

## Things to Keep in Sync

- **UI copy that doesn't match behaviour.** The invite screen says invites last 7 days, but they expire after 72 hours. The schedule dialog mentions Discovery, but only test runs can be scheduled. The PRD records the real behaviour (FR-7.1.3, FR-6.8.3). Fix the copy, or update both documents if the behaviour changes.
- **Server-only capabilities** (single sign-on session reuse, MFA codes, test data pool, blocked-request answers, coverage report). These are listed as partly built or not built in both documents. Update both when screens are added.

## Persona Coverage

QA leads and teams, engineering leaders and workspace admins are each covered by PRD epics and the role table. Viewers, a read-only role added after the original brief, are described in both documents.
