---
title: "Quality review of the July PRD, with current status"
reviewed: 2026-07-13
last updated: 2026-10-27
---

# Quality review of the July PRD, with current status

> **Note:** This rubric review was written against the **July 2026 draft** of the PRD. That draft described a discover, review and CI/CD-delivery product with analytics dashboards. Today's Vantage runs, heals and schedules tests itself, and those dashboards and CI/CD delivery were dropped. Each finding below is summarised and given a status as of 2026-10-27: **Resolved**, **Obsolete** or **Still open**.

## Overall verdict (July)
The draft was honest about its trade-offs: it named its non-goals, deviations from the brief and unmitigated risks, and tied success metrics to specific requirements. It was weak on two things. Most requirements had no testable outcome, including the core AI journey inference and all the analytics views. And its risk section cited the wrong open-question numbers.

## Decision-readiness: strong
No findings.

## Substance over theatre: strong
- **Low:** Four of six secondary personas drove no decision. **Status: Obsolete.** The PRD was rewritten around the current users (QA and engineering teams) and the three roles: admin, member, viewer.

## Strategic coherence: strong
No findings.

## Done-ness clarity: thin
- **High:** There was no testable definition of "business language" for inferred journeys. **Status: Still open (partly addressed).**
  - Journeys are presented with plain names and business-level steps; repeated steps on the same page are merged into one business step.
  - There is still no written pass/fail bar for what counts as business language.
- **High:** The analytics and dashboard requirements (capability map, journey explorer, coverage analytics, executive dashboard) were one-line statements with no testable outcome. **Status: Obsolete.** Those views were cut. Journey detail lives on the Journeys tab, and the Overview dashboard that exists now is a different, simpler view.
- **Medium:** The review-workflow and CI/CD-delivery requirements were terse. **Status: Obsolete.** Approve/reject were removed (journeys can be renamed or deleted), and CI/CD delivery was never built.

## Scope honesty: adequate
- **High:** The open question on how SSO/MFA-protected apps hand over a signed-in session was a blocker disguised as a routine item. **Status: Still open (partly addressed).**
  - The server can reuse a saved browser session and store an MFA code seed.
  - Neither has a screen, so in practice users can add apps with a username and password or with no sign-in.

## Downstream usability: thin
- **High:** Every risk-section reference to an open question pointed one item too far. **Status: Obsolete.** The PRD has since been rewritten, so those cross-references no longer exist.

## Shape fit: strong
No findings.

## Mechanical notes
- The description of the assumptions index was out of date. **Status: Obsolete** (PRD rewritten).
- "Capability" and "Journey" were used as shorthand for the glossary terms. **Status: Obsolete.** The product uses "journey" consistently; capabilities are internal only.
- Requirement and metric IDs were contiguous. **Status: Obsolete** (no longer relevant to the current PRD).
