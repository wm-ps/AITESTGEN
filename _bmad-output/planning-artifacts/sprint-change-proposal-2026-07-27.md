# Sprint Change Proposal — 2026-07-27

## Cut Story 4.3 (Full Regeneration of Test Assets on Request) — removed in full, not deferred

## 1. Issue Summary

Harsha has decided Story 4.3 / FR-18 ("Full Regeneration of Test Assets on Request" — a customer-triggered
full regeneration of a Journey's Scenarios and Test Assets) is **not in scope for V1**. This is a deliberate
product-scope decision, not a technical blocker — treat it the same way FR-10 (Approve), FR-11 (Reject), and
FR-28 (Edit a Journey) were cut on 2026-07-15: **removed in full**, no parked-for-later framing.

**Investigation finding, worth surfacing before cutting anything:** `sprint-status.yaml` and commit `6df2663`
("4.3 has been completed.") suggest Story 4.3 was implemented. It was not. That commit actually built **Story
4.2** (the `TestSuite`/`TestAsset` domain entities, `GenerateSuite`/`TestSuiteResults` screens,
`SuiteGenerationWorkflow`) — the commit message conflated the two. A direct search of `apps/api`, `apps/web`,
and `apps/workers/generation` turns up:
- **No regenerate-trigger endpoint** in `apps/api` (Story 4.3 Task 1 — never built)
- **No "Regenerate" UI control** anywhere in `apps/web` (Story 4.3 Task 3 — never built)
- **No code path that ever increments `Journey.attempt`** beyond its default of `1` — the one thing that would
  actually invoke a regeneration

So there is effectively **no feature code to remove**. What does exist is the `attempt`/`current`/
`generation_run_id` versioning scaffold on `Journey`/`Scenario`/`TestSuite`/`TestAsset` — but that scaffold is
genuinely owned by **Stories 4.1 and 4.2** (it's what makes their own idempotent re-trigger/double-click
protection work, per AD-9) and one test in
`apps/workers/generation/tests/test_playwright_generation_activity.py` exercises `EnsureTestSuiteActivity`'s
real supersede logic by manually bumping `journey.attempt` to simulate a future regeneration. Removing that
scaffold would require reopening already-implemented (`review`-status) Story 4.2 code for no reason — it's not
"4.3 code," it's 4.1/4.2 infrastructure that happens to be forward-compatible with a regeneration feature that
was never built and is now being cut. **Recommendation: leave the domain scaffold and the test in place**, and
only clean up the handful of comments/docstrings that narrate "Story 4.3" as if it's a committed feature.

## 2. Impact Analysis

### Epic Impact
- **Epic 4 (Scenario & Playwright Test Generation)**: narrows from 3 stories to 2 (4.1, 4.2). Epic 4's
  description line ("...regenerable from scratch on request") is no longer true and needs rewording. No other
  epic depends on Story 4.3 — nothing downstream references it as a prerequisite.
- **No epic becomes obsolete, no new epic is needed, no resequencing required.**

### Artifact Conflicts
- **PRD**: FR-18 (§4.5) needs to be cut, following this document's own established convention (see FR-10/11/28)
  — retained inline, marked `[CUT]`, not silently deleted. §5 Non-Goals' "No runtime drift/change detection"
  bullet currently ends with "...only regenerate it from scratch on request" — that clause is no longer true
  and needs rewording (V1 now has *no* mechanism to refresh a Journey's coverage at all once generated, which
  is itself worth stating plainly as the accepted consequence). §6.1 MVP scope bullet listing FR-16/FR-18/FR-29
  drops FR-18. §9 Assumptions Index gets a new dated entry recording this cut, matching the format of every
  prior entry there.
- **Architecture**: frontmatter `binds:` list drops FR-18. AD-1's closing note ("FR-18's full regeneration is
  the only way to redo generation for a Journey the reviewer keeps") needs rewording — as of this cut, there is
  **no** way to redo generation for a kept Journey short of deleting and it never re-appearing (deletion only
  excludes, it doesn't recreate). Module Map's "Playwright Generation" row FRs-covered drops FR-18 and its
  Isolation column's "Regeneration/versioning logic changes stay inside this module" clause is trimmed (the
  versioning scaffold stays for 4.1/4.2's own idempotency; the customer-facing regeneration trigger it was
  originally justified by does not). AD-8's descriptive mention of "a new FR-18 regeneration attempt" gets
  reworded to describe the scaffold in terms of what it actually serves today (4.1/4.2 idempotent re-trigger),
  not a cut feature.
- **UX (DESIGN.md/EXPERIENCE.md)**: checked — no wireframe, component, or flow is dedicated to a regenerate
  control; Story 4.3's own Dev Notes already flagged its screen placement as an unresolved gap, never a
  documented UX requirement. Nothing to revert here.
- **Other artifacts**: no deployment scripts, IaC, CI/CD, or monitoring config reference regeneration. No
  action needed.

### Code Impact (see Investigation finding above)
- Delete `_bmad-output/implementation-artifacts/4-3-full-regeneration-of-test-assets-on-request.md` (matches
  this project's own precedent — Stories 3.2/3.3/5.1-5.3/6.1's files were deleted outright when cut, not kept
  as stubs).
- Remove the `epic-4` entry for `4-3-full-regeneration-of-test-assets-on-request` from
  `implementation-artifacts/sprint-status.yaml`.
- Reword ~3 stale comments/docstrings across
  `apps/workers/generation/tests/test_playwright_generation_activity.py`,
  `packages/domain/src/domain/scenario.py`, and `packages/domain/src/domain/test_asset.py` that narrate
  "Story 4.3" as a real, upcoming feature. No test assertions or behavior change — comment-only.
- **No endpoint, workflow, or UI code to delete** — none was ever built.

## 3. Recommended Approach

**Option 1 (Direct Adjustment)** — cut the story and its FR from the docs, correct the stale "completed"
tracking, reword the handful of comments that assumed 4.3 would ship. **Effort: Low. Risk: Low.** This is the
obvious and only sensible path — there's no rollback needed (nothing was built) and no MVP scope question
(Epic 4 was already going to ship with or without this story; the other two carry the full FR-16/17/29 value).

**Option 2 (Rollback)** — not applicable, nothing to roll back.

**Option 3 (MVP Review)** — not applicable, this narrows scope further in the same direction the 2026-07-15
change already established (fewer reviewer/customer levers, simpler mental model); it doesn't threaten the MVP.

**Selected: Option 1, direct adjustment.** Scope classification: **Minor** — implementable directly, no
backlog reorganization, no architect/PM escalation needed.

## 4. Detailed Change Proposals

### PRD (`prds/prd-AITestGen-2026-07-13/prd.md`)

**§4.5, FR-18** — OLD:
```
#### FR-18: Full regeneration on request
When a customer triggers regeneration of Test Assets for a Journey, platform regenerates Scenarios and Test
Assets from scratch. [UPDATED 2026-07-15] Since generation is no longer gated on approval (§4.4), regeneration
is the only way to redo generation for a Journey the reviewer has kept; individual Scenarios can additionally
be edited/removed pre-generation as of 2026-07-15 — see FR-29.

**Out of Scope:** V1 has no capability to detect *what* changed in a Journey and regenerate incrementally —
regeneration is always full, not a diff/patch. See §5 Non-Goals.
```
NEW:
```
#### FR-18: Full regeneration on request `[CUT 2026-07-27]`
Previously: when a customer triggers regeneration of Test Assets for a Journey, platform regenerates Scenarios
and Test Assets from scratch. Cut in full — an explicit product decision that V1 ships with no customer-facing
way to refresh a Journey's generated coverage once produced; a reviewer's only lever over generated content
remains deletion (FR-13), which excludes rather than regenerates. Retained here, per this document's
convention, as a record of intent rather than silently deleted.
```

**§5 Non-Goals** — OLD: "No runtime drift/change detection on previously-discovered Journeys — V1 cannot tell
what changed inside a Journey, only regenerate it from scratch on request." NEW: "No runtime drift/change
detection on previously-discovered Journeys, and (as of 2026-07-27) no regeneration mechanism at all — V1
cannot tell what changed inside a Journey, and has no way to refresh its Scenarios/Test Assets short of
deleting the Journey outright (FR-13, which excludes rather than regenerates)."

**§6.1 MVP Scope** — drop `FR-18` from the "Scenario generation... (FR-16, FR-18, FR-29)" bullet →
"(FR-16, FR-29)".

**§9 Assumptions Index** — append:
```
- **2026-07-27**: FR-18 (Full regeneration on request) cut in full — explicit product decision, not deferred.
  V1 ships with no customer-facing way to refresh a Journey's generated Scenarios/Test Assets once produced;
  deletion (FR-13) remains the sole reviewer lever, and it excludes rather than regenerates. No code existed
  to remove — despite `sprint-status.yaml`/commit history suggesting Story 4.3 was "completed," it was never
  actually built (that work was Story 4.2's). Story 4.3 deleted from `epics.md` and its story file removed;
  `epics.md#Epic 4` description updated to drop the "regenerable from scratch on request" claim. Architecture
  AD-1/AD-8/Module Map updated to match — see `sprint-change-proposal-2026-07-27.md`.
```

### Epics (`epics.md`)

- Epic 4 description — OLD: "Every discovered Journey automatically produces happy-path/negative Scenarios and
  executable Playwright Test Assets, viewable, and regenerable from scratch on request — generation starts
  immediately on discovery (Epic 2), not on approval." NEW: "Every discovered Journey automatically produces
  happy-path/negative Scenarios and executable Playwright Test Assets — generation starts immediately on
  discovery (Epic 2), not on approval. `[UPDATED 2026-07-27]` There is no regeneration mechanism — once
  generated, a Journey's coverage is refreshed only by deleting the Journey (Epic 3) and letting re-discovery
  produce a new one."
- **FRs covered** line drops "FR-18."
- Delete the entire "### Story 4.3: Full Regeneration of Test Assets on Request" section, replacing it with a
  history note in the same style as the existing Epic 5/6/7 removal note directly below it:
  ```
  *(Story 4.3 "Full Regeneration of Test Assets on Request" [FR-18] removed in full 2026-07-27 — explicit
  product decision, not deferred. No code existed to remove: despite tracking suggesting it was "completed,"
  the regenerate-trigger endpoint and UI control were never built (see sprint-change-proposal-2026-07-27.md).)*
  ```
- **FR Coverage Map**: drop the `FR-18: Epic 4 - Full regeneration on request` line entirely (matching how
  FR-10/FR-11 are handled there — as `[CUT]` notes, not silent removal). I'll mark it `[CUT 2026-07-27]` rather
  than delete the line, consistent with the FR-10/11 treatment two lines above it.

### Architecture (`ARCHITECTURE-SPINE.md`)

- Frontmatter `binds:` — remove `FR-18`.
- **AD-1** — trim the clause "FR-18's full regeneration is the only way to redo generation for a Journey the
  reviewer keeps" → "there is no mechanism to redo generation for a Journey the reviewer keeps — deletion
  (FR-13) only excludes it, it does not trigger anything new. `[UPDATED 2026-07-27]` FR-18 (regeneration) is
  cut in full; this AD's `attempt`/`GenerationWorkflow` scaffold remains as-is, it simply has no second caller."
- **AD-8** — reword "A new FR-18 regeneration attempt writes new `Scenario`/`TestAsset` rows..." →
  "`[UPDATED 2026-07-27]` FR-18 is cut — no caller ever writes a second attempt today — but the `current`/
  `generation_run_id` fields this rule establishes are retained as-is: they're what Story 4.1/4.2's own
  idempotent re-trigger protection (AD-9) depends on, independent of whether a regeneration feature exists."
- **Module Map** row "Playwright Generation" — FRs column: `FR-17-18` → `FR-17`. Isolation column: drop
  "Regeneration/versioning logic changes stay inside this module" (nothing regenerates); keep the row
  otherwise unchanged.
- **Deferred section** — add one line noting FR-18/Story 4.3 is cut (not deferred), for the same reason the
  2026-07-15 cuts each got a line there, so a future reader doesn't mistake silence for an oversight.

### Sprint status (`implementation-artifacts/sprint-status.yaml`)

Remove the `4-3-full-regeneration-of-test-assets-on-request: ready-for-dev` line under `epic-4:`, and add a
comment there matching the file's existing convention for cut stories (e.g. the Story 1.5 removal note):
```
  # Story 4.3 (Full Regeneration of Test Assets on Request) removed 2026-07-27 — explicit product decision,
  #   not deferred; no code existed to build on despite tracking suggesting otherwise. See
  #   sprint-change-proposal-2026-07-27.md.
```

### Story file

Delete `_bmad-output/implementation-artifacts/4-3-full-regeneration-of-test-assets-on-request.md` outright —
matches this project's precedent for cut stories (3.2, 3.3, 5.1-5.3, 6.1 files were deleted, not stubbed).

### Code comments (no behavior change)

- `apps/workers/generation/tests/test_playwright_generation_activity.py` (~L164-183): reword "soft-superseded,
  Story 4.3 AC 2" and "Simulate Story 4.3 regeneration" to describe what the test actually verifies —
  `EnsureTestSuiteActivity`'s atomic supersede behavior when `Journey.attempt` changes — without implying a
  shipped regenerate-trigger feature.
- `packages/domain/src/domain/scenario.py` (~L5-8): reword "gives Story 4.3's regeneration something to
  supersede by" → "gives any future attempt-bump something to supersede by" (or similar) — same idea, no
  reference to a cut story.
- `packages/domain/src/domain/test_asset.py`: comment already speaks generically ("keeps incrementing across
  regenerations") — no change needed, it doesn't name Story 4.3.

## 5. Implementation Handoff

**Scope: Minor.** No backlog reorganization, no PM/Architect escalation. I (as the Dev agent context for this
correct-course pass) will apply all the doc edits above plus the three comment rewords directly, pending your
approval below.

## 6. Success Criteria

- FR-18 and Story 4.3 no longer appear as active/pending anywhere in `epics.md`, `sprint-status.yaml`, or the
  PRD's in-scope sections — each is marked `[CUT 2026-07-27]` where the document's convention requires keeping
  a record, and removed outright where the convention is deletion (story file, sprint-status entry).
- `apps/`, `packages/` contain no comment implying a regenerate-trigger feature exists or is planned.
- Epic 4 = Stories 4.1 + 4.2 only, matching what's actually implemented today.
