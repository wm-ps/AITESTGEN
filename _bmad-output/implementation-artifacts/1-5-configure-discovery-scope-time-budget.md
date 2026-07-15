# Story 1.5: Configure Discovery Scope & Time Budget

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**`[GAP — flagged 2026-07-15]`** The current reference prototype's Connect App form does not show Discovery Scope or Time Budget fields anywhere. Unlike the confirmed-cut screens (Applications list, App Overview, Dashboard, CI/CD, Settings), these fields were never explicitly identified as cut — they may simply be below the fold, in a later-added "Advanced" section, or genuinely dropped. **Do not build or drop this story on the current evidence** — re-verify against a fuller prototype export first. This story is **not** marked deferred or backlog; it needs re-verification before dev-story starts, nothing more. AC below is retained unchanged from the prior revision as the last-confirmed spec pending that check. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

## Story

As a user onboarding an Application,
I want to set a discovery scope and a maximum time budget,
so that discovery stays bounded to what I intend and within a safety cap.

## Acceptance Criteria

1. **Given** a user on the Connect App form, **when** they optionally restrict scope to specific sections/paths, and set a maximum time budget, **then** those values are saved on the `Application` record, defaulting to full-Application scope if left unspecified. [Source: epics.md#Story 1.5; FR-4; FR-5]
2. Submitting returns the user to the pipeline's Discover Journeys step, where the new Application's discovery begins. [Source: epics.md#Story 1.5]
3. The breadcrumb/context rule is honored: Connect App carries no Application-name breadcrumb until submission (no Application exists yet). [Source: epics.md#Story 1.5; UX-DR16]

## Tasks / Subtasks

- [ ] Task 1: Extend the `Application` entity for scope, time budget, and onboarding status (AC: 1, 2)
  - [ ] Add `discovery_scope` (nullable — a list/text of path patterns; PRD only says "limit to specific sections/paths," no fixed shape is specified, so don't over-design a structured schema beyond a simple list of strings) to `Application`
  - [ ] Add `time_budget_minutes` (required, positive integer) — minutes is a reasonable default unit; neither PRD nor architecture fixes the unit or a numeric ceiling, so don't invent a maximum bound beyond "must be positive"
  - [ ] Add `status` (`"draft" | "ready"`) to `Application`, defaulting to `draft` — Story 1.3 creates the row in `draft` status at wizard step 1; this story is what flips it to `ready` once the wizard completes. This closes the progressive-creation design started in Story 1.3 (the record exists from step 1 onward, filled in incrementally)
  - [ ] Alembic migration for the new columns
- [ ] Task 2: Build the wizard's final-step endpoint (AC: 1, 2)
  - [ ] A PATCH-style endpoint on the existing `Application` (created in Story 1.3), Organization-scoped via Story 1.2's middleware, accepting optional `discovery_scope` and required `time_budget_minutes`
  - [ ] On success, set `Application.status = "ready"`
  - [ ] Validate `time_budget_minutes > 0`; leave `discovery_scope` unset/null when the user doesn't supply one — that null is exactly what "defaults to full-Application scope" means downstream (Epic 2's `DiscoveryActivity` interprets a null scope as unrestricted)
- [ ] Task 3: Add scope/time-budget fields to the Connect App form (AC: 1, 2, 3) — **`[GAP — 2026-07-15]` per the banner above, re-verify these fields' actual presence/placement before building; the below is last-confirmed spec, not a re-confirmed one**
  - [ ] Optional scope input (e.g. a small repeatable list of path patterns) and a required time-budget input, as part of the single Connect App form (Story 1.3/1.4) — **not** a separate wizard step; the 3-step wizard this story originally described no longer exists (see Story 1.3's 2026-07-15 update)
  - [ ] On submit, call Task 2's endpoint as part of the same Connect App submission, then navigate to the Discover Journeys pipeline step (Story 2.1), not an Applications list
  - [ ] No Application-name breadcrumb until submission completes, consistent with Story 1.3 (UX-DR16)
- [ ] Task 4: `[SUPERSEDED 2026-07-15]` — building a standalone Applications list/table is no longer applicable; Home (Story 1.2) is a static 3-card landing, not a data-driven Application list, and "Managed Applications" re-enters an existing Application's pipeline directly rather than showing a table. **`[GAP]`** whether any Application-list view exists anywhere in the new IA is unconfirmed — do not build one speculatively; if Epic 2/3 stories need a status surface, revisit then.
  - [ ] The hero-stat strip and full Applications-table polish (UX-DR9) depend on data (Discovery Runs, coverage) that doesn't exist until later epics — out of scope here; keep this table minimal and honest about what data actually exists at this point
- [ ] Task 5: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] Completing step 3 with only a time budget (scope left blank) saves `discovery_scope=null` and the required `time_budget_minutes`
  - [ ] `Application.status` flips `draft` → `ready`, and the row appears in the Applications list
  - [ ] Steps 1 and 2 render as one-line summaries and are not clickable
  - [ ] No breadcrumb renders anywhere in the wizard flow

## Dev Notes

- **This story is the last one in Epic 1 and closes its stated goal**: "A user can sign in, and onboard an Application ... — ready for its first Discovery Run." Note precisely what that means and doesn't mean: this story's job stops at the Application appearing `ready` in the list. Actually **starting** a Discovery Run against it is Epic 2 Story 2.1's job — don't reach ahead into that story's scope (e.g., don't add a "Start Discovery" button here just because it would be a natural next click; Story 2.1 owns that).
- **No UX-specified status-pill variant exists for onboarding-complete.** This is a real gap between the UX spine (which only names Discovery Run–tied pill states) and this story's need to show *something* for a freshly onboarded Application. Resolved above: render plainly, don't invent a color/variant.
- **`discovery_scope`'s shape is intentionally left loose** (a simple list of path-pattern strings) because neither PRD FR-4 nor the Architecture Spine fixes a structured format — don't build a URL-pattern DSL, glob validator, or similar unrequested machinery for this.
- **Progressive Application creation, completed:** Story 1.3 created the row (`status=draft`) at step 1; Story 1.4 updated `auth_method`/`secret_ref` at step 2; this story updates scope/time-budget and flips `status=ready` at step 3. All three stories are patching the *same* row across the wizard's lifetime, not assembling a client-side draft that gets submitted once at the end — keep that consistent here.

### Project Structure Notes

- Extends `Application` (Stories 1.3, 1.4) and the wizard/stepper UI already built by those stories; adds the first real Applications-list rendering to `apps/web`. No new top-level directories.
- **Depends on Stories 1.1–1.4 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit. Verify those are built first.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5: Configure Discovery Scope & Time Budget; #Epic 1: Foundation, Auth & Application Onboarding]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-4, FR-5]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — status-pill (documented variants only)]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Component Patterns — Stepper; #Information Architecture — breadcrumb rule]
- [Source: _bmad-output/implementation-artifacts/1-3-onboard-an-application-basic-details.md — progressive Application creation, established at step 1]
- [Source: _bmad-output/implementation-artifacts/1-4-configure-application-authentication-method.md — step 2 of the same progressive record]

## Previous Story Intelligence

Stories 1.1–1.4 remain `ready-for-dev` (not `done`) as of this story's creation, with only the initial BMad-tooling commit in git. The carry-forward that matters here isn't code yet — it's the data-model contract established across 1.3 and 1.4: `Application` is created once (1.3) and progressively updated (1.4, then this story), never rebuilt from a client-side draft at the end. Verify 1.1–1.4 are actually implemented before starting this story, and check their File Lists for the exact `Application` schema/endpoint shapes already in place.

## Latest Technical Notes

No new library decisions — this story only extends the stack already established by Stories 1.1–1.4.

## Project Context Reference

No `project-context.md` exists yet in this repository. With Epic 1 now fully spec'd (Stories 1.1–1.5), this is a good point to run `bmad-generate-project-context` once the epic is actually implemented, so Epic 2's stories can reference real code instead of re-deriving conventions from these planning docs each time.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
