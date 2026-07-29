---
baseline_commit: dea7fc8fd61fa0d3e4fd4db2c491e763b149759d
---

# Story 2.15: Blocked Frontier — Aggregated Deferral

*Added per `sprint-change-proposal-2026-07-29.md`.*

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want blocked exploration areas that need the same missing data consolidated into one request,
so that I'm not asked the same question once per page.

## Acceptance Criteria

1. **Given** the Planner (Story 2.11) reaches a DEFER decision, **when** a `BlockedTask` is created or updated, **then** it is checked against existing open requirements with identical required content and aggregated rather than duplicated. [Source: epics.md#Story 2.15; FR-42; architecture#AD-20]
2. **Given** a blocked area, **when** autonomous exploration is otherwise exhausted and the area is meaningful, **then** one consolidated request is presented, with an explicit option to finish without supplying it. [Source: FR-42]
3. **Given** a DEFER from the Safety Engine (Story 2.12 — approval needed) versus the Data Resolver (Story 2.13 — data needed), **when** a `BlockedTask` is written, **then** both use the identical `BlockedTask` structure and resume path (Story 2.16) — only `required_type` differs; a single blocked path may carry both requirements at once. [Source: FR-42]
4. A blocked area does not stop the run — the Planner returns to the exploration queue and continues elsewhere. [Source: FR-42]

## Tasks / Subtasks

- [ ] Task 1: Add the `BlockedTask` domain entity (AC: 1, 3)
  - [ ] Add `BlockedTask` (`id`, `application_id` FK, `discovery_run_id` FK, `status` [`"blocked_data" | "blocked_approval" | "blocked_both" | "resolved"`], `required_description: str`, `required_type` [`"data" | "approval"`], `created_at`, `resolved_at` nullable) to `packages/domain`
  - [ ] Alembic migration
  - [ ] `ExplorationStep` (Story 2.16) references `BlockedTask` by FK — this story only needs `BlockedTask` itself; Story 2.16 owns the step-list
- [ ] Task 2: Wire DEFER → `BlockedTask` creation (AC: 1, 3, 4)
  - [ ] When the Planner (Story 2.11) reaches DEFER (from either the Safety Engine or the Data Resolver), create a `BlockedTask` with the appropriate `required_type`/`required_description`, or — if an open `BlockedTask` with an identical `required_description` already exists for this Application — attach to it instead of creating a new one (the aggregation check in AC 1)
  - [ ] If a single path needs both a data value and an approval, both requirements attach to the same `BlockedTask` (`status="blocked_both"`)
  - [ ] After writing/aggregating, the Planner immediately returns to the exploration queue — no blocking wait
- [ ] Task 3: Build aggregation-check and presentation-readiness logic (AC: 1, 2)
  - [ ] Read-time query: group open `BlockedTask` rows by `required_description` (exact match is sufficient for V1 — no fuzzy/semantic dedup) to present one consolidated item per distinct requirement, even though multiple crawl paths may reference it
  - [ ] "Presented only after autonomous exploration is otherwise exhausted" — for V1, this can be satisfied simply by surfacing open `BlockedTask`s once `DiscoveryRun.status` reaches `complete` (Story 2.3's amended AC) rather than mid-run; a mid-run surfacing mechanism is not required by this story's ACs
- [ ] Task 4: Verify end-to-end (AC: 1-4)
  - [ ] Four separate pages each needing "Active Policy Number" produce exactly one open `BlockedTask`, not four
  - [ ] A path needing both a Policy Number and approval to "Submit Claim" produces one `BlockedTask` with both requirements
  - [ ] A blocked path never halts exploration of the rest of the Application — verify the crawl reaches `status=complete` with open `BlockedTask` rows still present (per Story 2.3's amended completion AC)

## Dev Notes

- **This story owns aggregation and the `BlockedTask` shell; it deliberately does not own the full step-by-step path or the resume mechanism** — that's Story 2.16's job. Keep this story's scope to "detect, classify block reason, aggregate, persist the shell" only.
- **Aggregation is exact-string-match on `required_description` for V1** — a more sophisticated semantic-similarity aggregation ("Active Policy Number" vs. "Policy Number (Active)" as the same underlying ask) is out of scope here; flag it as a future refinement if pilot feedback shows exact-match aggregation is too brittle.
- **No user-facing UI is built by this story** — presenting the consolidated request to the user is a `[GAP]`-flagged UX item (see Story 2.17's note); this story's scope is the backend persistence/aggregation model only.

### Project Structure Notes

- Adds one new domain entity (`BlockedTask`) to `packages/domain`. No new top-level directories.
- Depends on Story 2.11's Planner (the DEFER decision this story reacts to) and feeds Story 2.16 (which extends `BlockedTask` with the actual step-list).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.15]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Sections 14, 14.1-14.4 of the source design document]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-20]

## Previous Story Intelligence

No prior story in this codebase has any notion of a "blocked" or deferred exploration state — Story 2.2's crawler currently either executes an action with generic data or (per its own Dev Notes) simply proceeds; there is no existing defer/park mechanism to build on. This is genuinely new domain surface.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
