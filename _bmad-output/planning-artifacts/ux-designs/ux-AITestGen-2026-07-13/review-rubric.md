---
updated: 2026-10-27
---

> **Historical review.** This is a review of an **earlier draft** (July 2026) of the design and experience documents, written when the product was still a four-step wizard. Most of what it discusses, including the wizard, Landing, Generate Suite, the "Ready / Needs Data" filter, scenario type badges and the Inter font, no longer exists. **`DESIGN.md` and `EXPERIENCE.md` are current** and describe the shipped product. Keep this file only as a record of that review.

# Spine Pair Review — AITestGen (earlier draft)

## Overall verdict
The pair was a largely strong contract. Its tokens were thorough, its section order followed the standard shape, and its prototype-reconciliation discipline (adopted / rejected / gap) was a real strength. It was let down by one critical defect: the experience document treated the "release readiness" user journey as still open, when the PRD had removed it in full. There was also a cluster of component and state gaps. Badge, kebab menu, icon button and the top bar's click behaviour had no dedicated coverage, and the URL reachability check on Connect App had no defined state.

## 1. Flow coverage — adequate
The PRD had one live user journey (Maria reviewing discovered journeys), and it had a well-formed key flow with a named protagonist, numbered steps, a climax and a resolution.
- **Critical.** The "Devon checks release readiness" flow was framed as blocked and awaiting a product decision. The PRD had already removed it. Fix: delete it, or state plainly that it was cut and reviving it needs a new product decision.
- **High.** The URL reachability check on Connect App had no flow step, behaviour rule or error state. Fix: add a blocked-submit error state.
- **Low.** The "returning user" flow lacked an explicit climax and failure path.

## 2. Token completeness — adequate
- **Medium.** Two colour tokens were defined but never used, one duplicating another. Fix: delete them or explain them.
- **Medium.** The three accent wash colours were written as transparency values rather than plain hex, against the spec's format. Fix: note the exception or convert them.
- **Medium.** No contrast ratios were stated for the wash-plus-text pairs on badges and pills, or for white text on the accent button. Fix: state them.

## 3. Component coverage — thin
- **High.** Icon button, kebab menu and badge had visual definitions but no section in the components list and no behaviour row in the experience document. Fix: add both.
- **High.** The top bar's behaviour (brand returns to Landing; avatar opens a menu with Log out) was described only in the visual document. Fix: add a behaviour row.
- **Medium.** Discovery progress had a visual entry but its behaviour lived only in the states table. Fix: add a component row or name the states table as its home.

## 4. State coverage — adequate
- **High.** There was no state for a failed URL reachability check on Connect App.
- **Low.** No loading state was defined between starting suite generation and the result screen.
- **Low.** No field-level validation states were defined for Connect App.

## 5. Visual reference coverage — strong
All three prototypes then in the mockups folder were named and marked current or historical.
- **Low.** The documents never stated, as a standing rule, that the spec wins over the prototype on conflict. Fix: add "Spine wins on conflict."

## 6. Bloat and overspecification — adequate
- **Low.** The "what changed since the previous revision" story was retold in four sections. Fix: state it once, or drop it.

## 7. Inheritance discipline — thin
Sources resolved and glossary terms matched the PRD.
- **Critical** (same as section 1). The experience document cited a PRD user journey that the PRD no longer contained.

## 8. Shape fit — strong
Both documents followed the expected section order. Leaving out a responsive section was justified, because the product is desktop-only.

## Mechanical notes
- There were no diagrams to check.
- Cross-references between the two documents resolved, apart from the unused tokens noted in section 2.
- Frontmatter was complete and consistent across both files.
- The PRD described scenarios as two categories, while the design showed three type badges. This was noted for awareness only.
