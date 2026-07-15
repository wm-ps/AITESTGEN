# Story 2.3: Discovery Stop Conditions & Completeness Status

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want a Discovery Run to stop when exploration is exhaustive or its time budget is reached, and to see clearly whether the result is complete,
so that I never mistake a partial map for a finished one.

## Acceptance Criteria

1. **Given** a running Discovery Run, **when** no new pages, actions, or state transitions are found, **then** `DiscoveryRun.status` is set to `complete`. [Source: epics.md#Story 2.3; FR-7; architecture#AD-10]
2. **Given** a running Discovery Run instead reaches its configured time budget before exhaustive traversal, **when** the time budget elapses, **then** `DiscoveryRun.status` is set to `incomplete`, and the status pill automatically transitions from "Running" to an amber "Incomplete" state — the same status-pill component, not a separate visual pattern. [Source: epics.md#Story 2.3; DESIGN.md#Components — status-pill]
3. Completeness is read directly from `DiscoveryRun.status` everywhere it's shown, never inferred from the presence or absence of other data. [Source: architecture#AD-10]

## Tasks / Subtasks

- [ ] Task 1: Replace Story 2.2's placeholder stopping cap with the real FR-7 rules (AC: 1, 2)
  - [ ] Track, per exploration iteration, whether any new page/action/state-transition was found (i.e. not already represented by an existing `Evidence` row for this run). When an iteration finds nothing new, that's exhaustive traversal
  - [ ] Compute a deadline from `Application.time_budget_minutes` (Story 1.5) and `DiscoveryRun.started_at`; check elapsed time each iteration
  - [ ] **Keep this inside the same `DiscoveryActivity` Story 2.2 built** — there's no need for a second Activity call or a Temporal-level `StartToCloseTimeout` as the primary mechanism. `DiscoveryActivity` already owns I/O (AD-2); it can check its own stop conditions each loop iteration and write the final `DiscoveryRun.status` itself before returning, exactly as it already writes `Evidence` rows incrementally. A self-checked deadline is also more graceful than relying on Temporal to hard-kill the activity mid-Playwright-action, which better satisfies NFR-2 ("complete or fail gracefully")
  - [ ] On exhaustive stop, set `DiscoveryRun.status = "complete"`; on deadline stop, set `DiscoveryRun.status = "incomplete"` — this is the one and only place either value gets written
  - [ ] Because Story 2.2 already writes each `Evidence` row as it's captured (not buffered until the end), a time-budget cutoff naturally retains whatever was captured so far — no extra "save partial results" step is needed; this is a direct consequence of 2.2's design, not new work this story has to build
- [ ] Task 2: Audit every completeness read-path to use `DiscoveryRun.status` directly (AC: 3)
  - [ ] Discovery Progress and any other surface referencing this run's completeness must query `status` directly — never infer completeness from `Evidence` row counts, elapsed time, or any other proxy. This is the literal enforcement of AD-10 ("completeness is never inferred from the presence/absence of other data"). `[UPDATED 2026-07-15: dropped the "Applications table row" surface — no Application-list view is confirmed to exist in the current IA, see Story 1.5's Task 4.]`
- [ ] Task 3: Wire the status-pill state transitions (AC: 2)
  - [ ] `Running` → `Incomplete`: reuse the exact same `status-pill` component; on transition, swap label text to "Incomplete" and recolor from `{colors.signal-wash}`/`{colors.signal}` to `{colors.warn-wash}`/`{colors.warn}` — this exact behavior is already documented in `DESIGN.md`'s `status-pill` component note, so there's nothing new to design here, only to implement
  - [ ] **`Complete` has no documented pill variant in `DESIGN.md`** — only `Running` (signal, pulsing) and the amber `Incomplete` transition are named; there is no third named color/label for a successfully-finished run. Resolved here: use `{colors.good-wash}`/`{colors.good}` (green) for `Complete`, consistent with `DESIGN.md`'s stated semantic-color rule ("Green means approved/generated/healthy"), with the pulsing dot removed once no longer "in progress." Treat this as a filled UX gap, not a literal DESIGN.md spec — flag it if a future design pass wants to formalize it
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] A Discovery Run against a small, fully-crawlable target reaches `status=complete` when no new evidence is found, with the pill showing the (gap-filled) `Complete` treatment
  - [ ] A Discovery Run against a large/slow target with a short time budget reaches `status=incomplete` before exhaustive traversal, with the pill transitioning Running → Incomplete live
  - [ ] Every surface showing run completeness reads `DiscoveryRun.status` directly (code-review-checkable, not just a runtime test)

## Dev Notes

- **This story's job is narrowly "replace the placeholder with the real thing," not "build a new mechanism from scratch."** Story 2.2 deliberately left a simple iteration-cap placeholder specifically so this story could swap in the real FR-7 logic without restructuring `DiscoveryActivity`'s loop. Read Story 2.2's Dev Notes and File List before starting Task 1.
- **AD-10 is a discipline requirement, not just a data-model one** — the failure mode it prevents is a screen quietly computing "is this run done?" from something other than `status` (e.g., "no new evidence in the last N seconds") and drifting out of sync with the authoritative field. Task 2's audit exists specifically to catch that.
- **The `Complete` pill-color gap is a real, filled ambiguity** — flagged explicitly above so it isn't mistaken for a literal `DESIGN.md` citation. If this is later formalized in a design pass, treat that as the design system catching up to an implementation decision, not this story having gotten something wrong.
- **Session-expiry (a third way a run can end) is explicitly Story 2.4's territory, not this one's.** Don't add `failed`/`session_expired` handling here — this story only implements the `complete`/`incomplete` pair.

### Project Structure Notes

- Modifies `DiscoveryActivity` (`apps/workers/discovery`, added by Story 2.1/2.2) and the Discovery Progress / Applications-table rendering (`apps/web`, from Stories 1.5/2.1). No new entities or top-level directories.
- **Depends on Stories 2.1 and 2.2 being actually implemented**, not just created — both remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3: Discovery Stop Conditions & Completeness Status]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md §4.2 — FR-7]
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
