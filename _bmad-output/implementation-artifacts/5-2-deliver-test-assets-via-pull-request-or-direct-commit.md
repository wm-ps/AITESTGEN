# Story 5.2: Deliver Test Assets via Pull Request or Direct Commit

Status: backlog

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**`[DEFERRED POST-V1 — 2026-07-15]`** The Connect to CI/CD screen this story depends on is cut from the current reference prototype's IA. Do not schedule this story for dev-story until the real delivery/execution mechanism is designed. Retained below verbatim as a record of original intent — historical spec, not a build target. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

## Story

As a user,
I want generated Test Assets automatically delivered to my configured Git host,
so that the tests reach my real repository without manual copy-paste.

## Acceptance Criteria

1. **Given** a `TestAsset` ready for delivery and an Application with a configured Git host and export mode, **when** `CIDeliveryActivity` runs, **then** it calls only the `DeliveryAdapter` interface, selected by the Application's configured Git host — never by its CI system. [Source: epics.md#Story 5.2; FR-19; architecture#AD-4]
2. It checks for an existing PR/commit using a deterministic key derived from `journey_id` + `attempt` before acting, so a retried delivery reuses its own prior effect instead of duplicating it. [Source: epics.md#Story 5.2; architecture#AD-9]
3. Once delivered, the Connect to CI/CD screen's provider card shows a "Connected" status label. [Source: epics.md#Story 5.2; EXPERIENCE.md#State Patterns]

## Tasks / Subtasks

- [ ] Task 1: Implement the `DeliveryAdapter` port and its three concrete adapters (AC: 1)
  - [ ] Implement `deliver(test_asset: TestAsset, application: Application, mode: Literal["pr", "direct_commit"]) -> DeliveryResult` in `packages/delivery_adapters`, exactly per the Module Contracts Protocol signature
  - [ ] Build `GitHubAdapter`, `GitLabAdapter`, `AzureReposAdapter` — selected by `Application`'s `CIConfig.git_host` (Story 5.1), **never** by any CI-system setting (AD-4 explicitly forbids this — CI system is Story 5.3's separate concern)
  - [ ] Each adapter uses `CIConfig.repo_identifier` and resolves the access credential via `SecretsClient` (both added in Story 5.1's scope extension) to authenticate against the respective provider's API
  - [ ] **Building three real Git-provider integrations is substantial scope for a single story** — flagged here as a sizing observation, not a scope change: if implementation time is constrained, `GitHubAdapter` is the highest-value one to get fully correct first (most common host), with `GitLabAdapter`/`AzureReposAdapter` following the identical interface once the pattern is proven. All three are still asked for by this story as epics.md scopes it
- [ ] Task 2: Build `CIDeliveryActivity`, extending `GenerationWorkflow`'s fan-out a third time (AC: 1, 2)
  - [ ] Signature `CIDeliveryActivity(test_asset: TestAsset, application: Application) -> DeliveryResult` per Module Contracts — dispatched once per `TestAsset`, reusing the same per-item fan-out pattern Story 4.2 established for `PlaywrightGenerationActivity`
  - [ ] **If the Application has no `CIConfig` yet, skip delivery for this attempt as a no-op, not a failure.** This resolves a real secondary gap: nothing in the epics describes what happens to `TestAsset`s generated before a user ever visits Connect to CI/CD. The natural (if implicit) resolution given the mechanisms this system already has: a user who configures CI/CD after Journeys are already approved gets delivery on their *next* regeneration (Story 4.3), not retroactively on already-generated assets. There is no dedicated "manually trigger delivery" affordance anywhere in the epics — worth flagging as a possible future UX gap if pilot feedback wants one, but out of scope to build speculatively here
  - [ ] **AD-9 idempotency, concretely**: before creating a PR or commit, check for one already existing under a deterministic key derived from `journey_id` + `attempt` (e.g. a branch name like `aitest/{journey_id}/{attempt}` for PR mode, or a commit-message/marker check for direct-commit mode) — a retried Activity execution finds and reuses its own prior effect rather than creating a duplicate PR or double-committing
- [ ] Task 3: Wire the "Connected" status label (AC: 3)
  - [ ] Add a `connected` flag (or timestamp) to `CIConfig`, set on the Application's first successful `CIDeliveryActivity` execution
  - [ ] Connect to CI/CD screen reads this to show "Connected" beneath the selected provider card; unconnected providers show nothing (`EXPERIENCE.md`'s State Patterns table)
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1-3)
  - [ ] A `TestAsset` for an Application with a configured GitHub `CIConfig` produces a real PR or direct commit (per configured `export_mode`) in a test repository
  - [ ] Retrying the same delivery (simulating an Activity retry for the same `journey_id`+`attempt`) does not create a duplicate PR/commit
  - [ ] An Application with no `CIConfig` configured completes its `GenerationWorkflow` without error, simply skipping delivery
  - [ ] The Connect to CI/CD screen shows "Connected" only after a real successful delivery, not merely after configuration (Story 5.1)

## Dev Notes

- **This is the third and largest fan-out extension of `GenerationWorkflow`** (after Story 4.2's Scenario→TestAsset fan-out) — read Stories 4.1-4.3's Dev Notes on the workflow's current shape before adding this stage.
- **AD-4's Git-host-not-CI-system selection rule is easy to get subtly wrong once Story 5.3 exists alongside this one** — a Jenkins-on-GitHub Application must still resolve `GitHubAdapter` here, never branch on the configured CI system. If this story and 5.3 are implemented close together, double-check neither accidentally cross-wires the two selection keys.
- **The "no CIConfig yet, skip delivery" resolution is a judgment call worth surfacing**, not a certainty — flagged explicitly in case product feedback later wants an explicit "deliver now" action instead of relying on regeneration as the implicit retry mechanism.
- **Distinguish "Connected" (this story, AC 3) from "configured" (Story 5.1)** — a `CIConfig` can exist (host/mode/repo selected) without ever having successfully delivered anything; don't conflate the two states in the UI or the data model.

### Project Structure Notes

- Implements `packages/delivery_adapters` (previously stubbed interface-only from Story 1.1), adds `CIDeliveryActivity` to `apps/workers/generation`, extends `GenerationWorkflow`, and extends the Connect to CI/CD screen (Story 5.1) with the "Connected" label. No new top-level directories.
- **Depends on Epic 1-4 and Story 5.1 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.2: Deliver Test Assets via Pull Request or Direct Commit]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-19]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-4, #AD-9, #Module Contracts — DeliveryAdapter]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#State Patterns — CI/CD provider connected]
- [Source: _bmad-output/implementation-artifacts/5-1-configure-git-host-export-mode-per-application.md — `CIConfig`'s `repo_identifier`/`secret_ref` this story depends on]
- [Source: _bmad-output/implementation-artifacts/4-2-generate-playwright-test-assets-from-scenarios.md — the per-item fan-out pattern this story's `CIDeliveryActivity` dispatch reuses]

## Previous Story Intelligence

Epics 1-4 and Story 5.1 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 5.1 is implemented, check its File List for the exact `CIConfig` schema (especially `repo_identifier`/`secret_ref` field names) before building the adapters here.

## Latest Technical Notes

- No specific GitHub/GitLab/Azure DevOps API client library is architecture-pinned — verify current-stable SDKs/API versions for each provider at implementation time (these vendor APIs change independently of this project's own stack).

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
