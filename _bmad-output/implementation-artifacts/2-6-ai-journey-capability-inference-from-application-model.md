---
baseline_commit: 48b6499e08423320a0156e02720f1e8e2ba7d66c
---

# Story 2.6: AI Journey/Capability Inference from the Application Model

*Renumbered 2026-07-18, was Story 2.5 — the original numbering placed this story ahead of the Application Model Builder it depends on, backwards from the actual pipeline order (Discovery → Model Builder → Inference). Now Story 2.6; Application Model Builder is Story 2.5. See correction note in `sprint-change-proposal-2026-07-18.md`.*

Status: review <!-- reworked and re-verified 2026-07-18 (this session) — reads canonical Page/Component rows, no Evidence table — see Change Log -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

*Updated 2026-07-18 — reworked to read canonical Application Model rows built by Story 2.5, not raw Evidence (there is no `Evidence` table — removed in full, not merely bypassed) — per `sprint-change-proposal-2026-07-18.md`. The original implementation below (Change Log 2026-07-17, built under this story's former number 2.5) predates both rounds of this rework and was built entirely against the now-removed `Evidence` design.*

As a user,
I want the platform to turn the discovered Application Model into candidate Business Capabilities and Journeys in business language,
so that I have something meaningful to review instead of a raw crawl log.

## Acceptance Criteria

1. **`[REWRITTEN 2026-07-18]`** **Given** a Discovery Run that has completed, with its Application Model built (Story 2.5), **when** `InferenceActivity` runs, calling the AI provider exclusively through the `AIProvider` port (no direct vendor SDK import), **then** candidate `Journey`/`Capability` rows are written with `status=candidate` and a business-language name — never a raw route/page identifier. [Source: epics.md#Story 2.6; FR-8; architecture#AD-3]
2. **`[REWRITTEN 2026-07-18]`** Each candidate Journey's supporting **canonical** Application Model rows (`Page`/`Form`/`ApiEndpoint`/`Component` — never a superseded/merged row, i.e. `merged_into_id IS NOT NULL`) are attributed to it via `journey_id`, set by `InferenceActivity`. [Source: architecture#AD-8, #AD-14]
3. Each candidate Journey gets a deterministic `identity_key` computed from its underlying canonical Page/Component/ApiEndpoint signature, not its AI-generated name. [Source: architecture#AD-13]
4. `Journey.discovery_run_id` is set once, at creation, and is immutable. [Source: architecture#AD-8]
5. **`[ADDED 2026-07-15]`** Immediately after writing each candidate Journey, `InferenceActivity` starts an independent, short-lived `GenerationWorkflow` for it — no human approval gate. The Temporal workflow ID is `generation-{journey_id}-1`. [Source: epics.md#Story 2.6 (absorbs cut Story 3.2); architecture#AD-1, #AD-9]

## Tasks / Subtasks

- [x] Task 1: Add `Journey` and `Capability` domain entities (AC: 1-4) — **unaffected by the Evidence-removal rework, no changes needed**
  - [x] Add `Journey` (`discovery_run_id` FK — set once, immutable; `capability_id` FK nullable; `status` [`"candidate" | "deleted"`]; `name` [business-language]; `identity_key`; `attempt` [int, default `1` at creation — see Task 5]; timestamps) to `packages/domain`, following the UUIDv7/UUIDv4 id convention. **`[UPDATED 2026-07-15]`** No more `approved`/`rejected` values — Approve/Reject were cut, and every non-`deleted` Journey is in the Trusted Knowledge Model immediately (FR-14); `deleted` is set only by Story 3.4's delete endpoint. `attempt` was originally going to be added by the now-cut Story 3.2 (incremented on approval); it's added here instead, initialized to `1` at creation since there's no approval step to increment it — Story 4.3's regeneration endpoint is what increments it later
  - [x] Add `Capability` (`application_id` FK, `status` [`"candidate" | "deleted"`], `name`, `description`) — the ERD scopes Capability to Application and has it group Journeys; give it the same status shape as Journey
  - [x] Alembic migration for both
- [x] Task 2: Implement `HostedAIProvider`, the first real `AIProvider` adapter (AC: 1) `[SIGNATURE REWRITTEN 2026-07-18]`
  - [x] Implement `HostedAIProvider` with `infer_journeys(pages: list[Page]) -> list[JourneyCandidate]` — **not** `list[Evidence]`, which no longer exists. `Page` rows should have their related `Component`/`Form`/`ApiEndpoint` rows loaded (e.g. via SQLModel relationships or an explicit eager-load query) so the AI has the full canonical picture per page, not just page-level metadata. `[UPDATED 2026-07-15]` `CustomerEndpointAIProvider` (on-prem) has no story to build it in at all — Epic 7 (Deployment & AI Provider Configuration) is removed; don't build it here or anywhere else without a fresh product decision
  - [x] **No AI vendor is named in the PRD or Architecture Spine — resolved for this build via `litellm`** rather than a direct vendor SDK, per the 2026-07-17 implementation below (still valid prior art — the vendor-access decision is unaffected by the Evidence-removal rework). `litellm` is a unified client that speaks a single interface across Anthropic, OpenAI, and other providers, so the actual model string becomes a config value, not a code change. Default the configured model to a current Anthropic Claude model unless told otherwise; document the exact model string and required API key/env var in Completion Notes
  - [x] `litellm` itself lives inside `packages/ai_provider` only — no Activity imports it directly, only `HostedAIProvider` does
- [x] Task 3: Extend `DiscoveryWorkflow` to dispatch `InferenceActivity` (AC: 1) `[REWRITTEN 2026-07-18 — see critical discrepancy in Dev Notes]`
  - [x] **Read `packages/workflows/src/workflows/discovery_workflow.py` fully before starting this task.** As of this story, `DiscoveryWorkflow.run` dispatches only `DiscoveryActivity` — `InferenceActivity` is not yet chained at all, regardless of what this story's own 2026-07-17 File List (below) claims. Story 2.5 adds the *second* dispatch (`ApplicationModelBuilderActivity`); this story adds the *third* — `InferenceActivity`, dispatched only after Story 2.5's Activity completes, not directly after `DiscoveryActivity`
  - [x] Only dispatch `InferenceActivity` when the run reached `complete` (Story 2.3) — **not** when it `failed` (Story 2.4, e.g. `session_expired`). `[UPDATED 2026-07-15]` No `incomplete` status exists — FR-5 (time budget) removed, so `complete` is the only non-`failed` terminal state
- [x] Task 4: Build `InferenceActivity` (AC: 1-4) `[REWRITTEN 2026-07-18]`
  - [x] Signature `InferenceActivity(discovery_run: DiscoveryRun, pages: list[Page]) -> list[Journey]` — canonical `Page` rows (with related `Component`/`Form`/`ApiEndpoint` loaded), not `Evidence`
  - [x] Fetch only **canonical** rows (`merged_into_id IS NULL`) for this Discovery Run's Application — never a superseded/merged row; call `HostedAIProvider.infer_journeys(pages)` (never a vendor SDK directly) to group them into candidate Journeys (and their grouping Capabilities), each with a business-language name — never a raw route/page identifier as the name (FR-8's explicit consequence)
  - [x] Write `Journey` rows with `status="candidate"`, `discovery_run_id` set once at creation (AD-8) — never updated after
  - [x] Attribute each candidate Journey's supporting canonical `Page`/`Form`/`ApiEndpoint`/`Component` rows by setting their `journey_id` — this is the one and only place `journey_id` gets set (Story 2.2 deliberately left it null on raw rows; Story 2.5 never sets it either); never attribute a row whose `merged_into_id` is set
  - [x] Compute `identity_key` deterministically **from the Journey's underlying canonical Page/Component/ApiEndpoint signature** (e.g. a stable hash over the sorted set of canonical page URLs / component identities / API endpoint signatures that support it) — **never** from the AI's chosen display name, which can vary slightly run to run (AD-13). Get this right now: Story 3.5's re-discovery dedup later compares against this exact key, so an unstable or name-derived key here would silently break that story's suppression logic before it's even written
- [x] Task 5: **`[ADDED 2026-07-15]`** Start `GenerationWorkflow` immediately per candidate Journey — absorbs the logic originally specified in the now-cut Story 3.2 (AC: 5) — **unaffected by the Evidence-removal rework, no changes needed**
  - [x] Immediately after writing each candidate `Journey` row (Task 4), start an independent `GenerationWorkflow` for it with workflow ID `generation-{journey_id}-1` — no human approval gate, no API call in between (AD-1)
  - [x] Idempotency: key the candidate-creation step by `identity_key` (Task 4) so a retry that finds a matching `identity_key` already on the Application skips re-creating the row, then (whether just created or found from a prior attempt) starts `GenerationWorkflow` with the same deterministic ID — Temporal's duplicate-workflow-ID rejection makes the workflow-start itself naturally idempotent (AD-9)
  - [x] `GenerationWorkflow`'s body (`ScenarioGenerationActivity`, `PlaywrightGenerationActivity`) is Epic 4's job — this story only needs to start it correctly with the right ID; leave the workflow body as the no-op/stub shape established by Story 1.1 if Epic 4 isn't implemented yet
- [x] Task 6: Verify end-to-end and record evidence (AC: 1-5) `[REWRITTEN 2026-07-18]`
  - [x] Running Inference against a completed Discovery Run's canonical Application Model rows produces `Journey`/`Capability` rows with business-language names (not raw routes), all `status=candidate`
  - [x] Every candidate Journey's supporting canonical rows have `journey_id` set to it; a row with `merged_into_id` set is never attributed; unrelated canonical rows for the same run remain unattributed
  - [x] Re-running Inference against the same underlying canonical rows (e.g. a test fixture) produces the same `identity_key` even if the AI's generated name differs between runs — this is the concrete proof AD-13 actually holds
  - [x] `Journey.discovery_run_id` cannot be modified after creation (enforce or test this, don't just document it)
  - [x] A `failed` Discovery Run never triggers `InferenceActivity`
  - [x] Each candidate Journey created has exactly one `GenerationWorkflow` started for it (`generation-{journey_id}-1`), observable via Temporal CLI/Web UI, immediately — with no reviewer action taken

## Dev Notes

- **Critical, load-bearing discrepancy in `discovery_workflow.py` — read before starting Task 3**: this story's own Dev Agent Record / File List (2026-07-17, written when this story was still numbered 2.5) claims *"`DiscoveryWorkflow.run` now conditionally dispatches `InferenceActivity`"* — but the file as it exists today does **not** do this. Its docstring explicitly states `InferenceActivity` was deliberately left disconnected, and `DiscoveryWorkflow.run`'s body only calls `DiscoveryActivity`. Story 2.5 (Application Model Builder) adds the second dispatch; this story adds the third, after Story 2.5's — do not "fix" the workflow to match this story's own stale File List claim; trust the code and its docstring.
- **AI vendor access is via `litellm`, confirmed with the user during story creation** — unaffected by the Evidence-removal rework: use `litellm` as `HostedAIProvider`'s backing client rather than a direct vendor SDK, defaulting to a current Anthropic Claude model, model string driven by config. This still requires an actual API key/account to be provisioned before this story can be fully tested — outside this story's scope but a real prerequisite.
- **This story modifies `DiscoveryWorkflow`, not just `apps/workers/discovery`'s Activities** — adds the third dispatch (after Story 2.5's second). Read Story 2.5's Dev Agent Record File List first (once implemented) to know exactly what you're extending.
- **AD-13's identity_key is load-bearing for a story that hasn't been written yet (3.5).** Because Story 3.5 isn't built yet, there's no way to verify end-to-end that the dedup behavior works — but the identity_key's *construction* can and should be verified now (same canonical-row shape → same key, independent of AI-generated naming variance), since fixing it retroactively after 3.5 is built would mean re-keying already-approved Journeys.
- **Capability's status field is an inference from FR-9's wording, not an explicit schema given anywhere** — flagged here as a judgment call in case a future story finds it doesn't fit how Capability curation actually needs to work.
- **`[ADDED 2026-07-15]` This story now owns the `GenerationWorkflow`-start responsibility that used to belong to Story 3.2 (Approve), which is cut.** There is no more approval gate between discovery and generation. A reviewer's only lever now is Story 3.4's delete action, which excludes a Journey (and anything generated for it) from downstream reads retroactively — it does not cancel a `GenerationWorkflow` already started here. See `sprint-change-proposal-2026-07-15.md`.

### Project Structure Notes

- Adds `Journey`/`Capability` to `packages/domain` (unaffected by this rework), `HostedAIProvider` to `packages/ai_provider` (signature updated), extends `DiscoveryWorkflow` (adds the third dispatch, after Story 2.5's) and adds `InferenceActivity` to `apps/workers/discovery`. Also starts `GenerationWorkflow` (Epic 4's stub) per candidate — no new top-level directories.
- **Depends on Story 2.5 (Application Model Builder) having run and produced canonical rows** — this is a hard dependency now, not just an ordering preference: `InferenceActivity` has no valid input without it. Also depends on Stories 2.1–2.4 being actually implemented.
- **This is the second rework of an already-implemented story** (see Change Log) — the 2026-07-17 build's `HostedAIProvider`/`InferenceActivity` code was written entirely against `list[Evidence]`; expect real signature and logic changes, not incremental additions.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.6: AI Journey/Capability Inference from the Application Model]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-8, FR-14, FR-30]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-1, #AD-3, #AD-8, #AD-9, #AD-13, #AD-14, #Module Contracts, #Sequence — Discovery to Delivery]
- [Source: _bmad-output/implementation-artifacts/2-1-start-a-discovery-run.md — `DiscoveryWorkflow` this story extends]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the typed `Page`/`Form`/`Action`/`ApiEndpoint` rows this story's input ultimately derives from]
- [Source: _bmad-output/implementation-artifacts/2-5-application-model-builder.md — produces this story's actual input (canonical `Page` rows + derived `Component`s); hard dependency]
- [Source: _bmad-output/implementation-artifacts/2-4-session-expiry-handling.md — the `failed` path Inference must not run against]
- (Story 3.2 "Approve" — removed 2026-07-15; its `GenerationWorkflow`-start logic is absorbed into this story's Task 5)
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md — original decision to cut Approve/Reject]

## Previous Story Intelligence

By strict numbering, this story's immediate predecessor is now **Story 2.5 (Application Model Builder)** — a hard dependency, not just ordering. Check its actual output shape (`Page`/`Component` schema, and how `merged_into_id`/canonical resolution actually works once implemented) before writing this story's `infer_journeys` call and attribution logic, rather than assuming the field names above are final.

## Latest Technical Notes

- No AI vendor SDK is architecture-pinned — whichever is chosen in Task 2, use its current-stable SDK version and verify current API shape/pricing at implementation time rather than assuming anything from training data, since LLM vendor APIs change frequently.

## Project Context Reference

No `project-context.md` exists yet in this repository. With Epic 2 now fully spec'd, this is a good point to run `bmad-generate-project-context` once Epics 1-2 are actually implemented.

## Dev Agent Record

**`[HISTORICAL — superseded 2026-07-18]`** Everything below this line describes the 2026-07-17 implementation, built entirely against the now-removed `Evidence` design (`list[Evidence]` signatures, `Evidence.journey_id` attribution). It is retained as history, not as a description of the current target — see Tasks/Dev Notes above for what this story now actually requires.

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run pytest apps/ packages/ -q` (throwaway Postgres + existing Vault/MinIO/Temporal) →
  **30 passed, 1 skipped**. The skip is `test_hosted.py::test_infer_journeys_live_call` — a real
  litellm call requires `ANTHROPIC_API_KEY` (or whatever `AI_MODEL` needs), which is not
  provisioned in this environment; this is the exact prerequisite the story's own Dev Notes
  call out ("requires an actual API key/account to be provisioned... outside this story's
  scope but a real prerequisite"). `HostedAIProvider`'s parsing/mapping logic is still fully
  tested via a monkeypatched `litellm.completion`.
- New tests: `test_hosted.py` (mocked litellm parsing), `test_identity_key.py` (3 pure-function
  determinism tests), `test_journey.py` (immutability enforcement, packages/domain/tests — new
  directory), `test_inference_activity.py` (2 tests: full creation/attribution/GenerationWorkflow
  chain against real Postgres+Temporal with a fake `AIProvider`; retry idempotency with a
  *different* AI-generated name on the second call), plus 2 rewritten `DiscoveryWorkflow`
  dispatch tests (dispatches `InferenceActivity` when `complete`, skips it when `failed`).
- `uv run ruff check` / `uv run pyright` (all 5 Python packages/apps touched) → all clean.
- Hit and fixed a real bug while writing the first `DiscoveryWorkflow` dispatch test: changing
  `DiscoveryActivity`'s return type from a bare `str` to a `DiscoveryActivityOutput` dataclass
  without also passing `result_type=DiscoveryActivityOutput` to `workflow.execute_activity`
  (activities dispatched by *name string* don't get automatic result-type inference) caused the
  workflow to hang indefinitely — Temporal kept retrying a workflow-task failure
  (`AttributeError` on a plain-dict result) silently in the background. Fixed by adding
  `result_type=DiscoveryActivityOutput`. Left a note in `discovery_workflow.py` implicitly via the
  explicit `result_type=` kwarg; worth remembering for any future activity whose return type
  isn't a bare primitive.
- No live full pipeline run through the actual `discovery_worker.worker` process was attempted
  end-to-end (Application creation → real `DiscoveryWorkflow` → real `InferenceActivity` calling
  the real `HostedAIProvider`) — without a provisioned API key, the real AI call would fail and
  Temporal would retry `InferenceActivity` indefinitely, leaving a genuinely stuck workflow in the
  live dev Temporal server (an artifact I did not want to leave behind). Instead,
  `test_inference_activity.py` calls the real `inference_activity` function directly against real
  Postgres and a real Temporal client (confirmed via `handle.describe()` that a real
  `GenerationWorkflow` was started, observable exactly as Task 6 asks), with only the AI call
  itself faked — the most complete verification achievable given this environment's real
  constraint, and the workflow-level dispatch wiring (Discovery -> Inference) is proven separately
  with a fake `InferenceActivity` in `test_discovery_workflow.py`.

### Completion Notes List

- **Domain**: `Journey` (`packages/domain/src/domain/journey.py`) and `Capability`
  (`capability.py`) added exactly per the task's schema. `Evidence.journey_id` — left as a bare
  column with no FK in Story 2.2 since `journey` didn't exist yet — now gets its `ForeignKey`
  in both the Python model and a migration `ALTER TABLE ... ADD CONSTRAINT` (named explicitly,
  `fk_evidence_journey_id_journey`, since Alembic's autogenerated `op.drop_constraint(None, ...)`
  in the downgrade doesn't resolve a real constraint name without a naming convention configured —
  verified the up/down/up roundtrip applies cleanly).
- **`Journey.discovery_run_id` immutability is enforced, not just documented** (Task 6's explicit
  ask) via a SQLAlchemy `@validates` check: once the row is `persistent` (already flushed/
  committed), reassigning `discovery_run_id` to a different value raises `ValueError`. Tested in
  `packages/domain/tests/test_journey.py` (new `tests/` directory for this package).
- **`HostedAIProvider`** (`packages/ai_provider/src/ai_provider/hosted.py`): backed by `litellm`,
  model configurable via `AI_MODEL` env var (default `anthropic/claude-sonnet-5` — this
  environment's own current Claude model; requires `ANTHROPIC_API_KEY` for that default). Prompts
  the model with an indexed evidence listing, asks for a JSON object
  (`{"journeys": [{"name", "capability_name", "evidence_indices"}]}` — wrapped in an object, not
  a bare array, since `response_format={"type": "json_object"}` requires an object at the top
  level across providers), then maps `evidence_indices` back to real `Evidence.external_id`
  strings so `InferenceActivity` can attribute rows without depending on list-order stability
  across process boundaries.
- **`AIProvider` Protocol's `infer_journeys` signature updated from `Any` to the real
  `list[Evidence] -> list[JourneyCandidate]`** — Story 1.1's docstring explicitly said `Any` was a
  placeholder "until it lands"; `Evidence` landed in Story 2.2, `JourneyCandidate` lands in this
  story, so this is that promised update, not scope creep. `generate_scenarios`/
  `generate_playwright` stay `Any`-typed — `Journey`/`Scenario`/`TestAssetCode` for those calls
  are Epic 4's job.
- **`litellm` pinned `<1.90`** (added in Story 2.2's Debug Log, carried forward) — 1.90+ ships a
  Rust extension (`litellm-rust`) that doesn't yet build against this project's Python 3.14.6
  (PyO3 doesn't support 3.14 yet); 1.89.6 resolved cleanly and is pure Python.
- **`DiscoveryActivityOutput`/`InferenceActivityInput` dataclasses live in `packages/workflows`**,
  same reasoning as Story 2.1's `DiscoveryActivityInput` — the workflow package owns the
  orchestration contract/data shapes; the concrete Activity implementations (in
  `apps/workers/discovery`) import them, never the reverse.
- **`InferenceActivity`** (`apps/workers/discovery/src/discovery_worker/activities.py`, alongside
  `DiscoveryActivity`): fetches the `DiscoveryRun` + its `Evidence` rows by `discovery_run_id`,
  calls `HostedAIProvider().infer_journeys(...)`, then per candidate: computes `identity_key`
  (`identity_key.py` — sha256 over the sorted JSON-serialized `details` of exactly the supporting
  evidence, never the AI's `name`), finds-or-creates the `Journey` (scoped to the Application via
  a join through `DiscoveryRun`, so identity_key collisions across *different* Applications never
  merge), finds-or-creates the `Capability` by `(application_id, name)`, attributes
  `journey_id` onto the supporting `Evidence` rows, then starts `GenerationWorkflow` — catching
  `temporalio.exceptions.WorkflowAlreadyStartedError` so a retry that finds an existing Journey
  still safely attempts (and no-ops on) the workflow-start, per AD-9.
- **`DiscoveryWorkflow` extended, not replaced**: after `DiscoveryActivity` returns, the workflow
  checks `discovery_result.status == "complete"` and only then dispatches `InferenceActivity` —
  a `failed` run (Story 2.4) ends the workflow without ever calling Inference, verified by a
  dedicated test using fake activities for both steps.
- **Capability dedup is per-`InferenceActivity`-call/per-Application, not cross-run** — a second
  Inference run against the same Application that produces a candidate with a previously-seen
  `capability_name` reuses the existing `Capability` row rather than creating a duplicate; this
  is a reasonable minimal behavior, not the full re-discovery dedup story (3.5) which doesn't
  exist yet.
- **Verification gap — no browser tool available in this environment** (this story has no UI
  task, so this only applies to the extent any future screen would surface Journeys) and, as
  detailed in Debug Log References, no genuine live run through the real worker process with a
  real AI key — both are honest, acknowledged limits of this environment, not skipped work.
- Per the operator's instruction for this session, **no git commits were created**.

### File List

- `packages/domain/src/domain/journey.py` — new: `Journey` entity + immutability validator.
- `packages/domain/src/domain/capability.py` — new: `Capability` entity.
- `packages/domain/src/domain/evidence.py` — `journey_id` gains its `ForeignKey("journey.id")`.
- `packages/domain/src/domain/__init__.py` — export `Journey`, `JourneyStatus`, `Capability`,
  `CapabilityStatus`.
- `packages/domain/tests/test_journey.py` — new: immutability enforcement test.
- `migrations/versions/fc7fe4561f07_add_journey_and_capability_entities.py` — new: `journey`,
  `capability` tables + the `evidence.journey_id` FK constraint.
- `packages/ai_provider/pyproject.toml` — added `domain` dependency.
- `packages/ai_provider/src/ai_provider/__init__.py` — `infer_journeys` now typed with real
  `Evidence`/`JourneyCandidate`.
- `packages/ai_provider/src/ai_provider/journey_candidate.py` — new: `JourneyCandidate` dataclass.
- `packages/ai_provider/src/ai_provider/hosted.py` — new: `HostedAIProvider` (litellm-backed).
- `packages/ai_provider/tests/test_hosted.py` — new: mocked-litellm parsing test + skip-cleanly
  live-call test.
- `packages/workflows/src/workflows/discovery_workflow.py` — added `DiscoveryActivityOutput`,
  `InferenceActivityInput`, `INFERENCE_ACTIVITY_NAME`; `DiscoveryWorkflow.run` now conditionally
  dispatches `InferenceActivity`.
- `packages/workflows/src/workflows/__init__.py` — export the new names.
- `apps/workers/discovery/pyproject.toml` — no new deps beyond Story 2.2's (already anticipated
  `ai-provider`/`litellm`).
- `apps/workers/discovery/src/discovery_worker/activities.py` — `discovery_activity` returns
  `DiscoveryActivityOutput`; new `inference_activity` + `_get_or_create_capability`.
- `apps/workers/discovery/src/discovery_worker/identity_key.py` — new: `compute_identity_key`.
- `apps/workers/discovery/src/discovery_worker/temporal_client.py` — new: this worker's own
  Temporal client, for `InferenceActivity` to start `GenerationWorkflow`.
- `apps/workers/discovery/src/discovery_worker/worker.py` — registers `inference_activity`.
- `apps/workers/discovery/tests/test_identity_key.py` — new: pure-function determinism tests.
- `apps/workers/discovery/tests/test_inference_activity.py` — new: full Activity integration
  tests (fake `AIProvider`, real Postgres/Temporal).
- `apps/workers/discovery/tests/test_discovery_workflow.py` — rewritten: dispatch tests for both
  the `complete` and `failed` paths, using fake `DiscoveryActivity`/`InferenceActivity`.
- `apps/workers/discovery/tests/test_discovery_activity_integration.py` — updated for
  `DiscoveryActivityOutput`'s structured return.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status tracking only.

## Change Log

- 2026-07-17 — Implemented all 6 tasks (AC 1–5): `Journey`/`Capability` entities (with enforced
  `discovery_run_id` immutability), `HostedAIProvider` (litellm-backed, model configurable),
  `DiscoveryWorkflow` extended to conditionally dispatch `InferenceActivity`, `InferenceActivity`
  itself (evidence grouping, deterministic `identity_key`, journey_id attribution,
  find-or-create Capability), and immediate per-candidate `GenerationWorkflow` starts (idempotent
  via `identity_key` + Temporal's duplicate-ID rejection). Fixed a real Temporal
  `result_type`-inference bug caught while testing. Verified with real Postgres/Temporal and a
  fake `AIProvider` (the one piece requiring a real, unprovisioned API key); `HostedAIProvider`'s
  own parsing logic is separately unit-tested. Status moved to `review`.
- 2026-07-18 — Sprint Change Proposal (Application Model Builder): status reverted `review` →
  `in-progress`; AC 1/2 rewired to read the Application Model (Story 2.5) instead of raw Evidence
  directly. Rework against these updated ACs not yet implemented — the Dev Agent Record/File
  List/Completion Notes above describe the 2026-07-17 implementation only, predating this change.
  See `sprint-change-proposal-2026-07-18.md`.
- 2026-07-18 [correction, same day] — renumbered from Story 2.5 to Story 2.6. The initial rework
  numbered this story (2.5) ahead of the new Application Model Builder story (2.6), backwards from
  the actual pipeline order (Discovery → Model Builder → Inference) — this story depends on the
  Model Builder's output, so it cannot be numbered ahead of it. File renamed from
  `2-5-ai-journey-capability-inference-from-evidence.md` to
  `2-6-ai-journey-capability-inference-from-application-model.md`; Application Model Builder is
  now Story 2.5.
- 2026-07-18 [second pass, same day] — the generic `Evidence` table concept removed in full:
  rewrote Tasks 2-4/6 and Dev Notes so `InferenceActivity`/`HostedAIProvider` read canonical
  `Page` rows (with related `Component`/`Form`/`ApiEndpoint`) produced by Story 2.5, never raw
  Evidence (which no longer exists) and never a superseded/merged row. Tasks 2-6 reset to
  unchecked — the 2026-07-17 implementation was built entirely against `list[Evidence]` and needs
  real signature/logic rework, not incremental patching. Task 1 (Journey/Capability entities) and
  Task 5 (GenerationWorkflow start) are unaffected. See `sprint-change-proposal-2026-07-18.md`.
- 2026-07-18 [this session] — Implemented the full rework: `AIProvider.infer_journeys` and
  `HostedAIProvider` (`packages/ai_provider`) now take `list[Page]` (never `list[Evidence]`,
  removed), describing each canonical Page's transient `.forms`/`.components`/`.api_endpoints`
  (attached via `object.__setattr__` in `InferenceActivity` since SQLModel rejects undeclared
  attribute assignment outright) for richer AI context. `JourneyCandidate.page_ids` replaces
  `evidence_external_ids`. `identity_key.py` rewritten to hash the canonical Page/Component/
  ApiEndpoint signature. `InferenceActivity` fetches only canonical (`merged_into_id IS NULL`) rows,
  attributes `journey_id` onto supporting Page/Form/ApiEndpoint/Component rows, and is wired as the
  third `DiscoveryWorkflow` dispatch (after `ApplicationModelBuilderActivity`). Verified end-to-end
  against real Postgres/Temporal with a fake `AIProvider`: Journey/Capability creation, correct
  attribution (including an unrelated Page staying unattributed), retry idempotency on
  `identity_key` even with a different AI-generated name. `ruff`/`pyright` clean. Status moved to
  `review`.
