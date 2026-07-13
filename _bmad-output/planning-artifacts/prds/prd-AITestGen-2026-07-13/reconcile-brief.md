---
title: "Reconciliation: Brief vs. PRD+Addendum — Application Intelligence Platform V1"
created: 2026-07-13
---

# Reconciliation: Product Brief vs. PRD + Addendum

**Inputs compared:**
- Brief: `_bmad-output/planning-artifacts/briefs/brief-AITestGen-2026-07-12/brief.md`
- PRD: `_bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md`
- Addendum: `_bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/addendum.md`

Known/pre-flagged deviation (not re-reported as new, but audited for accuracy below): PRD §5 and §9 cut all confidence/risk scoring, which the brief names as a V1 outcome (Solution §, Scope §). **Audit finding on this known item is included as Gap 2 below**, since the PRD's stated justification for the cut is incomplete relative to what the brief actually specified.

## Gaps Found

**Gap 1 — Silent, unflagged reversal of "merge duplicates" from the human review workflow (contradiction).**
Brief, "The Solution" (¶3, line 32): the reviewer "confirms journeys, renames what the AI labeled awkwardly, **merges duplicates**, marks what matters most to the business" — merging is presented as a normal, expected review action. PRD §4.4 FR-13 "Out of Scope" explicitly states "Merging two discovered Journeys, splitting one into two... are not supported in V1," and PRD's own UJ-1 (§2.3) rewrites the analogous brief scenario to swap "merges duplicates" for "deletes two low-value duplicates" — i.e., the persona narrative was edited to paper over the cut. Unlike the confidence-scoring cut, this deviation has no `[NOTE FOR PM]` callout, no §9 Assumptions Index entry, and isn't listed in the top-level §5 Non-Goals — it's buried in a feature-level "Out of Scope" line with no sign-off flag. This is a second unflagged scope reversal riding on the coattails of the one everybody already knows about.

**Gap 2 — The known confidence/risk-scoring cut is over-justified: two of its four inputs don't need telemetry.**
Brief Scope (line 70): the risk/confidence scorecard is "based on runtime signals only — journey complexity, usage, error rates, and test-coverage gaps." PRD §5 justifies cutting the *entire* scorecard because "usage/error-rate signals require a real telemetry feed V1 doesn't have." That reasoning only applies to 2 of the 4 named inputs. "Journey complexity" is derivable from discovery-run data V1 already captures (FR-6: pages/actions/state transitions per Journey), and "test-coverage gaps" is exactly what FR-24 Coverage Analytics already computes. The addendum partially self-corrects for the *per-Journey confidence score* ("does not strictly require a production feed... could be computed purely from discovery-time signals") but never revisits the scorecard's complexity/coverage-gap dimensions with the same logic — so the PRD's write-up of "why it was cut" is accurate for usage/error-rate but incomplete/overbroad as a justification for cutting the whole scorecard.

**Gap 3 — "Marks what matters most to the business" (reviewer prioritization) dropped with no FR and no acknowledgment.**
Brief, "The Solution" (line 32), same sentence as Gap 1: reviewers are expected to "mark what matters most to the business" during triage — a lightweight prioritization/importance-flagging action, distinct from approve/reject/rename/delete. No FR in §4.4 (FR-9–FR-15) covers this, and it isn't listed as a Non-Goal in §5, so it reads as a silent omission rather than a decision. Notably, PRD's own Risk Register item 3 (§12) independently worries that "reviewers triaging a large discovery output have no prioritization aid" — the PRD identifies the resulting risk without connecting it back to the brief capability that would have addressed it.

**Gap 4 — CI/CD delivery no longer guarantees tests "run automatically as part of standard regression" (Scope-section commitment narrowed without deviation parity).**
Brief Scope (line 69) commits, as an explicit "In V1" bullet: integration into the customer's CI/CD system "so tests run automatically as part of standard regression." PRD FR-21 delivers only "instructions/a template for the customer to manually wire" tests in, with automated wiring marked `[NON-GOAL for MVP]`. This is disclosed in §5 Non-Goals, so it's less buried than Gap 1 — but it never gets the explicit "deviation from approved brief, flag for sign-off" treatment that confidence-scoring received in §9, even though it directly contradicts a brief Scope-section outcome ("run automatically") rather than a softer aspiration. Net effect: without manual customer follow-through, exported tests do not run automatically — the brief's stated V1 outcome isn't actually met by FR-19–FR-21 alone.

**Gap 5 (minor) — "System of record" / internal-initiative framing tone is thinned, not dropped.**
Brief Executive Summary frames V1 explicitly as one step toward a "system of record for application intelligence... a destination earned through V1 proving itself in real pilots, not a claim made in advance of it," and notes the platform is "built as an internal enterprise initiative aimed at an external market." PRD §1 Vision keeps the roadmap-credibility framing ("wins pilots on... a credible roadmap") but drops the "internal enterprise initiative aimed at an external market" detail entirely and softens "system of record" to background context in the addendum only. Low materiality (no FR/scope impact) — flagged for completeness since the task asked about tone/framing flattening, but this is the weakest of the five gaps.

## Persona Coverage Check (no material gap beyond above)
Engineering Leader and QA Director JTBDs are well-served by FR-9–FR-25 and UJ-1/UJ-2. Secondary personas (CTO, Product Owner, Architect, Test Teams) are explicitly scoped by the brief itself as "real future users, not the primary V1 design target" — the PRD's treatment (§2.1, listed but not FR-mapped) is consistent with that, not a gap.
