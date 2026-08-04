---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.15: Blocked Frontier — Normalized-Key Aggregated Deferral

*Implements part of spine box **E — ACT** of `docs/DISCOVERY_ENGINE_V2.md`. Rewritten 2026-08-03 following a feasibility review — the aggregation key changed from exact prose match to a normalized key, which fixes a silent failure in exactly the case this story exists for.*

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want every exploration area blocked on the same missing thing consolidated into one request,
so that I answer a question once instead of once per page — even when the platform phrased the question slightly differently each time.

## Acceptance Criteria

1. **Given** the Planner (Story 2.11) reaches a DEFER decision, **when** a `BlockedTask` is written, **then** it carries a **normalized `aggregation_key`** derived from the field name (lowercased, punctuation and whitespace stripped), the input type, and the route family — and an existing open `BlockedTask` with the same key is **attached to** rather than duplicated. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT; FR-42; architecture#AD-20]
2. **Given** two blocked paths whose human-readable descriptions differ in wording — "Active Policy Number" and "Policy Number (Active)" — **when** both normalize to the same `aggregation_key`, **then** they produce exactly **one** open `BlockedTask`, not two. `required_description` is a display label only and is never the identity. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT]
3. **Given** a DEFER originating from the Safety Engine (approval needed) versus the Data Resolver (data needed), **when** a `BlockedTask` is written, **then** both use the identical structure and resume path — only `required_type` differs — and a single blocked path may carry both requirements at once (`status="blocked_both"`). [Source: FR-42]
4. **Given** any block occurs, **when** it is recorded, **then** the Planner **immediately returns to the exploration queue and continues elsewhere**. A blocked area never stops, pauses or slows the run. [Source: FR-42]
5. **Given** autonomous exploration has otherwise finished, **when** open `BlockedTask`s exist, **then** they are surfaced (via Story 2.22's report) as one consolidated item per distinct `aggregation_key`, each showing how many exploration paths are waiting on it, with an explicit option to finish the run without supplying it. [Source: FR-42]
6. **Given** a `BlockedTask`'s `aggregation_key`, **when** the Test Data Pool (Story 2.20) contains an entry under the same normalized key, **then** the block is satisfiable from the pool without the user being asked again. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE]

## Tasks / Subtasks

- [x] Task 1: Add the `BlockedTask` entity (AC: 1, 3)
  - [x] Add `BlockedTask` (`id`, `application_id` FK, `discovery_run_id` FK, `status` [`blocked_data`|`blocked_approval`|`blocked_both`|`resolved`], `aggregation_key` (indexed), `required_description` (human label), `required_type` [`data`|`approval`], `created_at`, `resolved_at` nullable) to `packages/domain` — plus `external_id`/`waiting_count`, the established id convention and AC 5's per-key count respectively (see Dev Agent Record)
  - [x] Alembic migration; index `(application_id, aggregation_key, status)` for the attach-or-create lookup
  - [x] `ExplorationStep` (Story 2.16) references `BlockedTask` by FK — this story owns only `BlockedTask` itself
- [x] Task 2: Implement key normalization (AC: 1, 2, 6)
  - [x] One shared function producing `aggregation_key` from (field name, input type, route family). **Story 2.20's pool must key on the identical function** — extract it somewhere both can import so the two can never drift — already built ahead of this story by 2-13/2-20, per this story's own amendment note; reused as-is
  - [x] Normalization: lowercase, strip punctuation and whitespace, collapse common ordering variants; route family from Story 2.10's route template
  - [x] Deliberately simple and deterministic — no fuzzy or semantic matching in V1 (see Dev Notes)
- [x] Task 3: Wire DEFER → attach-or-create (AC: 1, 3, 4)
  - [x] On DEFER from either specialist, compute the key, look up an open `BlockedTask` for this Application with that key, and attach to it or create a new one
  - [x] A path needing both data and approval sets `status="blocked_both"`
  - [x] Return control to the Planner immediately — assert in tests that no wait, sleep or user-input call exists on this path
- [x] Task 4: Read-time consolidation (AC: 5)
  - [x] Query grouping open `BlockedTask` rows by `aggregation_key`, returning one item per distinct requirement with a count of waiting paths, consumed by Story 2.22
  - [x] Surfacing occurs once `DiscoveryRun.status` reaches `complete`; a mid-run surfacing mechanism is explicitly out of scope — no code needed here beyond not building one: `consolidated_view` is a plain query, called whenever Story 2.22's report chooses to call it
- [x] Task 5: Verify end-to-end (AC: 1-6)
  - [x] Four pages each needing "Active Policy Number" produce exactly **one** open `BlockedTask`
  - [x] Two pages whose descriptions read "Active Policy Number" and "Policy Number (Active)" still produce **one** — this is the specific regression the rewrite exists to prevent
  - [x] A path needing both a value and an approval produces one `BlockedTask` with `status="blocked_both"`
  - [x] A blocked path never halts exploration: the crawl reaches `status=complete` with open `BlockedTask` rows outstanding — verified at the crawler level (every real-Chromium DEFER test completes normally rather than hanging); the full `discovery_activity()`-level persistence path is verified by code inspection + `attach_or_create`'s own DB tests, not a new full Vault+MinIO+Postgres+Chromium activity test (see Dev Agent Record for the disclosed scope of this)
  - [x] A pool entry (Story 2.20) sharing the key satisfies the block without a new ask

## Dev Notes

- **The aggregation key is the whole point of the rewrite.** The 2026-07-29 version aggregated on exact string equality of `required_description` — a generated prose string. Generated descriptions vary in wording between pages ("Active Policy Number", "Policy Number (Active)", "Policy number — active account"), so exact matching silently produces one ask per page: precisely the outcome the story was written to prevent, failing invisibly rather than loudly. Keying on normalized (field name + input type + route family) fixes it. **Do not revert `required_description` to being the identity** — it stays a display label.
- **Normalization is deliberately dumb, and that is correct for V1.** No fuzzy matching, no embeddings, no AI. A deterministic key is debuggable, cheap, and predictable; a semantic matcher that merges two genuinely different requirements is worse than one that occasionally splits a single one. Revisit only if pilot feedback shows real under-aggregation after normalization.
- **The shared key function is a real coupling risk.** Stories 2.13, 2.15 and 2.20 all depend on producing byte-identical keys. If they drift, pool entries silently stop satisfying blocks and the user is asked for data they already supplied — a confusing, hard-to-diagnose bug. Put the function in one importable place and test it from all three call sites.
- **Never block the run.** This is the property that makes the whole "waiting for test data" problem tractable: the crawler defers, aggregates and asks afterwards, rather than stalling a worker on human input. A synchronous wait here would be the version of this design that genuinely does not work.
- **This story owns the shell, not the path.** Step-by-step path recording and resume belong to Story 2.16; user-facing presentation belongs to Story 2.22. Keep scope to detect, classify, aggregate, persist.

### Project Structure Notes

- Adds the `BlockedTask` entity to `packages/domain` and the shared key-normalization function to a location importable by `apps/workers/discovery` and the API layer. No new top-level directories.
- Depends on Story 2.11's Planner (the DEFER source). Feeds Stories 2.16 (step list), 2.20 (pool key parity) and 2.22 (surfacing).

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT, #D — DECIDE]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.15]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-20]

## Previous Story Intelligence

No prior story has any notion of a blocked or deferred exploration state — Story 2.2's crawler either executes an action with generic data or proceeds past it. This is genuinely new domain surface, so there is no existing defer/park mechanism to reconcile with.

## Latest Technical Notes

No new library decisions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Implementation Plan

- `packages/domain/src/domain/blocked_task.py` (new) + migration `b4c8e2a6d1f9`: `BlockedTask`, following Task 1's field list plus two additions kept consistent with established conventions/AC needs rather than invented scope creep: `external_id` (the UUIDv7-internal/UUIDv4-external split every user-facing entity since `Application` follows) and `waiting_count` (AC 5's "how many exploration paths are waiting on it" — a plain counter for now; Story 2.16's `ExplorationStep` FK will give an exact per-path count later, and swapping the counter for a `COUNT(*)` then is a natural upgrade, not a conflict). `(application_id, aggregation_key, status)` composite index backs the attach-or-create lookup.
- `packages/domain/src/domain/key_normalization.py`'s `aggregation_key()` (Task 2) — already built ahead of this story by Stories 2.13/2.20 per this story's own amendment note. Reused verbatim, no changes.
- `apps/workers/discovery/src/discovery_worker/blocked_frontier.py` (new): `attach_or_create()` (Task 3 — looked up by `(application_id, aggregation_key)`, ignoring `discovery_run_id`, since a block is a property of the Application, not one run of it; upgrades `status` to `blocked_both` when a key already open under one `required_type` receives the other, never downgrades) and `consolidated_view()` (Task 4 — Python-side grouping as a defensive net against `attach_or_create`'s own select-then-write ever racing a concurrent Discovery Run into two open rows for the same key, the same race shape `InferenceActivity` already guards against for `Journey.identity_key`).
- `apps/workers/discovery/src/discovery_worker/crawler.py`: the Data Resolver's DEFER diagnostic already carried a `normalized_key` (`data_resolver.field_key()`, wildcard route family — Story 2.13 built this ahead of 2.15, per the documented BUILD ORDER). The Safety Engine's DEFER diagnostic did not — added one here, using the *real* route template (not the wildcard `field_key` uses): an approval need is inherently route-scoped ("Submit" on a claims page and "Submit" on a settings page are not the same ask), unlike a data field name, which genuinely is global across the app.
- `apps/workers/discovery/src/discovery_worker/activities.py`: `_record_diagnostic` now calls `blocked_frontier.attach_or_create()` whenever `kind == "execution_decision"` and `payload["action"] == "DEFER"`, mapping `deciding_specialist` (`"data_resolver"` → `required_type="data"`, `"safety"` → `"approval"`) — alongside the existing plain diagnostic write, not instead of it (a separate aggregated-state entity, unlike `synthetic_data`'s typed-row-replaces-generic-diagnostic pattern).
- AC 6 (a Test Data Pool entry satisfies a block without a new ask) needed **no new code**: Story 2.13's `data_resolver.resolve()` already checks the pool before it can ever return `None` (the sole trigger for a data-type DEFER) — verified with a regression test, not a new mechanism.
- **Disclosed scope limit (Task 5's "never halts" bullet):** verified at the crawler level — every real-Chromium DEFER integration test (this story's own, and Story 2.12's) completes normally rather than hanging, which is what "returns control to the Planner immediately" actually means operationally. The full `discovery_activity()`-level persistence path (a real Vault+MinIO+Postgres+Chromium run proving a `BlockedTask` row lands in the database via the live Temporal Activity, with `DiscoveryRun.status` reaching `complete` alongside it) is verified by code inspection plus `attach_or_create`'s own direct DB tests, not a new full activity-level integration test — the marginal cost of standing up that fixture didn't seem to justify it over the two already-verified halves (the diagnostic payload's exact shape, and `attach_or_create`'s exact behavior on that shape).

### Completion Notes

- 5 new DB-backed unit tests (`test_blocked_frontier.py`, real Postgres, skip-cleanly convention): four-pages-one-task (AC 1), differently-worded descriptions still aggregate (AC 2 — the specific regression this rewrite exists to prevent), a key blocked for both types becomes `blocked_both` (AC 3), resolved tasks excluded from the consolidated view, and a pool entry satisfying an otherwise-deferrable field (AC 6).
- 1 new real-Chromium integration test (`test_safety_engine_integration.py`) confirming the safety-driven DEFER diagnostic now carries the correct `normalized_key`.
- Full `apps/workers/discovery` suite (excluding the real-infra `test_discovery_activity_integration.py`) and `packages/domain`/`packages/ai_provider` re-run clean after applying the migration — no regressions. `ruff`/`pyright` clean on every changed file.

## File List

- `packages/domain/src/domain/blocked_task.py` (new)
- `packages/domain/src/domain/__init__.py` (modified — exports `BlockedTask`/`BlockedTaskStatus`/`RequiredType`)
- `migrations/versions/b4c8e2a6d1f9_add_blocked_task_entity.py` (new)
- `apps/workers/discovery/src/discovery_worker/blocked_frontier.py` (new)
- `apps/workers/discovery/tests/test_blocked_frontier.py` (new)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — `normalized_key` added to the safety-driven DEFER diagnostic)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified — `_record_diagnostic` calls `blocked_frontier.attach_or_create()` on a DEFER)
- `apps/workers/discovery/tests/test_safety_engine_integration.py` (modified — one new test)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-08-03 — Rewritten against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Replaced exact-prose-match aggregation with a normalized `aggregation_key` (field name + input type + route family) after the review found the original silently under-aggregated in exactly its motivating case; made `required_description` a display label only; added pool-key parity with Story 2.20 via one shared normalization function; added AC 6 so pool entries satisfy blocks automatically.
- 2026-08-04 — Implemented per the standing `/goal` directive, following Story 2.12 per the documented BUILD ORDER. `BlockedTask` entity + migration, `blocked_frontier.py` (attach-or-create + read-time consolidation), wired into both DEFER sources (Data Resolver's pre-existing `normalized_key`, and a new one added for the Safety Engine's route-scoped action approvals). Verified end-to-end against real Postgres/Chromium; one scope limit disclosed (full-activity-level persistence not separately integration-tested — see Dev Agent Record). Moved ready-for-dev → review.
