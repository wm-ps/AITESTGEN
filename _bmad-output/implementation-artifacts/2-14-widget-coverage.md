---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.14: Widget Coverage — Tabs, Dialogs, Multi-Window, File Upload

*Added per `sprint-change-proposal-2026-07-29.md`.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to correctly handle tabs, modals, new browser windows, and file uploads across any frontend framework,
so that discovery doesn't silently skip or get stranded by common enterprise UI patterns.

## Acceptance Criteria

1. **Given** a tab-group widget (ARIA `role="tablist"`/`"tab"`, or an equivalent framework-rendered pattern), **when** detected, **then** each tab is a Tier-1 candidate action (Story 2.11) whose resulting content is observed and fingerprinted as its own state (or VARIANT of the current one) via Story 2.10's State Identity Engine. [Source: epics.md#Story 2.14; FR-41]
2. **Given** an action opens a dialog/modal/popup, **when** its contents are observed, **then** they are fingerprinted as a nested state the same way as a full page, even though the URL/route may not change; the dialog's own close action (Escape/"X"/Cancel) is reliably detected and exercised to safely return to the underlying page state before continuing exploration. [Source: FR-41]
3. **Given** an action opens a new browser tab/window, **when** it is same-origin and in-scope, **then** it is followed and explored as a related sub-flow, linked back to the opening action; **when** it is cross-origin or out-of-scope, **then** it is flagged and deferred, and focus returns to the original tab to continue exploration there. [Source: FR-41]
4. **Given** a `type="file"` input, **when** encountered, **then** it is routed to the Data Resolver (Story 2.13) for a safe generated placeholder file, reused across upload fields and logged the same as any synthetic value. [Source: FR-41]
5. **Given** an element with no standard ARIA role, **when** detected, **then** structural heuristics (tag type, class-name patterns, visual/positional cues) apply as a fallback, and such elements are flagged with lower confidence for later review rather than silently trusted. [Source: FR-41]

## Tasks / Subtasks

- [ ] Task 1: Build ARIA-first widget detection (AC: 1, 2, 5)
  - [ ] New module in `apps/workers/discovery` (e.g. `widgets.py`) that inspects the accessibility tree first for each observed interactive element: `role="tab"`/`"tablist"` → tab handling (Task 2); an element that triggers an overlay (detect via a new element appearing with `role="dialog"`/`aria-modal="true"`, or a lower-confidence structural signal — a newly-visible high-z-index container) → dialog handling (Task 3); no standard role found → structural-heuristic fallback (Task 5), tagged with a `confidence: low` marker persisted alongside the resulting `Action`/`Component` row
- [ ] Task 2: Tab handling (AC: 1)
  - [ ] Each detected tab becomes a Tier-1 candidate action (tag via Story 2.11's tiering) — switching it and observing the revealed content through Story 2.10's State Identity Engine, exactly as any other in-page action
- [ ] Task 3: Dialog/modal handling (AC: 2)
  - [ ] On detecting an overlay opened by an action, treat its contents as a nested state: run the Runtime Observer and Story 2.10's classification against it as if it were a page
  - [ ] Detect and exercise the overlay's close mechanism (try, in order: an Escape keypress, an element with an accessible name matching "Close"/"Cancel"/"X", or a role-based close button) before continuing — losing track of how to close a dialog must not strand the crawl; add a bounded retry/fallback (e.g. force-navigate back to the pre-dialog URL) if no close mechanism is found within a small number of attempts
- [ ] Task 4: Multi-tab/window handling (AC: 3)
  - [ ] Listen for Playwright's new-page/popup event on any action execution
  - [ ] Same-origin + in-scope (matches the Application's base URL origin) → follow it as a linked sub-flow, recording the link back to the opening `Action`
  - [ ] Cross-origin or out-of-scope → do not follow; flag/log it (reuse the Story 2.15 Blocked Frontier's "deferred" shape, or a simpler flagged-log entry if 2.15 hasn't landed yet) and return focus to the original page/tab
- [ ] Task 5: File-upload routing (AC: 4)
  - [ ] Detect `input[type="file"]` elements during form/field enumeration
  - [ ] Route to Story 2.13's Data Resolver, which generates/reuses a small set of safe placeholder files (a minimal dummy image and PDF are sufficient defaults) and logs the choice via `SyntheticDataEntry` with `is_placeholder_file=true`
- [ ] Task 6: Structural-heuristic fallback (AC: 5)
  - [ ] For elements with no standard ARIA role, apply simple structural heuristics (tag type — `button`/clickable `div`; class-name patterns matching common component-library conventions; visual/positional cues) and mark the resulting `Action`/`Component` with a low-confidence flag so it can be surfaced for review rather than silently trusted at full fidelity
- [ ] Task 7: Verify end-to-end (AC: 1-5)
  - [ ] A tab-group widget's tabs are each explored and fingerprinted as distinct/VARIANT states
  - [ ] A modal opened by an action is observed as a nested state, and its close action reliably returns the crawl to the underlying page
  - [ ] A same-origin popup is followed and linked back to its opening action; a cross-origin popup is deferred/flagged and focus returns to the original tab
  - [ ] A file-upload field receives a placeholder file and the choice is logged
  - [ ] An element with no ARIA role still gets an `Action`/`Component` row, flagged low-confidence

## Dev Notes

- **Framework independence is the whole point of the ARIA-first approach** — a properly built React/Angular/Vue/design-system component exposes standard ARIA roles regardless of framework; only low-code-generated or legacy markup typically lacks them. Do not special-case any specific frontend framework's internals anywhere in this story's code.
- **Dialog close-detection is the highest-risk piece of this story** — an undetected/failed close leaves the crawl stranded inside a dialog for the rest of the run. Build the bounded-retry/fallback described in Task 3 rather than assuming the first close attempt always works.
- **File-upload placeholders are reused, not regenerated per field** — generate a small, fixed set once per Discovery Run (per Section 13.4 of the source design document) and reuse them across every upload field encountered, rather than creating a new file per occurrence.

### Project Structure Notes

- Adds a new `widgets.py` module to `apps/workers/discovery`. No new domain entities beyond what Story 2.13 (`SyntheticDataEntry`) and Story 2.15 (`BlockedTask`, for cross-origin-window deferrals) already introduce.
- Depends on Story 2.10 (State Identity Engine, for fingerprinting dialog/tab content), Story 2.11 (tiering, for tab actions), and Story 2.13 (Data Resolver, for file uploads).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.14]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Section 13 of the source design document]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the existing form/action capture this story extends with widget-specific handling]

## Previous Story Intelligence

Story 2.2's crawler already captures generic `Action`/`Form` rows via label/selector-shape grouping (representative-action sampling) — this story's tab/dialog/file-upload handling should extend that same capture path with widget-specific branches, not build a parallel capture mechanism.

## Latest Technical Notes

Playwright Python 1.57+ (architecture-pinned) supports new-page/popup event listening and accessibility-tree queries (`page.accessibility.snapshot()` or ARIA-role locators) needed here — verify the exact current API surface at implementation time.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
