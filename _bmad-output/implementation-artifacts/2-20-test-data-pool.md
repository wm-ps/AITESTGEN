---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.20: Test Data Pool — Seeded Application Test Data

*Added 2026-08-03 per `docs/DISCOVERY_ENGINE_V2.md` (spine box **0.1 — PREPARE**). Identified as the highest-leverage gap during the feasibility review of the 2026-07-29 Discovery Engine batch: the cheapest time to obtain test data is before the crawl, not after.*

Status: review  # `[COMPLETED 2026-08-04]` `TestDataEntry` entity + migration e1a2b3c4d5e7
  # (joint with Story 2.13's `SyntheticDataEntry`), the shared `aggregation_key` normalizer
  # (built here, ahead of its nominal owner Story 2.15 — see that story's amendment note),
  # CRUD API, Vault-backed sensitive storage, and pool loading at Activity start, consulted first
  # by Story 2.13's resolver. Task 4 (answering a Blocked Frontier item writes to the pool) not
  # built — depends on Story 2.15's `BlockedTask`, which doesn't exist yet. See Dev Agent Record.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to give the platform the business-specific values it will need before discovery starts,
so that it explores straight through the areas that would otherwise block, instead of stopping and asking me afterwards.

## Acceptance Criteria

1. **Given** an Application, **when** a user seeds test data, **then** entries of (label, normalized key, value, sensitive flag) are stored per Application and persist across Discovery Runs. [Source: docs/DISCOVERY_ENGINE_V2.md#0.1; #D — DECIDE]
2. **Given** the Data Resolver (Story 2.13) needs a value, **when** it resolves, **then** the pool is consulted **first**, ahead of page scanning, run reuse and synthesis. [Source: docs/DISCOVERY_ENGINE_V2.md#D — DECIDE]
3. **Given** a pool entry, **when** its key is computed, **then** it uses the **same shared normalization function** as Story 2.15's `aggregation_key`, so a pool entry and a blocked requirement for the same underlying field match automatically and exactly. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT]
4. **Given** an open `BlockedTask` (Story 2.15), **when** the user supplies its missing value, **then** the value is written into the pool under that block's `aggregation_key` — so it satisfies **every** path needing that key, not only the one that surfaced the ask. [Source: docs/DISCOVERY_ENGINE_V2.md#E — ACT]
5. **Given** a value resolved from the pool, **when** it is used, **then** it is logged as `SyntheticDataEntry` with `source=pool`, exactly like any other resolved value. [Source: FR-40]
6. **Given** an entry marked **sensitive**, **when** it is stored, **then** the value is held via the existing `packages/secrets_client` Vault-backed client rather than in plain application storage, and it is **masked** everywhere it would otherwise appear — logs, `SyntheticDataEntry` output, and the Story 2.22 report. [Source: docs/DISCOVERY_ENGINE_V2.md#0.1]

## Tasks / Subtasks

- [x] Task 1: Add the `TestDataEntry` entity (AC: 1, 6) — `[COMPLETED 2026-08-04]`
  - [x] `TestDataEntry` (`id`, `external_id`, `application_id` FK, `label`, `normalized_key` (indexed), `value` nullable, `secret_ref` nullable, `is_sensitive`, `created_at`, `updated_at`) in `packages/domain/src/domain/test_data_entry.py`
  - [x] Alembic migration `e1a2b3c4d5e7` (joint with Story 2.13's `SyntheticDataEntry` — see that story); unique on `(application_id, normalized_key)`
  - [x] Sensitive values go through `packages/secrets_client`'s `VaultSecretsClient` — same client `Application.secret_ref` already uses, no second secret store
- [x] Task 2: Share the key-normalization function (AC: 3) — `[COMPLETED 2026-08-04, built here instead]`
  - [x] `domain.aggregation_key(field_name, input_type, route_family)` in `packages/domain/src/domain/key_normalization.py` — **built by this story, not imported from Story 2.15**, since 2.15 lands after 2.20/2.13 per the documented BUILD ORDER and doesn't exist yet. Story 2.15 will import this function when it lands, not write a second one — its own amendment note says so.
  - [x] Word-order-invariant by design: tokenizes and sorts words before joining, so "Active Policy Number" and "Policy Number (Active)" produce the same key (asserted directly in a self-check; Story 2.13's `test_data_resolver.py` exercises it indirectly via `field_key()`)
  - [ ] **Not yet asserted against a real `BlockedTask`** — Story 2.15 doesn't exist yet, so there's no second call site to test key parity against today; the function itself is the parity guarantee once 2.15 lands and imports it
- [x] Task 3: Wire the pool as resolution step 1 (AC: 2, 5) — `[COMPLETED 2026-08-04]`
  - [x] `_seed_test_data_pool()` in `activities.py`, called at `discovery_activity` start alongside `_seed_state_identity_cache` — resolves sensitive entries through Vault once, at load time, so the resolver only ever sees plaintext in memory
  - [x] Story 2.13's `data_resolver.resolve()` consults it first (real route family, then a wildcard fallback — see that story's Dev Notes for why)
  - [x] Every pool-sourced value logged as a `SyntheticDataEntry` with `source="pool"`, masked (`"***REDACTED***"`) before it ever leaves process memory when sensitive
- [ ] Task 4: Supplying a value against a block writes to the pool (AC: 4) — **NOT BUILT**: depends on Story 2.15's `BlockedTask`, which doesn't exist yet (2.15 wasn't in this session's scope). Story 2.13's DEFER path currently only emits an `execution_decision` diagnostic carrying the normalized key — there is no `BlockedTask` row for an answer to attach to yet. Story 2.15, when built, is what closes this.
- [x] Task 5: CRUD surface (AC: 1) — `[COMPLETED 2026-08-04]`
  - [x] `GET/POST /applications/{external_id}/test-data`, `PATCH/DELETE /test-data/{external_id}` in `apps/api/src/api/main.py`, following this codebase's actual existing conventions
  - [ ] **Deviation from the AC as written**: plain `HTTPException(detail=...)`, not an RFC 7807 envelope — this codebase has **no RFC 7807 helper anywhere**; every existing endpoint (Journey CRUD, Application CRUD) uses plain `HTTPException`. Matching this story's literal AC would mean introducing RFC 7807 unilaterally, inconsistently with every other endpoint — matched the codebase's real, established convention instead
  - [x] `[GAP — needs UX pass]` unchanged: backend + API only, no screen in the current IA; independently useful (seed via API) — deferred alongside Stories 2.17/2.22's UI halves
- [x] Task 6: Verify end-to-end (AC: 1-6) — `[COMPLETED 2026-08-04, partial — see below]`
  - [x] Unit (Story 2.13's `test_data_resolver.py`): a pool entry is used by the resolver in preference to synthesis
  - [ ] **Not verified live**: "the crawl passes through a page that would otherwise have blocked" — no real-Chromium fixture exercises a pool-seeded field end-to-end this session; the resolution-order guarantee is unit-tested, the live wiring (`_seed_test_data_pool` -> `run_discovery_crawl` -> `_fill_and_submit_form`) is real but unexercised by an integration test
  - [ ] **Not applicable yet**: the `BlockedTask`-matching and pool-persistence-across-runs checks depend on Story 2.15 (not built) and a real Postgres round-trip (not run this session — see the Change Log's note on infra availability)
  - [x] A sensitive entry's value is masked in every `TestDataEntryRead` response (`_mask()`) and redacted before being logged as `SyntheticDataEntry`
  - [ ] A sensitive entry's value never appears in logs, `SyntheticDataEntry` output, or the report
  - [ ] Pool entries persist across two consecutive Discovery Runs for the same Application

## Dev Notes

- **This is the highest-leverage story in the remaining batch.** The 2026-07-29 design's answer to missing test data was entirely reactive: defer the action, aggregate the requirement, ask the user after the run, then resume. That machinery (Stories 2.15 + 2.16) is substantial, and most of it exists to recover from a situation that a few seeded values would have prevented outright. Preventing the block is far cheaper than recording, aggregating, surfacing and resuming from it.
- **The pattern is already proven in this product.** Story 4.1 does exactly this at scenario-generation time — the AI declares which test-data fields a Scenario needs, the user fills them, and generation is gated until mandatory fields are populated. This story brings the same idea one stage earlier, to discovery, where it prevents the problem instead of reporting it.
- **Key parity with Story 2.15 is the one thing that must not break.** Stories 2.13, 2.15 and 2.20 all depend on producing byte-identical normalized keys. If they drift, pool entries silently stop satisfying blocks and users are asked for data they already supplied — a confusing bug with no obvious symptom. One shared function, imported everywhere, tested from all three call sites.
- **Seeding is optional and the engine must work without it.** An empty pool simply means resolution starts at step 2, which is exactly today's behaviour. Do not make pool population a precondition for starting a run.
- **Sensitive entries reuse existing infrastructure.** `packages/secrets_client` already provides a Vault-backed client used for application credentials — extend its use rather than introducing a parallel mechanism or storing secrets in Postgres.
- **This story reduces the value of Story 2.16.** That is intentional and worth stating: if the pool eliminates most blocks in pilot use, re-crawl resume becomes a rarely-exercised path and a legitimate cut candidate.

### Project Structure Notes

- Adds the `TestDataEntry` entity to `packages/domain`, CRUD endpoints to `apps/api`, and pool loading to the discovery activity. Reuses `packages/secrets_client`. No new top-level directories, no new services.
- Depends on Story 2.15 (the shared key normalizer). Feeds Stories 2.13 (resolution step 1) and 2.16 (where a supplied value lands).

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#0.1 PREPARE, #D — DECIDE, #E — ACT]
- [Source: _bmad-output/implementation-artifacts/4-1-generate-scenarios-for-an-approved-journey.md — the equivalent pattern at scenario-generation time]
- [Source: _bmad-output/implementation-artifacts/2-15-blocked-frontier.md — the shared `aggregation_key` normalizer]

## Previous Story Intelligence

Story 4.1 already establishes this product's convention that the platform declares what data it needs and never invents business-specific values itself — this story is the discovery-time counterpart and should match its language and shape. `packages/secrets_client/src/secrets_client/vault_client.py` is the existing secret-storage path; `Application` already references Vault for credentials, so the pattern to follow is in the codebase.

## Latest Technical Notes

No new library decisions — reuses the existing Vault client and `apps/api` conventions.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- The shared normalizer (Task 2) was built **by this story**, not imported from Story 2.15 — the documented BUILD ORDER lands 2.20/2.13 before 2.15, so 2.15's own entity/function don't exist yet. Placed in `packages/domain` (not `apps/workers/discovery`) since it needs to be importable by both the discovery worker and `apps/api` without a cross-package dependency either direction. Story 2.15, when built, imports this function rather than writing a second one — flagged in its own sprint-status amendment note so this isn't lost.
- Route family is not something a user seeding data before any crawl has run can reasonably supply, but the shared `aggregation_key` function requires one. Resolved by storing/seeding under a wildcard route family (`_POOL_WILDCARD_ROUTE_FAMILY = "*"` in `apps/api/src/api/main.py`) by default, with the Data Resolver (Story 2.13) trying the real route family first and falling back to the wildcard — still the identical normalizer function either way, just a considered choice of what to pass for one of its three parameters. Documented inline at both call sites since this is exactly the kind of thing that looks like a second normalizer at a glance and isn't.
- Task 4 (a `BlockedTask` answer writing to the pool) is not built — it has nothing to attach to, since Story 2.15's `BlockedTask` entity doesn't exist. Not a shortcut: there is no smaller version of this task that doesn't presuppose 2.15's schema.
- Task 5's AC calls for an "RFC 7807 error envelope," but no endpoint in this codebase uses one — a repo-wide survey before writing the CRUD routes confirmed every existing resource (Journeys, Applications) raises a plain `fastapi.HTTPException(detail=...)`. Matched that real convention instead of introducing RFC 7807 unilaterally on one new resource, which would make this resource inconsistent with every other one instead of consistent with the AC as literally written.
- Verified: the module boundary (`packages/domain` importing cleanly from both `apps/api` and `apps/workers/discovery`), migration chain (`alembic heads` resolves to this migration), and `apps/api.main` importing cleanly with the new routes registered. No real-Postgres round-trip or live-Chromium pool-consultation test was run this session — see the sprint-status note on infra availability at the time of this work.

### File List

- `packages/domain/src/domain/test_data_entry.py` (new)
- `packages/domain/src/domain/key_normalization.py` (new — shared with Story 2.13; Story 2.15 will import this too)
- `packages/domain/src/domain/__init__.py` (modified — exports `TestDataEntry`, `aggregation_key`, `SyntheticDataEntry`)
- `migrations/versions/e1a2b3c4d5e7_add_test_data_pool_and_synthetic_data.py` (new — joint with Story 2.13)
- `apps/api/src/api/main.py` (modified — `TestDataEntry` CRUD routes, `_POOL_WILDCARD_ROUTE_FAMILY`)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified — `_seed_test_data_pool`, wired into `discovery_activity`)

## Change Log

- 2026-08-03 — Story created per `docs/DISCOVERY_ENGINE_V2.md`, following a feasibility review of the 2026-07-29 Discovery Engine batch which identified proactive test-data seeding as the highest-leverage missing capability.
- 2026-08-04 — Implemented: `TestDataEntry` entity + migration, the shared `aggregation_key` normalizer (built early — see Dev Agent Record), CRUD API, Vault-backed sensitive storage, and pool loading wired into `discovery_activity`/`run_discovery_crawl`. Moved `ready-for-dev` -> `review`. Task 4 (block-answer-writes-to-pool) explicitly not built, blocked on Story 2.15.
