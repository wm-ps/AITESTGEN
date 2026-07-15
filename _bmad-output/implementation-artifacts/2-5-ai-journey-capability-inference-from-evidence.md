# Story 2.5: AI Journey/Capability Inference from Evidence

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to turn captured discovery evidence into candidate Business Capabilities and Journeys in business language,
so that I have something meaningful to review instead of a raw crawl log.

## Acceptance Criteria

1. **Given** a Discovery Run that has completed, with captured Evidence, **when** `InferenceActivity` runs, calling the AI provider exclusively through the `AIProvider` port (no direct vendor SDK import), **then** candidate `Journey`/`Capability` rows are written with `status=candidate` and a business-language name — never a raw route/page identifier. [Source: epics.md#Story 2.5; FR-8; architecture#AD-3]
2. Each candidate Journey's supporting `Evidence` rows are attributed to it via `journey_id`, set by `InferenceActivity`. [Source: architecture#AD-8]
3. Each candidate Journey gets a deterministic `identity_key` computed from its evidence shape, not its AI-generated name. [Source: architecture#AD-13]
4. `Journey.discovery_run_id` is set once, at creation, and is immutable. [Source: architecture#AD-8]
5. **`[ADDED 2026-07-15]`** Immediately after writing each candidate Journey, `InferenceActivity` starts an independent, short-lived `GenerationWorkflow` for it — no human approval gate. The Temporal workflow ID is `generation-{journey_id}-1`. [Source: epics.md#Story 2.5 (absorbs cut Story 3.2); architecture#AD-1, #AD-9]

## Tasks / Subtasks

- [ ] Task 1: Add `Journey` and `Capability` domain entities (AC: 1-4)
  - [ ] Add `Journey` (`discovery_run_id` FK — set once, immutable; `capability_id` FK nullable; `status` [`"candidate" | "deleted"`]; `name` [business-language]; `identity_key`; `attempt` [int, default `1` at creation — see Task 5]; timestamps) to `packages/domain`, following the UUIDv7/UUIDv4 id convention. **`[UPDATED 2026-07-15]`** No more `approved`/`rejected` values — Approve/Reject were cut, and every non-`deleted` Journey is in the Trusted Knowledge Model immediately (FR-14); `deleted` is set only by Story 3.4's delete endpoint. `attempt` was originally going to be added by the now-cut Story 3.2 (incremented on approval); it's added here instead, initialized to `1` at creation since there's no approval step to increment it — Story 4.3's regeneration endpoint is what increments it later
  - [ ] Add `Capability` (`application_id` FK, `status` [`"candidate" | "deleted"`], `name`, `description`) — the ERD scopes Capability to Application and has it group Journeys; give it the same status shape as Journey
  - [ ] Alembic migration for both
- [ ] Task 2: Implement `HostedAIProvider`, the first real `AIProvider` adapter (AC: 1)
  - [ ] Story 1.1 stubbed only the `AIProvider` Protocol interface in `packages/ai_provider` — implement `HostedAIProvider` now with `infer_journeys(evidence: list[Evidence]) -> list[JourneyCandidate]` per the exact signature in the Architecture Spine's Module Contracts. `[UPDATED 2026-07-15]` `CustomerEndpointAIProvider` (on-prem) has no story to build it in at all — Epic 7 (Deployment & AI Provider Configuration) is removed; don't build it here or anywhere else without a fresh product decision
  - [ ] **No AI vendor is named in the PRD or Architecture Spine — resolved for this build via `litellm`** rather than a direct vendor SDK. `litellm` is a unified client that speaks a single interface across Anthropic, OpenAI, and other providers, so the actual model string (e.g. `anthropic/claude-...`, `openai/gpt-...`) becomes a config value `HostedAIProvider` reads at startup, not a code change — this dovetails with AD-3's whole reason for existing (swap the model/vendor without touching any Activity) and effectively gives that swappability at two layers: the `AIProvider` port itself, and `litellm` underneath it. Default the configured model to a current Anthropic Claude model unless told otherwise; document the exact model string and required API key/env var in Completion Notes
  - [ ] `litellm` itself lives inside `packages/ai_provider` only — it's the one package allowed to depend on it, same as AD-3's existing "no Activity imports a vendor SDK directly" rule, just satisfied one layer down (no Activity imports `litellm` either, only `HostedAIProvider` does)
- [ ] Task 3: Extend `DiscoveryWorkflow` to dispatch `InferenceActivity` (AC: 1)
  - [ ] Per AD-1 and the Architecture Spine's own sequence diagram, `InferenceActivity` is a **second Activity dispatched from the same bounded `DiscoveryWorkflow`** built in Story 2.1 — not a new workflow. This is the step that makes `DiscoveryWorkflow` actually bounded/terminating, as AD-1 describes: "runs Discovery + Inference and terminates by writing candidate Journeys/Capabilities to Postgres"
  - [ ] Per the sequence diagram, only dispatch `InferenceActivity` when the run reached `complete` (Story 2.3) — **not** when it `failed` (Story 2.4, e.g. `session_expired`). A failed run has no reliable evidence set to infer from and the workflow should simply end after writing the failure status. `[UPDATED 2026-07-15]` No `incomplete` status exists — FR-5 (time budget) removed, so `complete` is the only non-`failed` terminal state
- [ ] Task 4: Build `InferenceActivity` (AC: 1-4)
  - [ ] Signature `InferenceActivity(discovery_run: DiscoveryRun, evidence: list[Evidence]) -> list[Journey]` per Module Contracts
  - [ ] Call `HostedAIProvider.infer_journeys(evidence)` (never a vendor SDK directly) to group this run's `Evidence` rows into candidate Journeys (and their grouping Capabilities), each with a business-language name — never a raw route/page identifier as the name (FR-8's explicit consequence)
  - [ ] Write `Journey` rows with `status="candidate"`, `discovery_run_id` set once at creation (AD-8) — never updated after
  - [ ] Attribute each candidate Journey's supporting `Evidence` rows by setting their `journey_id` — this is the one and only place `journey_id` gets set (Story 2.2 deliberately left it null); `DiscoveryActivity` must never set it
  - [ ] Compute `identity_key` deterministically **from the Journey's underlying evidence shape** (e.g. a stable hash over the sorted set of page URLs / action signatures / API call signatures that support it) — **never** from the AI's chosen display name, which can vary slightly run to run (AD-13). Get this right now: Story 3.5's re-discovery dedup later compares against this exact key, so an unstable or name-derived key here would silently break that story's suppression logic before it's even written
- [ ] Task 5: **`[ADDED 2026-07-15]`** Start `GenerationWorkflow` immediately per candidate Journey — absorbs the logic originally specified in the now-cut Story 3.2 (AC: 5)
  - [ ] Immediately after writing each candidate `Journey` row (Task 4), start an independent `GenerationWorkflow` for it with workflow ID `generation-{journey_id}-1` — no human approval gate, no API call in between (AD-1)
  - [ ] Idempotency: key the candidate-creation step by `identity_key` (Task 4) so a retry that finds a matching `identity_key` already on the Application skips re-creating the row, then (whether just created or found from a prior attempt) starts `GenerationWorkflow` with the same deterministic ID — Temporal's duplicate-workflow-ID rejection makes the workflow-start itself naturally idempotent (AD-9)
  - [ ] `GenerationWorkflow`'s body (`ScenarioGenerationActivity`, `PlaywrightGenerationActivity`) is Epic 4's job — this story only needs to start it correctly with the right ID; leave the workflow body as the no-op/stub shape established by Story 1.1 if Epic 4 isn't implemented yet
- [ ] Task 6: Verify end-to-end and record evidence (AC: 1-5)
  - [ ] Running Inference against a completed Discovery Run's Evidence produces `Journey`/`Capability` rows with business-language names (not raw routes), all `status=candidate`
  - [ ] Every candidate Journey's supporting `Evidence` rows have `journey_id` set to it; unrelated `Evidence` for the same run remains unattributed
  - [ ] Re-running Inference against the same underlying evidence shape (e.g. a test fixture) produces the same `identity_key` even if the AI's generated name differs between runs — this is the concrete proof AD-13 actually holds
  - [ ] `Journey.discovery_run_id` cannot be modified after creation (enforce or test this, don't just document it)
  - [ ] A `failed` Discovery Run never triggers `InferenceActivity`
  - [ ] Each candidate Journey created has exactly one `GenerationWorkflow` started for it (`generation-{journey_id}-1`), observable via Temporal CLI/Web UI, immediately — with no reviewer action taken

## Dev Notes

- **AI vendor access is via `litellm`, confirmed with the user during story creation** — this was the one open item in this story that wasn't a technical judgment call, and it's now resolved: use `litellm` as `HostedAIProvider`'s backing client rather than a direct vendor SDK, defaulting to a current Anthropic Claude model, model string driven by config. This still requires an actual API key/account to be provisioned before this story can be fully implemented and tested — that provisioning step is outside this story's scope but is a real prerequisite.
- **This story modifies `DiscoveryWorkflow`, not just `apps/workers/discovery`'s Activities** — Story 2.1 built the workflow to dispatch one Activity; this story adds the second (conditional) dispatch. Read Story 2.1's Dev Agent Record File List first to know exactly what you're extending.
- **AD-13's identity_key is load-bearing for a story that hasn't been written yet (3.5).** Because Story 3.5 isn't built yet, there's no way to verify end-to-end that the dedup behavior works — but the identity_key's *construction* can and should be verified now (same evidence shape → same key, independent of AI-generated naming variance), since fixing it retroactively after 3.5 is built would mean re-keying already-approved Journeys.
- **Capability's status field is an inference from FR-9's wording, not an explicit schema given anywhere** — flagged here as a judgment call in case a future story finds it doesn't fit how Capability curation actually needs to work (Epic 3's stories are about Journey curation specifically; if Capability handling turns out to need something different, that's worth revisiting there, not silently reworking here).
- **`[ADDED 2026-07-15]` This story now owns the `GenerationWorkflow`-start responsibility that used to belong to Story 3.2 (Approve), which is cut.** There is no more approval gate between discovery and generation — at the scale a real discovery run can produce (dozens to hundreds of candidates), requiring a human decision on every one before anything downstream can happen wasn't realistic. A reviewer's only lever now is Story 3.4's delete action, which excludes a Journey (and anything generated for it) from downstream reads retroactively — it does not cancel a `GenerationWorkflow` already started here. See `sprint-change-proposal-2026-07-15.md`.

### Project Structure Notes

- Adds `Journey`/`Capability` to `packages/domain`, `HostedAIProvider` to `packages/ai_provider` (previously stub-only from Story 1.1), extends `DiscoveryWorkflow` (Story 2.1) and adds `InferenceActivity` to `apps/workers/discovery`. **`[ADDED 2026-07-15]`** Also starts `GenerationWorkflow` (Epic 4's stub, per Story 1.1) per candidate — no new top-level directories.
- **Depends on Stories 2.1–2.4 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5: AI Journey/Capability Inference from Evidence]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-8, FR-14]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-3, #AD-8, #AD-9, #AD-13, #Module Contracts, #Sequence — Discovery to Delivery]
- [Source: _bmad-output/implementation-artifacts/2-1-start-a-discovery-run.md — `DiscoveryWorkflow` this story extends]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — `Evidence.journey_id` deliberately left null, attributed here]
- [Source: _bmad-output/implementation-artifacts/2-4-session-expiry-handling.md — the `failed` path Inference must not run against]
- (Story 3.2 "Approve" — removed 2026-07-15; its `GenerationWorkflow`-start logic is absorbed into this story's Task 5)
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md — original decision to cut Approve/Reject]

## Previous Story Intelligence

Stories 2.1–2.4 remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once implemented, check 2.1's File List for `DiscoveryWorkflow`'s exact structure before adding the `InferenceActivity` dispatch, and 2.2/2.3's for `Evidence`'s exact schema before writing the attribution logic.

## Latest Technical Notes

- No AI vendor SDK is architecture-pinned — whichever is chosen in Task 2, use its current-stable SDK version and verify current API shape/pricing at implementation time rather than assuming anything from training data, since LLM vendor APIs change frequently.

## Project Context Reference

No `project-context.md` exists yet in this repository. With Epic 2 now fully spec'd, this is a good point to run `bmad-generate-project-context` once Epics 1-2 are actually implemented.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
