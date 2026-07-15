# Story 2.3: Discovery Completion `[RENAMED 2026-07-15, was "Discovery Stop Conditions & Completeness Status"]`

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Rewritten 2026-07-15 — FR-5 (time budget) removed in full, along with FR-4 (discovery scope). There is no time-budget stop condition, no `incomplete` status, and no accompanying amber status-pill state. A Discovery Run only ever completes via exhaustive traversal or fails (Story 2.4). This is an accepted-risk tradeoff — see PRD §12 Risk item 7 (no safety cap against unbounded exploration; an Application with infinite pagination or similar could run indefinitely). Filename retained for continuity.*

## Story

As a user,
I want a Discovery Run to stop once exploration is exhaustive,
so that I know the map reflects everything discovery found.

## Acceptance Criteria

1. **Given** a running Discovery Run, **when** no new pages, actions, or state transitions are found, **then** `DiscoveryRun.status` is set to `complete`. [Source: epics.md#Story 2.3; FR-7; architecture#AD-10]
2. Completeness is read directly from `DiscoveryRun.status` everywhere it's shown, never inferred from the presence or absence of other data. [Source: architecture#AD-10]

## Tasks / Subtasks

- [ ] Task 1: Replace Story 2.2's placeholder stopping cap with the real FR-7 rule (AC: 1)
  - [ ] Track, per exploration iteration, whether any new page/action/state-transition was found (i.e. not already represented by an existing `Evidence` row for this run). When an iteration finds nothing new, that's exhaustive traversal — the only stop condition
  - [ ] **Keep this inside the same `DiscoveryActivity` Story 2.2 built** — there's no need for a second Activity call. `DiscoveryActivity` already owns I/O (AD-2); it can check this stop condition each loop iteration and write the final `DiscoveryRun.status` itself before returning, exactly as it already writes `Evidence` rows incrementally
  - [ ] On exhaustive stop, set `DiscoveryRun.status = "complete"` — this is the one and only place that value gets written
  - [ ] **`[RESOLVED 2026-07-15]` No time-budget cutoff exists.** An earlier draft of this story computed a deadline from `Application.time_budget_minutes` and wrote `status="incomplete"` on timeout — both the field and the status value are gone (FR-5 removed). Do not build a deadline check of any kind here; Story 2.2's placeholder iteration-cap is test-only scaffolding, not a product feature to formalize
- [ ] Task 2: Audit every completeness read-path to use `DiscoveryRun.status` directly (AC: 2)
  - [ ] Discovery Progress and any other surface referencing this run's completeness must query `status` directly — never infer completeness from `Evidence` row counts, elapsed time, or any other proxy. This is the literal enforcement of AD-10 ("completeness is never inferred from the presence/absence of other data")
- [ ] Task 3: Wire the status-pill's `Complete` state (AC: 1)
  - [ ] **`Complete` has no documented pill variant in `DESIGN.md`** — only `Running` (signal, pulsing) is named. Resolved here: use `{colors.good-wash}`/`{colors.good}` (green) for `Complete`, consistent with `DESIGN.md`'s stated semantic-color rule ("Green means approved/generated/healthy"), with the pulsing dot removed once no longer "in progress." Treat this as a filled UX gap, not a literal DESIGN.md spec — flag it if a future design pass wants to formalize it
  - [ ] **`[RESOLVED 2026-07-15]` No `Incomplete` state to build.** An earlier draft specified a `Running` → `Incomplete` (amber) transition on time-budget cutoff, reusing `DESIGN.md`'s documented amber note — that note describes a state this pill no longer has. The only transition is `Running` → `Complete`
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] A Discovery Run against a small, fully-crawlable target reaches `status=complete` when no new evidence is found, with the pill showing the (gap-filled) `Complete` treatment
  - [ ] Every surface showing run completeness reads `DiscoveryRun.status` directly (code-review-checkable, not just a runtime test)
  - [ ] No code path anywhere computes or displays an `incomplete` state — a deliberate negative check, not just a positive functional test

## Dev Notes

- **This story's job is narrowly "replace the placeholder with the real thing," not "build a new mechanism from scratch."** Story 2.2 deliberately left a simple iteration-cap placeholder specifically so this story could swap in the real FR-7 logic without restructuring `DiscoveryActivity`'s loop. Read Story 2.2's Dev Notes and File List before starting Task 1.
- **AD-10 is a discipline requirement, not just a data-model one** — the failure mode it prevents is a screen quietly computing "is this run done?" from something other than `status` (e.g., "no new evidence in the last N seconds") and drifting out of sync with the authoritative field. Task 2's audit exists specifically to catch that.
- **The `Complete` pill-color gap is a real, filled ambiguity** — flagged explicitly above so it isn't mistaken for a literal `DESIGN.md` citation. If this is later formalized in a design pass, treat that as the design system catching up to an implementation decision, not this story having gotten something wrong.
- **Session-expiry (the only other way a run can end) is explicitly Story 2.4's territory, not this one's.** Don't add `failed`/`session_expired` handling here — this story only implements the `complete` transition.
- **`[RESOLVED 2026-07-15]` No safety cap against unbounded exploration exists, by explicit product decision.** An Application with infinite pagination, calendar "next" links, or another unbounded-traversal pattern could cause this story's exhaustive-traversal check to never fire. This is an accepted risk (PRD §12 item 7), not something to silently work around with a hidden iteration cap — if a future revision reintroduces some form of safety cap, that's a product decision to make explicitly, not an implementation detail to infer from this story's notes.

### Project Structure Notes

- Modifies `DiscoveryActivity` (`apps/workers/discovery`, added by Story 2.1/2.2) and the Discovery Progress status-pill rendering (`apps/web`, from Story 2.1). No new entities or top-level directories.
- **Depends on Stories 2.1 and 2.2 being actually implemented**, not just created — both remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: Discovery Completion]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md §4.2 — FR-7; §12 Risk item 7]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-10 — Discovery Run completeness as a first-class status]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — status-pill]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the placeholder stopping cap this story replaces]

## Previous Story Intelligence

Stories 2.1 and 2.2 remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once 2.2 is implemented, check its File List for `DiscoveryActivity`'s exact loop structure and placeholder-cap implementation before modifying it here — this story edits that same function rather than adding a parallel one.

## Latest Technical Notes

No new library decisions — this story only extends `DiscoveryActivity`'s existing logic and Playwright/Temporal usage from Stories 2.1/2.2.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
