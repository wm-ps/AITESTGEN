---
baseline_commit: 48b6499e08423320a0156e02720f1e8e2ba7d66c
---

# Story 2.3: Discovery Completion `[RENAMED 2026-07-15, was "Discovery Stop Conditions & Completeness Status"]`

Status: done <!-- verified live end-to-end 2026-07-20: real Discovery Runs reach status=complete with no iteration cap, as designed -->

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

- [x] Task 1: Replace Story 2.2's placeholder stopping cap with the real FR-7 rule (AC: 1)
  - [x] Track, per exploration iteration, whether any new page/action/state-transition was found (i.e. not already represented by an existing `Evidence` row for this run). When an iteration finds nothing new, that's exhaustive traversal — the only stop condition
  - [x] **Keep this inside the same `DiscoveryActivity` Story 2.2 built** — there's no need for a second Activity call. `DiscoveryActivity` already owns I/O (AD-2); it can check this stop condition each loop iteration and write the final `DiscoveryRun.status` itself before returning, exactly as it already writes `Evidence` rows incrementally
  - [x] On exhaustive stop, set `DiscoveryRun.status = "complete"` — this is the one and only place that value gets written
  - [x] **`[RESOLVED 2026-07-15]` No time-budget cutoff exists.** An earlier draft of this story computed a deadline from `Application.time_budget_minutes` and wrote `status="incomplete"` on timeout — both the field and the status value are gone (FR-5 removed). Do not build a deadline check of any kind here; Story 2.2's placeholder iteration-cap is test-only scaffolding, not a product feature to formalize
- [x] Task 2: Audit every completeness read-path to use `DiscoveryRun.status` directly (AC: 2)
  - [x] Discovery Progress and any other surface referencing this run's completeness must query `status` directly — never infer completeness from `Evidence` row counts, elapsed time, or any other proxy. This is the literal enforcement of AD-10 ("completeness is never inferred from the presence/absence of other data")
- [x] Task 3: Wire the status-pill's `Complete` state (AC: 1)
  - [x] **`Complete` has no documented pill variant in `DESIGN.md`** — only `Running` (signal, pulsing) is named. Resolved here: use `{colors.good-wash}`/`{colors.good}` (green) for `Complete`, consistent with `DESIGN.md`'s stated semantic-color rule ("Green means approved/generated/healthy"), with the pulsing dot removed once no longer "in progress." Treat this as a filled UX gap, not a literal DESIGN.md spec — flag it if a future design pass wants to formalize it
  - [x] **`[RESOLVED 2026-07-15]` No `Incomplete` state to build.** An earlier draft specified a `Running` → `Incomplete` (amber) transition on time-budget cutoff, reusing `DESIGN.md`'s documented amber note — that note describes a state this pill no longer has. The only transition is `Running` → `Complete`
- [x] Task 4: Verify end-to-end and record evidence (AC: 1, 2)
  - [x] A Discovery Run against a small, fully-crawlable target reaches `status=complete` when no new evidence is found, with the pill showing the (gap-filled) `Complete` treatment
  - [x] Every surface showing run completeness reads `DiscoveryRun.status` directly (code-review-checkable, not just a runtime test)
  - [x] No code path anywhere computes or displays an `incomplete` state — a deliberate negative check, not just a positive functional test

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

claude-sonnet-5

### Debug Log References

- `uv run pytest apps/ packages/ -q` (same throwaway Postgres/Vault/MinIO/Temporal stack as Story
  2.2) → **19 passed** — `test_discovery_activity_integration.py` now also asserts
  `DiscoveryRun.status == "complete"` after a full crawl against the live local target.
- `uv run ruff check` / `uv run pyright` → all clean.
- `npx vitest run` → **13 passed** (11 pre-existing + 2 new `StatusPill` tests: `Running`
  signal-colored with a pulsing dot, `Complete` good/green-colored with no dot). `tsc -b` /
  `oxlint` clean.
- `grep -rniE "\bincomplete\b" apps/ packages/ --include="*.py" --include="*.ts" --include="*.tsx"`
  (excluding `node_modules`) → zero hits in product source, satisfying Task 4's negative check
  that no code path computes or displays an `incomplete` state.

### Completion Notes List

- **Story 2.2's `MAX_ITERATIONS` placeholder removed entirely, not tightened** — the crawl loop
  (`crawler.py`) now runs `while page_queue:` with no cap at all, per this story's explicit,
  repeated instruction that no safety cap exists by product decision (PRD §12 Risk item 7,
  accepted risk). The natural termination condition — the page queue empties because no new
  same-origin links were found to enqueue — **is** the exhaustive-traversal signal; forms and
  standalone-button actions are already exercised exhaustively per page in the same pass Story 2.2
  built, so "the queue is empty" already means "no new page, form, or action was found."
- **`DiscoveryRun.status = "complete"` written in exactly one place**: `discovery_activity`
  (`activities.py`), immediately after `run_discovery_crawl` returns, in the same DB session/commit
  as the `Evidence` rows. No second Activity call, per Task 1's explicit instruction — the same
  `DiscoveryActivity` Story 2.2 built owns this write.
- **Audit (Task 2) confirmed clean, no changes needed**: `GET /applications/{id}` already returned
  `discovery_status=discovery_run.status` directly (Story 1.3), and the new
  `GET /discovery-runs/{id}/evidence` endpoint (Story 2.2) never touches completeness at all — it
  only lists `Evidence` rows. Neither endpoint nor the frontend (`DiscoverJourneysPlaceholder`,
  `StatusPill`) infers completeness from row counts, elapsed time, or any other proxy.
- **`StatusPill`'s `Complete` variant**: `{colors.good-wash}`/`{colors.good}` (green), pulsing dot
  suppressed (the dot only renders for `status === "running"`, unchanged from Story 2.1/2.2). A
  small `COLORS` lookup keyed by status replaces the previously-hardcoded signal-only styling —
  deliberately just `running`/`complete` for now, not pre-building a `failed` entry (Story 2.4's
  job).
- **No `Incomplete` state anywhere** — verified by both code inspection (no `time_budget`,
  `deadline`, or `incomplete` identifiers anywhere in `DiscoveryActivity`/`DiscoveryRun`/the
  frontend) and the `grep` check in Debug Log References.
- **Verification gap — no browser tool available in this environment**: the pill's green
  color/no-dot rendering was verified via `vitest`/DOM style assertions and a real end-to-end
  crawl-to-`complete` run, not by visually confirming the Discovery Progress screen in a live
  browser.
- Per the operator's instruction for this session, **no git commits were created**.

### File List

- `apps/workers/discovery/src/discovery_worker/crawler.py` — removed `MAX_ITERATIONS`; loop is now
  `while page_queue:`, terminating on genuine exhaustion only.
- `apps/workers/discovery/src/discovery_worker/activities.py` — writes
  `DiscoveryRun.status = "complete"` after a successful crawl.
- `apps/workers/discovery/tests/test_discovery_activity_integration.py` — added the
  `status == "complete"` assertion.
- `apps/web/src/components/StatusPill.tsx` — added the `Complete` (green) color variant via a
  `COLORS` lookup; pulsing-dot color now derives from the resolved variant instead of being
  hardcoded to signal.
- `apps/web/src/components/StatusPill.test.tsx` — new: `Running` vs. `Complete` variant tests.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status tracking only.

## Change Log

- 2026-07-17 — Implemented all 4 tasks (AC 1–2): replaced Story 2.2's placeholder iteration cap
  with the real exhaustive-traversal stop condition (no safety cap, by explicit product decision),
  confirmed every completeness read-path already used `DiscoveryRun.status` directly, and added the
  gap-filled `Complete` (green) status-pill variant. Verified against a live local target reaching
  real `status=complete`, and a `grep`-based negative check that no `incomplete` state exists
  anywhere in source. Status moved to `review`.
