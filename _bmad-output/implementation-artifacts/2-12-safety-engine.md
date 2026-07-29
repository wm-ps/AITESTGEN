---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.12: Safety Engine — Action Classification & Post-Action Verification

*Added per `sprint-change-proposal-2026-07-29.md`. `[REVERSES PRD §12 Risk item 6's prior "accepted risk, no guardrail" decision — flagged for explicit Product Manager sign-off before this story moves past `backlog`/`ready-for-dev`.]`*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to never perform a clearly destructive action and to defer ambiguous ones for explicit authorization,
so that discovery can't cause irreversible side effects in the target environment.

## Acceptance Criteria

1. **Given** a candidate action, **when** classified, **then** it is Safe (View/Expand/Navigate/Filter/Search/Pagination — executed automatically), Clearly Destructive (Delete/Remove/Terminate/Transfer/Payment — never executed), or Ambiguous/state-changing (Submit/Approve/Reject/Save/Confirm/Proceed — deferred to the Blocked Frontier, Story 2.15, not guessed). [Source: epics.md#Story 2.12; FR-39; architecture#AD-19]
2. Classification is verb/pattern-based (a known-safe list, a known-destructive list) with an AI-assisted opinion consulted only for ambiguous language given page context; the Safety Engine owns the final verdict — the AI's opinion is supporting evidence, never authoritative. [Source: FR-39]
3. **Given** genuine uncertainty even after the AI-assisted opinion, **when** the Safety Engine can't confidently classify Safe, **then** it defaults to DEFER, never EXECUTE. [Source: FR-39]
4. **Given** a Safe action just executed, **when** a lightweight before/after indicator comparison (record count, status field) shows an unexpected change, **then** it is flagged as a safety-classification anomaly in the end-of-run report — visibility only, does not block the crawl. [Source: FR-39]
5. The Safety Engine's classification runs before the Data Resolver is consulted for the same action — a Clearly Destructive action never reaches the Data Resolver at all. [Source: architecture#AD-19]

## Tasks / Subtasks

- [ ] Task 1: Build the verb/pattern classifier (AC: 1, 2)
  - [ ] New module in `apps/workers/discovery` (e.g. `safety_engine.py`) with three lookup lists (Safe, Clearly Destructive, Ambiguous) matched against an action's accessible name/label — start from the PRD's named examples (View/Open/Expand/Collapse/Navigate/Tab/Pagination/Search/Filter → Safe; Delete/Remove/Terminate/Transfer/Payment → Destructive; Submit/Approve/Reject/Save/Confirm/Proceed → Ambiguous) and treat anything matching none of the three as Ambiguous by default (conservative), never as Safe by default
  - [ ] For an Ambiguous match, optionally consult the `AIProvider` port (AD-3) with the action's label + surrounding page context for a supporting classification opinion; the verdict returned by this module is always the Safety Engine's own, informed but not overridden by the AI call
- [ ] Task 2: Wire the conservative-default and DEFER path (AC: 3, 5)
  - [ ] The Safety Engine's public interface returns exactly one of `SAFE | DESTRUCTIVE | DEFER` — no fourth value, no "unknown" passed further downstream
  - [ ] Wire this as the Planner's (Story 2.11) safety question, called before the Data Resolver (Story 2.13) question, per AD-19 — a `DESTRUCTIVE` verdict short-circuits the Planner's decision to SKIP without consulting the Data Resolver at all
- [ ] Task 3: Build post-action verification (AC: 4)
  - [ ] Before executing a Safe action, capture a lightweight "before" snapshot of key indicators already available from the Runtime Observer (e.g. a visible record count, a status field's text) — reuse existing Observer capture, don't build a new capture mechanism
  - [ ] After execution, compare against an "after" snapshot; an unexpected change (e.g. record count changed when the action's label implied a read-only view) writes a flagged anomaly entry to the end-of-run report — this is visibility-only and must never change the Execution Decision or block the crawl
- [ ] Task 4: Verify end-to-end (AC: 1-5)
  - [ ] A "Delete" button anywhere in a test target is never clicked, regardless of page context
  - [ ] A "Submit"/"Approve" action is deferred (verify it reaches Story 2.15's Blocked Frontier once that story exists, or a stub queue otherwise) rather than executed
  - [ ] A genuinely unclassifiable verb (not in any of the three lists) defaults to DEFER, not EXECUTE
  - [ ] A before/after mismatch on a Safe action's execution produces a flagged anomaly entry, and the crawl continues regardless

## Dev Notes

- **`[FLAGGED FOR SIGN-OFF]` This story reverses PRD §12 Risk item 6's explicit "accepted risk — no platform-side guardrail is built in V1, by explicit decision" statement.** That decision was made deliberately at PRD-finalization time; building this story means someone with authority over that PRD needs to explicitly re-confirm the reversal before implementation starts, not just inherit it silently via a backlog addition. See `sprint-change-proposal-2026-07-29.md` §5 for the full flag.
- **Residual risk unaffected**: this story does not verify the target environment is actually non-production (PRD Open Question 3, unchanged) — it narrows *what* the crawler is willing to do regardless of environment, it does not verify *where* it's running. Do not conflate the two in implementation or in any UI copy describing this feature.
- **Conservative-by-default is the single most important behavior here** — an action whose verb doesn't clearly match any of the three lists must default to DEFER, never to SAFE. Getting this backwards defeats the entire point of the story.
- **Post-action verification is deliberately non-blocking (V1 scope)** — do not be tempted to add an auto-rollback or auto-halt on anomaly detection; the PRD/architecture explicitly scope this as visibility-only.

### Project Structure Notes

- Adds a new `safety_engine.py` module to `apps/workers/discovery`. No new domain entities beyond what Story 2.15 (Blocked Frontier) needs for the DEFER destination. No new top-level directories.
- Depends on Story 2.11's Planner (this story is one of its five specialist questions) and, for the DEFER path, Story 2.15's `BlockedTask` entity.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.12]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Section 11 of the source design document; §5 Implementation Handoff's sign-off flag]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md §12 Risk item 6 — the reversed decision]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-3, #AD-19]

## Previous Story Intelligence

No prior story in this codebase performs any action-safety classification — Story 2.2's crawler currently exercises whatever actions it finds (bounded only by the per-page action-label cap, AD-15). This is genuinely new capability, not a rework of existing logic.

## Latest Technical Notes

No new library decisions. AI-assisted ambiguous-verb classification reuses the existing `AIProvider` port/`HostedAIProvider` client.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
