---
name: 'Vantage (AITestGen)'
type: architecture-spine
purpose: build-substrate
altitude: initiative
paradigm: 'Durable Orchestrated Pipeline (Temporal) with Ports & Adapters at the boundaries'
scope: 'Vantage as built today: sign-in and org-scoped workspace, application onboarding, discovery (Explorer by default; the classic crawler with AI journey inference for older applications), journey curation, scenario and Playwright test generation, plain-English and recorded test cases, test execution with self-healing, flaky flags, Allure reports, run emails and schedules, and workspace administration (team, roles, settings, activity).'
status: final
created: '2026-07-13'
updated: '2026-10-27'
snapshot: 'branch feature-crawl2.0 @ 460f8e4 (includes the Explorer merge 2d88b20)'
sources:
  - 'current code, config, migrations and git history (verified 2026-10-27)'
  - 'docs/DISCOVERY_ENGINE_V2.md (classic crawl-engine design spine, matches the code)'
  - 'docs/vantage-explorer/ (Explorer design notes; this spine is grounded in the code, not those notes)'
companions: []
---

# Architecture Spine — Vantage (AITestGen)

This spine describes the system as it exists on 2026-10-27. Every decision below is backed by current code; decisions that were reversed are listed only in **Decisions retired** at the end.

## Design Paradigm

**Durable Orchestrated Pipeline with Ports & Adapters at the boundaries.** The product's long-running work (discover → infer → generate → execute → heal → report) runs as Temporal Workflows. Workflows coordinate only; Temporal Activities in the worker apps own every side effect (browser automation, LLM calls, DB writes, S3, Vault, SMTP, subprocesses). Everything external sits behind a small adapter package: the LLM (`packages/ai_provider`), secrets (`packages/secrets_client`), object storage (`packages/object_store`) and email (`packages/mailer`). The one deliberate exception is the Explorer module (AD-22), which has its own LLM client and its own email helper. Human actions (rename/delete a journey, trigger generation, run tests, change settings) are ordinary CRUD through the API, never a paused workflow.

Layer → namespace map:

| Layer | Namespace | Role |
| --- | --- | --- |
| Presentation | `apps/web` | React SPA; renders state, polls the API, mirrors role permissions |
| Command/Query surface | `apps/api` | Auth, org scoping, CRUD, starts/queries/cancels Temporal workflows, read-time derivations (flaky flags, coverage report, activity feed) |
| Orchestration | `packages/workflows` | Temporal workflow definitions + pure helpers (`heal_policy`, `failure_explainer`); no I/O (AD-2) |
| Execution | `apps/workers/explorer`, `apps/workers/discovery`, `apps/workers/generation`, `apps/workers/execution` | Temporal workers; all I/O-performing Activities. The Explorer worker keeps its workflow in the worker package (`explorer_worker/workflow.py`), not in `packages/workflows` |
| Interactive service | `apps/workers/recording` | Not a Temporal worker: FastAPI + websockets for Record & Play |
| Adapters | `packages/ai_provider`, `packages/secrets_client`, `packages/object_store`, `packages/mailer` | Insulate the domain from LiteLLM, Vault, S3 and SMTP |
| Shared engines | `packages/safety_classifier`, `packages/locator_capture`, `packages/playwright_typecheck`, `packages/test_suite_assembler` | Pure or subprocess-bound helpers shared by several workers |
| Domain | `packages/domain`, `packages/explorer_core` | SQLModel entities shared by API and workers; `explorer_core` holds the `explorer_*` tables, constants (task queue, statuses) and Explorer's email helper |

```mermaid
flowchart LR
    web[apps/web] -->|JSON/HTTPS, cookie session| api[apps/api]
    web -->|websocket noVNC + control| rec[apps/workers/recording]
    api --> domain[packages/domain]
    api -->|start/query/cancel| temporal[(Temporal)]
    api --> rec
    temporal --> expl[explorer worker<br/>default discovery engine]
    temporal --> disc[discovery worker<br/>classic crawler]
    temporal --> gen[generation worker<br/>+ live-exploration queue]
    temporal --> exe[execution worker]
    disc & gen & exe --> domain
    expl --> domain
    expl --> ecore[packages/explorer_core]
    api --> ecore
    disc & gen & exe --> ai[packages/ai_provider → LiteLLM proxy]
    expl -->|own httpx client, explorer_worker/llm.py| litellm[LiteLLM proxy]
    disc & exe & rec & expl --> secrets[packages/secrets_client → Vault]
    disc & exe --> s3[packages/object_store → S3]
    expl -.->|page screenshots only, if configured| s3
    exe --> mail[packages/mailer → SMTP]
    api --> mail
    ecore -->|explorer_core/notify.py| smtp[SMTP]
```

## Invariants & Rules (Architecture Decisions)

### AD-1 — Discovery is one bounded workflow; generation is an explicit, separate trigger

- **Two discovery engines.** `apps/api/src/api/discovery.py` reads `EXPLORER_REPLACES_DISCOVERY` (default `"1"`; `"0"` restores the crawler). While it is on, every fresh (non-resume) `start_discovery_run` — including the one `create_application` starts — calls `api.explorer.begin_run`, which starts `ExplorerRunWorkflow` (AD-22) and mirrors a `DiscoveryRun` row to `running` (stage `explorer`). If the Explorer queue has no pollers, it writes `DiscoveryRun(status="failed", stage="explorer", failure_reason="worker_unavailable")`. The classic crawler below now runs only when the flag is `0`, or to resume a crawler run. `ApplicationRead.discovery_engine` is `"explorer"` once **any** `explorer_run` exists for the application, otherwise `"crawler"`; the web uses it to hide Journeys/Scenarios and show the Explorer tab.
- **Rule (classic crawler):** `DiscoveryWorkflow` (queue `discovery-task-queue`) runs `DiscoveryActivity` → `ApplicationModelBuilderActivity` → `InferenceActivity` and ends. It does **not** start generation. Scenario generation starts only when the user triggers it (`POST /applications/{id}/generate-scenarios`), which starts one `GenerationWorkflow` per Journey with id `generation-{journey_id}-{attempt}`; suite (Playwright code) generation is a separate `SuiteGenerationWorkflow` (`suite-{journey_id}-{attempt}`). Curation (rename/delete) is plain CRUD and never touches a workflow.
- **Discovery is optional per application:** `Application.discovery_required=false` creates the application with no discovery run; test cases then come only from plain-English authoring or recording.
- **Explorer is the deliberate exception to "no human wait inside a workflow":** `ExplorerRunWorkflow` waits up to 14 days for the `brief_confirmed` signal (AD-22). It still never starts generation; it promotes proven scenarios and stops, and the user presses Generate tests.
- **Prevents:** human latency inside workflow history; a crawl silently spending LLM budget on journeys nobody kept.

### AD-2 — Workflows orchestrate only; Activities own all I/O

- **Rule:** `packages/workflows` contains no network, DB, browser, LLM, filesystem or wall-clock calls — only Activity calls, child workflows, timers and signals. Pure decision helpers that need no I/O (`heal_policy.py`, `failure_explainer.py` rules) live there too.
- **Prevents:** Temporal replay non-determinism.

### AD-3 — Every LLM call goes through one `AIProvider` port, over a LiteLLM proxy

- **Rule:** No worker or API module imports a vendor SDK. `packages/ai_provider` defines the `AIProvider` Protocol; its only implementation, `HostedAIProvider`, POSTs `/chat/completions` via httpx to a LiteLLM proxy (`LITELLM_BASE_URL`, `LITELLM_API_KEY`). The model is an alias (`AI_MODEL`; prod `gpt-5.6-luna`, code default `anthropic/claude-sonnet-5`), with one GPT-specific request-param branch. Prompts are inline in `hosted.py`.
- **Port methods (Protocol):** `infer_journeys`, `generate_scenarios`, `infer_state_similarity`, `classify_action_safety`, `decide_live_exploration_action`, `generate_playwright` (also used for typecheck repair and self-heal). `analyze_test_case_prompt` and `explain_test_failure` exist only on `HostedAIProvider`, not on the Protocol.
- **Exception — Explorer:** `apps/workers/explorer/src/explorer_worker/llm.py` deliberately does not use `packages/ai_provider`. It POSTs to `{LITELLM_BASE_URL}/chat/completions` itself (httpx, `response_format: json_object`, images as base64 JPEG, 3 attempts with backoff, 240 s timeout, raises `LLMError` when `LITELLM_BASE_URL` is unset). Two model tiers: `EXPLORER_THINKING_MODEL` (default `gpt-5.6-sol`; reading screens, writing the App Summary) and `EXPLORER_FAST_MODEL` (default `gpt-5.6-luna`; quick choices). Prompts live in `brain.py`. It still uses no vendor SDK and still goes through the same LiteLLM proxy, so the lock-in goal holds; what is lost is the single port.
- **Prevents:** vendor lock-in and SDK churn; swapping models is a config change.

### AD-4 — LangGraph + Playwright MCP is confined to live exploration

- **Rule:** LangGraph is used in exactly one place: `apps/workers/generation/.../live_exploration/agent.py`, a `StateGraph` observe → decide → act loop for plain-English test cases. The browser is driven through Playwright MCP (`@playwright/mcp@0.0.41`, stdio subprocess); decisions come from `AIProvider`. It runs on its own queue (`live-exploration-task-queue`, a second `Worker` in the generation process). The crawler and the self-heal loop use in-process Playwright, not MCP.
- **Prevents:** agent-framework sprawl into deterministic pipelines.

### AD-5 — Target-application credentials live only in Vault

- **Rule:** Target-app login credentials and SSO `storageState` JSON are written/read only through `packages/secrets_client` (hvac, Vault KV v2 at `secret/`). `Application.secret_ref` stores the path, never the value. The execution worker resolves credentials into the Playwright subprocess environment only; generated/downloaded projects read them from `process.env.*`.
- **Explorer roles:** extra test accounts per application (`explorer_role`) are stored in Vault the same way; the row keeps only `secret_ref`, and `DELETE /explorer/roles/{id}` deletes the Vault secret.
- **Sign-in switch:** `PATCH /applications/{id}/requires-login` (admin) turning sign-in off writes an empty storageState (`{"cookies":[],"origins":[]}`) to Vault and sets `auth_method="none"`; `PUT …/credentials` on a `none` app switches it back to `standard_login` with `requires_login=true`.
- **Not in Vault:** platform deployment secrets (k8s Secret `aitestgen-secrets`).
- **Prevents:** credentials in Postgres, logs or generated code.

### AD-6 — The FastAPI OpenAPI spec is the frontend/backend contract

- **Rule:** `apps/web/src/api-types.gen.ts` is generated by `openapi-typescript` from `apps/api`'s `/openapi.json`; a CI job fails on drift. Known exception: a few fields (`role`, `discovery_required`) are hand-patched in `api.ts` pending regeneration.

### AD-7 — One deletion path for journeys

- **Rule:** Only the API (`DELETE /journeys/{id}`) moves a Journey to `status=deleted`. Workers write `candidate` only. Deleted journeys are excluded from downstream reads; nothing already generated is cancelled.

### AD-8 — Discovery captures typed rows; the Model Builder merges to canonical

*Classic crawler only. Explorer keeps its own `explorer_*` tables (AD-22) and stores its screenshots and videos as bytes in Postgres, not S3.*

- **Rule:** `DiscoveryActivity` writes typed rows (`page`, `form`, `form_field`, `validation_rule`, `action`, `api_endpoint`, `page_transition`), each scoped by `application_id` and `discovery_run_id`, with `merged_into_id = null`. There is no generic Evidence table. Screenshots go to S3 (`discovery-runs/` prefix); Postgres stores the key.
- `ApplicationModelBuilderActivity` is the only writer of `merged_into_id` (cross-run, per Application) and the only writer of derived `component`, `component_locator`, `assertion` rows (idempotent find-or-create).
- `InferenceActivity` is the only writer of `journey`, `journey_step`, `capability` and of `journey_id` attribution on canonical rows.

### AD-9 — Side-effecting Activities are idempotent under at-least-once retry

- **Rule:** Deterministic workflow ids (`generation-{journey_id}-{attempt}`, `suite-…`, `regenerate-{scenario_id}`, `autofill-{scenario_id}`, `heal-{test_result_id}`) let Temporal's duplicate-id rejection absorb double clicks. `EnsureTestSuiteActivity` is fetch-or-create. Run-completed email is claimed once (lost rather than duplicated). Journey creation is keyed by `identity_key` (AD-13).

### AD-10 — Run state is a first-class, queryable column, never inferred

- **Discovery:** `discovery_run.status` ∈ `running | paused | complete | failed`; `stage` ∈ `initializing | authenticating | discovering | analyzing | analyzed`; `stop_reason` ∈ `exhausted | max_pages | max_duration` tells a full crawl from a capped one; `source` ∈ `crawler | live_exploration`.
- **Explorer:** `explorer_run.status` ∈ `queued | signing_in | understanding | summarizing | awaiting_confirmation | confirmed | planning | exploring | explored | hunting | testing | tested | failed | stopped | paused | expired`. `ACTIVE_RUN_STATUSES` (queued … testing, minus `explored`/`tested`) allows one active run per application. Mission, test-case and question rows carry their own status columns (AD-22). The Explorer UI polls `/events?after=<id>` every 1.5 s and the run every 2.5 s, using `explorer_event`'s bigint identity as the cursor.
- **Test runs:** `test_run.status` ∈ `pending | running | completed | blocked | cancelled`; `test_result.status` ∈ `pending | passed | failed | timed_out | errored | blocked | cancelled`.
- The web polls these; percentages are presentation-only.

### AD-11 — Failures are typed, small, and plain-English

- **Discovery:** a fixed `discovery_error` taxonomy, DISC-001 (Temporal restart) … DISC-006 (form-field resolution timeout), each with code + human message. Session loss mid-crawl triggers bounded re-login (`_MAX_CONSECUTIVE_REAUTH_ATTEMPTS=3`) before failing.
- **Service availability:** before starting a workflow the API checks `has_pollers(task_queue)` and returns 503 with a machine code (`DISCOVERY_/GENERATION_/EXECUTION_/LIVE_EXPLORATION_/EXPLORER_UNAVAILABLE`; `EXPLORER_UNAVAILABLE` is handled inside `ExplorerTab.tsx`, not `errorCodes.ts`); a failed Temporal Schedule call returns 502 `SCHEDULE_BACKEND_UNAVAILABLE`. The web maps codes in `errorCodes.ts`.
- **Test failures:** `failure_explainer.py` regex rules give a deterministic title/detail and a run-level root-cause category; unmatched errors go to the LLM once and are cached in `failure_explanation` by `error_fingerprint` of the redacted text.
- **Credentials:** `VerifyCredentialsWorkflow` performs a real login before discovery starts (`valid | invalid | uncertain`).

### AD-12 — Every query is Organization-scoped through one dependency

- **Rule:** `current_org_id` (`CurrentOrgIdDep`) is the single tenant-scoping mechanism. Roles (`admin | member | viewer`) are org-wide. `block_viewer_writes` is a global FastAPI dependency that denies every POST/PUT/PATCH/DELETE for viewers except `/auth/logout` (deny by default); `NotViewerDep` also blocks the Allure report and suite download. `require_admin` gates team, invites, role changes, application edit/delete, credentials (list/reveal/verify/update), execution-policy update, Settings, the admin cleanup/reconcile triggers and the Activity feed. The web mirrors this in `PermissionsContext.tsx`.
- **Explorer gap:** the `/explorer` router (`apps/api/src/api/explorer.py`) guards every route with `CurrentOrgIdDep` only (`start_run` also takes `CurrentUserDep` to record the starter). The app-wide `block_viewer_writes` still applies, so viewers cannot change anything there. But nothing on that router uses `require_admin` or `NotViewerDep`: any member can add or delete role test accounts (Vault secrets), knowledge and documents, and a viewer can download the tests zip (`/runs/{id}/tests/download`), the report, mission recordings and the highlight video. Explorer actions also write nothing to `activity_event`.

### AD-13 — Journeys carry a deterministic `identity_key`

- **Rule:** `identity_key.py` derives a Journey's identity from its canonical page/component signature, not its AI name. Re-discovery suppresses duplicates and keeps original attribution.

### AD-14 — Crawl heuristics are deliberate, bounded sampling (see `docs/DISCOVERY_ENGINE_V2.md`)

*AD-14 and AD-15 describe the classic crawler only. Explorer's equivalents are in AD-22.*

- Pipeline: PREPARE → crawl loop (Observe → Identify → Enumerate → Decide → Act → Return) → CLOSE OUT, breadth-first.
- **State identity** (`state_identity.py`): SAME/VARIANT/NEW by route templating + fingerprint scoring; per-application thresholds (0.75/0.35); in-process cache, no Redis.
- **Sampling:** one action per distinct label (no per-page count cap; removed 2026-07-22); frames (depth 3), shadow DOM, popups, tabs; scroll/"load more" sampled, not exhausted; broken destinations excluded; nav retries `_MAX_NAV_RETRIES=2`.
- **Readiness:** network-quiet (ignores analytics/polling) + 300 ms DOM-stable + content check; page-load timeout default 15 s, per-app/per-run override; not settled → DISC-004.
- **Caps:** `DiscoverySettings.max_pages` (default 500) and `max_discovery_duration_minutes` (default 30) end a run with `stop_reason` recorded. `DiscoveryActivity` has a 6 h start-to-close and 2 min heartbeat.

### AD-15 — Planner order: loop guard → safety → data; the crawl never blocks

- **Rule:** `planner.py` tiers actions and runs a fixed chain (`loop_guard` → safety → data) yielding `execute | defer | skip`, gated by `interaction_level` (passive/normal/aggressive).
- **Safety** (`safety_engine.py` + `packages/safety_classifier`): Clearly Destructive is always refused; Ambiguous per `Application.safety_posture`. The AI safety consult exists but is not wired.
- **Data** (`data_resolver.py`): Test Data Pool → per-run reuse → safe synthesis → DEFER; every value is logged to `synthetic_data_entry`.
- **Blocked frontier:** DEFERs aggregate into `blocked_task` by `(application_id, aggregation_key)` with `exploration_step` rows as a human-readable record.
- **Pause/resume** of a run is exposed (`/pause-discovery`, `/resume-discovery`); both return 409 for Explorer applications (`_require_crawler_discovery` in `main.py`), which pause and resume through `/explorer/runs/{id}/pause|resume` instead. The separate re-crawl-from-entry-point `resume.py` exists but is not wired to any caller.

### AD-16 — Generated tests are TypeScript `@playwright/test`, gated by a real typecheck

- **Rule:** `PlaywrightGenerationActivity` produces a TS spec per Scenario, grounded on known pages and locators, then runs `tsc --noEmit` (`packages/playwright_typecheck`) with an AI repair loop, then `spec_linter.py`. Linter findings are flag-only (`needs_review` + warnings). Suite generation fans out in up to 3 waves with a 30 s cooldown. Recorded specs go through the same typecheck.
- **Explorer-proven code:** Explorer's promoted scenarios carry `grounding.proven_code`. `_proven_explorer_code` (generation `activities.py`) typechecks it and uses it as-is; only if it fails the typecheck does the normal `_generate_and_typecheck` path run. `spec_linter.resolve_requires_auth` trusts a boolean `grounding.requires_auth`. `_TEST_CALL_RE` has a lookbehind so it no longer matches `.test(` (e.g. regex `.test(` in a spec).
- **Three sources of scenarios:** `discovery` (crawl → journey → scenarios, or Explorer promote, which also writes `source="discovery"` and is told apart by `grounding.explorer_test`), `nl` (plain-English via live exploration, AD-4; the verification runs are discarded), `recorded` (Record & Play, AD-19).

### AD-17 — Execution runs the real Playwright CLI per spec, on one worker host per run

- **Rule:** `ApplicationTestExecutionWorkflow` → `PrepareTestRunActivity` assembles the project once (`test_suite_assembler`, local dir) → `ExecuteTestActivity` runs `npx playwright test` per spec (within-run `asyncio.Semaphore`, default 5) → `GenerateAllureReportActivity` → `FinalizeTestRunActivity` → `SendTestRunReportEmailActivity`. Artifacts (screenshot/trace/video) go to S3 under `test-runs/`.
- **One at a time:** `PrepareTestRunActivity` sets `PrepareTestRunActivityResult.one_at_a_time` when any scenario's `grounding.one_at_a_time` is true (Explorer sets it when it guesses the app keeps state per login, `sense.py` `keeps_state`); the workflow then uses a semaphore of 1.
- **Sign-in step:** the `--project=setup` auth step's timeout is 180 s for applications with discovery (was 60 s) and 150 s (`_AUTH_SETUP_TIMEOUT_NO_DISCOVERY_S`) without. `auth.setup.ts` (assembler) races "password field visible" against "URL left the login page" before checking `isAuthenticated`; when current `@auth` assets exist without a recorded login form, the assembler falls back to `generic_login_evidence`. The `@auth` failure hint fires only on failed/timedOut and appends the original error.
- **Skipped → blocked:** a Playwright `skipped` result is stored as `test_result.status="blocked"` with `blocked_reason` taken from the `test.fixme`/`test.skip` annotation (`_skip_reason`).
- The Allure step reads the local project dir, so a run must stay on one execution-worker host; the deployment is single-replica on purpose.
- Only one run per application at a time (`EXECUTION_IN_PROGRESS`).
- **Cancel:** the API marks run/results cancelled under a row lock, then cancels the workflow; activities heartbeat, watch the row and kill Playwright process trees; `CleanupCancelledTestRunActivity` runs; no report, no email.
- **Stale runs:** `ReconcileStaleTestRunsWorkflow` every 15 min.

### AD-18 — Self-healing never rewrites an assertion

- **Rule:** after every failed execute, `HealTestActivity` runs: evidence → AI diagnosis (+ `live_inspection.py` on the live page) → targeted edit → typecheck → assertion-change guard (`assertions.js`) → re-run.
- `heal_policy.py`: failures inside `expect(...)` are never healed; infra failures get one same-code retry with no AI.
- **Switch:** `AUTO_HEAL_ENABLED` (execution `activities.py`, default `"1"`; any other value turns automatic heals off, manual heals still run).
- **Known bugs are never healed:** heal is skipped when the scenario's `grounding.proven_code` contains `test.fixme(true` (an Explorer known-bug test).
- Budgets: automatic `AUTO_HEAL_ATTEMPT_CAP=2`; manual (`POST /test-results/{id}/heal`, `HealTestExecutionWorkflow`) capped by `DiscoverySettings.max_heal_attempts`.
- **Flaky** is computed at read time, not stored: a scenario is flaky if its last 10 completed (non-verification) results include at least one pass and one fail/timeout/error.

### AD-19 — Record & Play is a separate interactive service, not a workflow

- **Rule:** `apps/workers/recording` (FastAPI :8100) runs, per session, Xvfb + headed Chromium with `playwright codegen --target playwright-test` + x11vnc. RFB bytes are proxied in-process over `/recordings/{token}/vnc`; stop/cancel over `/recordings/{token}/control`. The web uses `@novnc/novnc` `RFB` directly.
- Tokens are minted by the API (sha256 stored, 30 min expiry). Pool: `RECORDING_MAX_CONCURRENT_SESSIONS=4`, max 60 min. `auth_mode=authenticated` pre-mints a storageState.
- Output is normalized, typechecked, and saved as a `recorded` Scenario + TestAsset.

### AD-20 — Schedules are Temporal Schedules; only test runs are scheduled

- **Rule:** user schedules (`daily | weekly | monthly | custom_cron`) are created by the API (`schedule_spec.py`) as Temporal Schedules with overlap=SKIP targeting `ScheduledExecutionWorkflow`, which checks `CheckScheduleGateActivity` and then runs the execution workflow as a child. Default zone `SCHEDULE_DEFAULT_TIME_ZONE` (prod Asia/Kolkata). Discovery is never scheduled.
- System schedules (daily cleanup `0 6 * * *` Asia/Kolkata; stale-run reconcile `*/15 * * * *`) are created by scripts, not at boot.

### AD-21 — Platform auth is a server-signed cookie, invite-only

- **Rule:** email + bcrypt password; session is an httpOnly `session` cookie signed with itsdangerous (`SESSION_SECRET_KEY`), samesite=lax, sliding 1 h idle expiry (re-issued per request, updates `last_active_at`). No self-signup: admin-issued single-use invites and password-reset tokens (sha256 stored). No platform SSO/OAuth/JWT. "SSO session reuse" is a *target-app* auth method only.

### AD-22 — Explorer is a separate module that hands only proven scenarios to the core pipeline

- **Shape:** worker `apps/workers/explorer/src/explorer_worker/` (package `explorer-worker`, Python ≥3.14), tables and constants in `packages/explorer_core`, API router `apps/api/src/api/explorer.py` (`/explorer`, 36 routes, mounted with `app.include_router(explorer_router)`), web `apps/web/src/explorer/` (`ExplorerTab`, `LiveView`, `SummaryView`, `ScreensView`, `ScenariosView`, `HealthView`, `QuestionsView`, `RolesPanel`, `explorerApi.ts`). Explorer reads only its own `explorer_*` tables while running; the core tables are written in one place, the promote stage.
- **Workflow:** `ExplorerRunWorkflow` on `explorer-task-queue`, id `explorer-run-{run.external_id}` (a "Not a bug" hand-off uses `…-send-{uuid4}`). Modes: `full` (understand → wait for `brief_confirmed` → plan_missions → mission pool → hunt → breadth → plan_tests → test pool → promote → reel), `missions` (pool → hunt → breadth, returns `explored`), `tests` (from plan_tests), `resume` (start step from `explorer_resume_point`), `send` (promote only). Mission and test pools run up to `MAX_PARALLEL=3`; retry policy `maximum_attempts=1`, a pool item that dies is requeued once. Hunt, breadth, plan_tests, promote and reel are "bonus" steps that log and continue on failure; any other non-cancel `ActivityError` runs `explorer_fail_run`. Pause and Stop cancel the workflow. Unconfirmed summaries expire after `CONFIRM_WAIT_DAYS=14` (`explorer_expire_run`; `expired` cannot be resumed). `MISSIONS_ADDED_SIGNAL` is defined but unused: adding a mission to an `explored` run starts a new `missions` execution.
- **Activities (18):** `explorer_understand_app` (2 h, 5 min heartbeat), `explorer_plan_missions` (15 min), `explorer_queued_missions`, `explorer_run_mission` (45 min), `explorer_finish_exploring`, `explorer_requeue_mission`, `explorer_hunt_hidden_screens` (40 min), `explorer_breadth` (40 min), `explorer_plan_tests` (20 min), `explorer_planned_tests`, `explorer_build_test` (45 min), `explorer_requeue_test`, `explorer_finish_testing`, `explorer_send_to_vantage` (promote, 10 min), `explorer_highlight_video` (20 min), `explorer_resume_point`, `explorer_fail_run`, `explorer_expire_run`.
- **Stages in code:** `understand.py` (first look, App Summary), `missions.py`/`pursue.py` (mission walking, risk gating), `hunt.py` (hidden screens), `breadth.py` (roles, unlinked pages, JS coverage), `tests_stage.py`/`testkit.py`/`quality.py` (7 test kinds: navigation, data_load, form_submission, validation, error_state, journey, page_quality; proving), `promote.py` (hand-off), `reel.py` (highlight video), `memory.py` (questions, knowledge), `browser.py` (Playwright), `sense.py` (heuristics), `session.py` (sign-in and session reuse), `journal.py` (events, run updates, email).
- **Hand-off (`promote.py`):** only `explorer_test_case.status="proven"` rows are promoted. It writes `DiscoveryRun` (source `crawler`, stage `explorer` → `analyzed`), `Journey` (`identity_key` `explorer:<slug>`), `JourneyStep`, `Page`, `Component`/`ComponentLocator`/`Form`/`FormField`, and `Scenario` (`source="discovery"`, `safety_classification="SAFE"`, type happy for navigation/data_load/form_submission/journey and negative for validation/error_state/page_quality, `grounding` = `{explorer_test, kind, proven: True, requires_auth, check, captured_flow, proven_code, one_at_a_time}`). It retires older `Scenario`/`TestSuite`/`TestAsset` rows (`current=False`). It **does not create TestAssets**: the user runs generation, which uses the proven code (AD-16). The `explorer_core/models.py` docstring saying Explorer "never reads or writes" the classic tables is stale for this step.
- **Limits:** `MAX_MISSIONS=15`, `MAX_TESTS=150` (test cap `clamp(15 × screens, 10, 150)`), `MAX_JOURNEYS=8`, `JOURNEY_STEPS=40`, promote `MAX_STEPS=12`; static-asset cache 30 min / 300 MB; signed-in session reused for 20 min. Tunables are env vars (see Configuration below).
- **Prevents:** a second discovery engine reaching into the classic crawler's tables, and unproven AI guesses becoming test cases.

## Consistency Conventions

| Concern | Convention |
| --- | --- |
| Naming | Entities singular PascalCase; tables snake_case singular (`test_run`, `discovery_run`); workflows `…Workflow`; activities `…Activity`; task queues `<area>-task-queue`. API JSON is snake_case (no camelCase aliasing). |
| IDs & dates | Internal PKs UUIDv7 (`server_default uuidv7()`, Postgres 18). API exposes a separate UUIDv4 `external_id`. Timestamps `timestamptz`, UTC. Per-app human counters: `next_test_run_number`, `next_test_case_number`. |
| Errors | FastAPI `{"detail": …}`; machine codes in `detail` where the web must branch (AD-11), free text otherwise. No RFC 7807 envelope. |
| Config | `os.environ` only (no settings library); k8s ConfigMap + Secret. Global runtime knobs live in the `discovery_settings` singleton (id=1), editable on the Settings page. Explorer's knobs are env-only (table below). |
| Logging | stdlib `logging` INFO to stdout; discovery observability is in DB (`diagnostic_record`, `discovery_error`, coverage report; for Explorer, `explorer_event`). |
| Busy UI / icons | Trailing `BouncingDots`, never spinners; vertical kebab menus (see CLAUDE.md). |
| Shortcuts | Deliberate bounded simplifications are tagged `ponytail:` in code with their ceiling (82 in tracked source: 66 before the Explorer merge plus 16 in Explorer). |

### Configuration added with Explorer

| Env var | Default | Read in |
| --- | --- | --- |
| `EXPLORER_REPLACES_DISCOVERY` | `1` (`0` = classic crawler) | `apps/api/src/api/discovery.py` |
| `AUTO_HEAL_ENABLED` | `1` (anything else = automatic heals off; manual heals still run) | `apps/workers/execution/src/execution_worker/activities.py` |
| `LITELLM_BASE_URL` / `LITELLM_API_KEY` | none (`LLMError` if the URL is unset) | `explorer_worker/llm.py` |
| `EXPLORER_THINKING_MODEL` / `EXPLORER_FAST_MODEL` | `gpt-5.6-sol` / `gpt-5.6-luna` | `explorer_worker/llm.py` |
| `EXPLORER_WORKER_MAX_CONCURRENT_ACTIVITIES` | `8` | `explorer_worker/worker.py` |
| `EXPLORER_WAIT_MINUTES` | `10` (`0` = never wait for an answer) | `explorer_worker/memory.py` |
| `EXPLORER_MISSION_STEPS` / `EXPLORER_TASK_PASSES` | `20` / `1` | `explorer_worker/missions.py` |
| `EXPLORER_PROOF_RUNS` | `1` (`0` = proving off) | `explorer_worker/tests_stage.py` |
| `EXPLORER_FIRST_LOOK_SCREENS` / `EXPLORER_REVISIT_SCREENS` / `EXPLORER_FIRST_LOOK_MINUTES` | `24` / `10` / `25` | `explorer_worker/understand.py` |
| `TEMPORAL_ADDRESS` | `localhost:7233` | `explorer_worker/worker.py` |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5433/aitestgen` | `explorer_worker/db.py` |
| `FRONTEND_BASE_URL`, `SMTP_HOST/PORT/USER/PASSWORD/FROM/FROM_NAME` | `http://localhost:5173`; SMTP unset = log instead of send | `explorer_core/notify.py` |

None of the `EXPLORER_*` or `AUTO_HEAL_ENABLED` variables is in `ops/k8s/01-configmap.yaml` (it already has `LITELLM_BASE_URL`), so a deployed API runs with `EXPLORER_REPLACES_DISCOVERY` on.

## Stack (locked versions, 2026-10-27)

| Layer | Name | Version |
| --- | --- | --- |
| Runtime | Python | 3.14.6 (`python:3.14-slim` images) |
| API | FastAPI / uvicorn | 0.139.0 / 0.51.0 |
| ORM / DB driver / migrations | SQLModel / SQLAlchemy / psycopg / Alembic | 0.0.39 / 2.0.51 / 3.3.4 / 1.18.5 |
| Database | PostgreSQL | 18.4 (local Docker); prod external host |
| Orchestration | Temporal Python SDK / server | 1.30.0 / `temporalio/admin-tools:1.31.2` `start-dev` |
| Browser | Playwright (Python) | 1.61.0 |
| Agent | LangGraph / langchain-core / mcp | 1.2.11 / 1.6.1 / 2.1.1; `@playwright/mcp@0.0.41` |
| LLM transport | httpx → LiteLLM proxy | httpx 0.28.1 (Explorer: model aliases `gpt-5.6-sol` / `gpt-5.6-luna`) |
| Document parsing (Explorer knowledge uploads) | pypdf | 6.20.1 (API dependency `pypdf>=5.0`; .docx is read by unzipping, no library) |
| Secrets / storage | hvac → Vault / boto3 → S3 | 2.4.0 → `hashicorp/vault:1.18` / 1.43.55 → AWS S3 |
| Misc Python | pydantic, bcrypt, itsdangerous, pillow | 2.13.4, 5.0.0, 2.2.0, 12.3.0 |
| Python tooling | uv workspace, ruff, pyright, pytest | ruff 0.15.21, pyright 1.1.411, pytest 9.1.1 |
| Web | React / Vite / TypeScript / Tailwind | 19.2.7 / 8.1.5 / 5.9.3 / 4.3.3 |
| Web libs | recharts, @novnc/novnc, FontAwesome, openapi-typescript | 3.10.1, 1.7.0, 7, ^7.13 |
| Web tooling | vitest, oxlint | 3.2.7, 1.74.0 |
| Web build/serve | Node / nginx | `node:22-alpine` / `nginx:1.27-alpine` |
| Generated projects | @playwright/test / allure / allure-playwright | ^1.48.0 / ^3.20.1 / ^3.13.0 |

See `reviews/review-version-currency.md` for the currency check of this table.

## Structural Seed

```text
apps/
  api/                 FastAPI: main.py (~5.8k lines) + auth, activity, coverage_report, discovery,
                       explorer (/explorer router, ~1.5k lines), invites, password_reset, recordings,
                       schedule_spec, temporal_client, test_suite_export, db;
                       src/api/scripts/ (seed, backfills, create schedules, smoke)
  web/                 React 19 + Vite 8 SPA; no router lib (pathname + shell state), no data lib
                       (fetch in src/api.ts + polling hooks); nginx in prod; src/explorer/ = Explorer tab
  workers/
    explorer/          explorer-task-queue: ExplorerRunWorkflow; understand, missions, pursue, hunt,
                       breadth, tests_stage, testkit, quality, promote, reel, memory, brain, llm,
                       browser, sense, session, mind, journal, resume, samples, db
                       (no Dockerfile, k8s manifest or Jenkinsfile yet)
    discovery/         discovery-task-queue: DiscoveryWorkflow, VerifyCredentialsWorkflow;
                       crawler, session, credential_check, state_identity, planner, safety_engine,
                       data_resolver, blocked_frontier, widgets, model_builder, journey_clustering,
                       identity_key, screenshot_quality, diagnostics
    generation/        generation-task-queue: GenerationWorkflow, SuiteGenerationWorkflow,
                       LiveExplorationTestWorkflow, RegenerateTestAssetWorkflow,
                       AutofillScenarioTestDataWorkflow; live-exploration-task-queue:
                       LiveExploreActivity, LiveHealActivity (LangGraph + Playwright MCP); spec_linter
    execution/         execution-task-queue: ApplicationTestExecutionWorkflow, HealTestExecutionWorkflow,
                       ScheduledExecutionWorkflow, CleanupWorkflow, ReconcileStaleTestRunsWorkflow;
                       live_inspection, project_cache, run_report_email
    recording/         FastAPI + websockets Record & Play service (Xvfb, Chromium, codegen, x11vnc)
packages/
  domain/              SQLModel entities
  explorer_core/       explorer_* tables (models.py), constants (task queue, statuses), notify.py email
  workflows/           workflow definitions + heal_policy, failure_explainer (no I/O)
  ai_provider/         AIProvider + HostedAIProvider (LiteLLM over httpx)
  secrets_client/      Vault KV v2 (hvac)
  object_store/        S3 (boto3)
  mailer/              SMTP + branded header
  test_suite_assembler/ TestAsset → runnable TS Playwright project; vantage_report Allure plugin
  safety_classifier/   destructive/safe/ambiguous classifier
  locator_capture/     DOM/locator extraction (crawler + self-heal)
  playwright_typecheck/ tsc --noEmit gate, assertions.js guard, process_tree kill
  ci_instructions/, delivery_adapters/   empty seams; CI/CD delivery removed
migrations/            Alembic, 85 revisions, single head c1f4a7e2d9b6 (alembic.ini at root)
ops/k8s/               EKS manifests (ops/k8s_BK is an older backup)
ops/jenkins/           one Jenkinsfile per deployable + Jenkinsfile-sonar
docker-compose.yml     local deps: postgres:18.4 (:5433), Temporal dev server (:7233/UI :8233),
                       vault:1.18 (:8200), recording-worker (:8100); no MinIO
```

### Data model

```mermaid
erDiagram
    ORGANIZATION ||--o{ PLATFORM_USER : has
    ORGANIZATION ||--o{ INVITE : issues
    ORGANIZATION ||--o{ APPLICATION : owns
    ORGANIZATION ||--o{ ACTIVITY_EVENT : logs
    APPLICATION ||--o{ DISCOVERY_RUN : has
    DISCOVERY_RUN ||--o{ PAGE : captures
    PAGE ||--o{ FORM : "observed on"
    FORM ||--o{ FORM_FIELD : has
    FORM_FIELD ||--o{ VALIDATION_RULE : has
    PAGE ||--o{ ACTION : "observed on"
    DISCOVERY_RUN ||--o{ API_ENDPOINT : captures
    DISCOVERY_RUN ||--o{ PAGE_TRANSITION : captures
    PAGE ||--o{ COMPONENT : derives
    COMPONENT ||--o{ COMPONENT_LOCATOR : has
    DISCOVERY_RUN ||--o{ DISCOVERY_ERROR : records
    APPLICATION ||--o{ BLOCKED_TASK : aggregates
    BLOCKED_TASK ||--o{ EXPLORATION_STEP : "reached via"
    APPLICATION ||--o{ TEST_DATA_ENTRY : seeds
    CAPABILITY ||--o{ JOURNEY : groups
    DISCOVERY_RUN ||--o{ JOURNEY : discovers
    JOURNEY ||--o{ JOURNEY_STEP : has
    JOURNEY ||--o{ SCENARIO : generates
    JOURNEY ||--o{ TEST_SUITE : "per attempt"
    SCENARIO ||--o{ TEST_ASSET : "compiles to (current flag)"
    APPLICATION ||--o{ TEST_RUN : runs
    SCHEDULE ||--o{ TEST_RUN : triggers
    TEST_RUN ||--o{ TEST_RESULT : has
    TEST_RESULT ||--o{ TEST_RESULT_ARTIFACT : "S3 pointers"
    APPLICATION ||--o{ RECORDING_SESSION : has
    APPLICATION ||--o{ EXPLORER_RUN : "explored by"
    EXPLORER_RUN ||--o{ EXPLORER_EVENT : streams
    EXPLORER_RUN ||--o{ EXPLORER_SCREEN : maps
    EXPLORER_RUN ||--o{ EXPLORER_MISSION : plans
    EXPLORER_RUN ||--o{ EXPLORER_TEST_CASE : proves
    EXPLORER_RUN ||--o{ EXPLORER_QUESTION : asks
    APPLICATION ||--o{ EXPLORER_KNOWLEDGE : remembers
    APPLICATION ||--o{ EXPLORER_ROLE : "test accounts"
    EXPLORER_TEST_CASE }o--o| SCENARIO : "promoted, proven only (grounding link, no FK)"
```

| Group | Tables |
| --- | --- |
| Tenancy & users | `organization`, `platform_user` (role, `last_active_at`), `invite`, `password_reset`, `activity_event` (categories discovery/scenarios/test_cases/test_runs/settings; outcomes running/done/failed/changed/stopped) |
| Application | `application` (url, login_url, `auth_method` ∈ `standard_login | sso_session_reuse | none`, `secret_ref`, `safety_posture`, identity thresholds, `page_load_timeout_seconds`, `discovery_required`, `requires_login` (bool, NOT NULL, default true; set to `auth_method != "none"` on create), counters, soft-delete `deleted_at`), `discovery_settings` (global singleton), `execution_policy` (vestigial) |
| Discovery capture | `discovery_run`, `page`, `form`, `form_field`, `validation_rule`, `action`, `api_endpoint`, `page_transition` |
| Derived model | `component`, `component_locator`, `assertion` |
| Inference | `journey` (candidate/deleted, `identity_key`, attempt, `captured_flow`, `generation_error`), `journey_step`, `capability` |
| Engine bookkeeping | `diagnostic_record` (JSONB sink), `discovery_error`, `blocked_task`, `exploration_step`, `synthetic_data_entry`, `test_data_entry` |
| Generation | `scenario` (type happy/negative/edge; source discovery/nl/recorded; `test_data`; `safety_classification`; `test_case_number`), `test_suite`, `test_asset` (`current`, status incl. `needs_review`, warnings) |
| Execution | `test_run`, `test_result` (auto/manual heal counters, `heal_started_at`, `healed_test_asset_id`, `blocked_reason`), `test_result_artifact`, `failure_explanation`, `schedule`, `recording_session` |
| Explorer (`packages/explorer_core/models.py`) | `explorer_run` (status per AD-10, headline, health_score, requirements_first, `brief` JSONB, brief_confirmed_at, notes, `started_by_id` → platform_user, `insights`/`branch_points` JSONB, error), `explorer_event` (bigint identity PK = polling cursor; kind thought/action/screen/health/phase/summary/error/question), `explorer_shot` (**JPEG bytes in Postgres**), `explorer_screen` (signature, entity, view_kind, mode, url_pattern, fields, actions, hidden_hints, condition, `route` JSONB), `explorer_health_issue` (crash/broken_link/server_error/background_error/slow/wording/looks_wrong/false_alarm/accepted), `explorer_mission` (kind task/branch/area/rule/custom; status queued/running/waiting/done/blocked/failed/skipped), `explorer_transition`, `explorer_recording` (**webm bytes in Postgres**; kind mission/proof/reel), `explorer_test_case` (kind, `script`/`check` JSONB, status planned/building/proven/known_bug/dropped, trust confirmed/standard/seen, proof_runs, proof_passes, catches_breakage, code), `explorer_question` (data/risk/rule/clarify; open/answered/dismissed; issue_id), `explorer_knowledge` (per application; answer/doc/fact), `explorer_role` (per application; Vault `secret_ref`), `explorer_access` |

Explorer migrations (10, all after the July–October chain): `e7a1c3b5d9f2` base tables (parent `b8d4f6a0c2e3`) → `f3b5d7e9a1c4` missions/map/recordings → `a4c6e8f0b2d5` test cases → `b5d7f9a1c3e6` questions/knowledge → `c6e8a0b2d4f7` roles/access/insights/reel → `d7f9b1c3e5a8` `explorer_run.started_by_id` → merge `362ae149aa7c` (with `d4a1c7e9b3f2`) → `a8c2e4f6b1d3` `explorer_screen.route` → `b9d3f5a7c2e4` `application.requires_login` → merge `c1f4a7e2d9b6` (with the crawl branch head `e4c8b2d6f1a7`), now the single head. Because Explorer and the crawl branch share one database, switching between branches needs `alembic stamp --purge` then `upgrade heads`.

Migrations: Alembic; prod applied by the API Jenkins pipeline (`kubectl exec deployment/api -- alembic upgrade head`); CI runs `uv run alembic upgrade head`. `api.db.init_db()` (`create_all`) is used only by test fixtures and the dev seed/backfill scripts.

### Workflows and queues

| Queue (worker) | Workflows | Key activities | Concurrency (code default / k8s) |
| --- | --- | --- | --- |
| `explorer-task-queue` | `ExplorerRunWorkflow` (modes full/missions/tests/resume/send; signal `brief_confirmed`) | 18 `explorer_*` activities (AD-22); understand 2 h, pool items 45 min, hunt/breadth 40 min, plan_tests 20 min, promote 10 min, reel 20 min; all `maximum_attempts=1` | 8 / not deployed |
| `discovery-task-queue` | `DiscoveryWorkflow`, `VerifyCredentialsWorkflow` (still used for every credential check, including Explorer apps) | `DiscoveryActivity` (6 h, 2 min heartbeat), `ApplicationModelBuilderActivity` (10 min), `InferenceActivity` (5 min, 3 attempts, sequential clustered batches), `MarkDiscoveryRunFailedActivity`, `VerifyCredentialsActivity` (single attempt, 150 s) | 5 / 3 |
| `generation-task-queue` | `GenerationWorkflow`, `SuiteGenerationWorkflow`, `LiveExplorationTestWorkflow`, `RegenerateTestAssetWorkflow`, `AutofillScenarioTestDataWorkflow` | `ScenarioGenerationActivity`, `EnsureTestSuiteActivity`, `PlaywrightGenerationActivity`, `FinalizeSuiteGenerationActivity`, `RegenerateTestAssetActivity`, `AutofillScenarioTestDataActivity` (no AI), `AnalyzePromptActivity`, `MergeLiveJourneyActivity` | 5 / 20 |
| `live-exploration-task-queue` (generation process) | — | `LiveExploreActivity`, `LiveHealActivity` (explore turn budget `max(30, min(150, 12 × actions))`; heal 10 turns) | 2 |
| `execution-task-queue` | `ApplicationTestExecutionWorkflow`, `HealTestExecutionWorkflow`, `ScheduledExecutionWorkflow`, `CleanupWorkflow`, `ReconcileStaleTestRunsWorkflow` | Prepare, Execute, Heal, GenerateAllureReport, SendTestRunReportEmail, Finalize/ForceComplete, CleanupCancelled, FindPurgeCandidates/PurgeApplication, CheckScheduleGate, ReconcileStaleTestRuns, PrepareSingleTestRun/ReadTestResultStatus/DiscardTestRun | 20 / 6 |

### Key sequence — onboard → discover → generate → run

```mermaid
sequenceDiagram
    actor U as User
    participant W as Web
    participant A as API
    participant T as Temporal
    participant D as Discovery worker
    participant X as Explorer worker
    participant G as Generation worker
    participant E as Execution worker
    participant V as Vault
    participant S as S3
    U->>W: Add application (URL, sign-in method)
    W->>A: POST /applications/test-connection, /verify-credentials
    A->>T: VerifyCredentialsWorkflow
    T->>D: VerifyCredentialsActivity (real login)
    W->>A: POST /applications
    A->>V: store credentials (secret_ref)
    alt discovery_required and EXPLORER_REPLACES_DISCOVERY (default)
        A->>T: ExplorerRunWorkflow (explorer-run-{id})
        T->>X: understand → App Summary
        U->>W: edit / confirm summary
        W->>A: PUT /explorer/runs/{id}/brief, POST /confirm
        A->>T: signal brief_confirmed
        T->>X: missions → hunt → breadth → plan + prove tests → promote → reel
        X->>A: (via DB) proven Scenarios + Journeys, DiscoveryRun stage=analyzed
    else discovery_required, flag off (classic crawler)
        A->>T: DiscoveryWorkflow
        T->>D: Discovery → ModelBuilder → Inference
        D->>S: screenshots
        D->>A: (via DB) candidate journeys, stage=analyzed
    end
    U->>W: Continue to scenarios / Generate suite (Explorer apps: Generate tests on Test cases)
    W->>A: POST /generate-scenarios, /generate-suite
    A->>T: GenerationWorkflow / SuiteGenerationWorkflow per journey
    T->>G: scenarios → TS spec → tsc gate → linter
    U->>W: Run tests (all or named selection) or schedule
    W->>A: POST /test-runs
    A->>T: ApplicationTestExecutionWorkflow
    T->>E: prepare → npx playwright test → heal → Allure → finalize → email
    E->>V: credentials into subprocess env
    E->>S: artifacts, single-file Allure report
```

## Security model

- **Platform users:** invite-only, bcrypt, signed httpOnly cookie with 1 h sliding idle expiry (AD-21); org scoping (AD-12); viewer deny-by-default on writes plus report/download reads.
- **Target-app secrets:** Vault only (AD-5); temporary verify-credentials secrets can be orphaned if a worker dies (`ponytail:` in `main.py`).
- **Explorer authorization gap:** `/explorer/*` is org-scoped and covered by the global viewer write block, but has no admin or `NotViewerDep` checks (AD-12): members manage role test accounts in Vault and knowledge; viewers can download the tests zip, report, recordings and reel. No Explorer action reaches the Activity feed.
- **Explorer data at rest:** screenshots and webm recordings live as bytes in Postgres (`explorer_shot`, `explorer_recording`), outside the S3 lifecycle; uploaded knowledge documents are stored as extracted text in `explorer_knowledge`.
- **Crawler safety:** destructive actions always refused; ambiguous per application posture (AD-15). Explorer applies its own risk gating while walking missions (`pursue.py`). Test execution has no safety/ExecutionPolicy gate (removed on request).
- **CORS:** `CORS_ALLOWED_ORIGINS`, credentialed, exposes `Content-Disposition`.

## Deployment topology

- **AWS EKS**, AWS Load Balancer Controller ALB ingresses (`group.name: ps-team-app-stage-alb`): `vantage.omnewave.com` (web), `vantage-api.omnewave.com` (api), `vantage-recording.omnewave.com` (recording), `aitestgen-temporal.onwavemaker.com` (Temporal UI).
- Every Deployment is `replicas: 1`. Temporal runs `start-dev` (in-memory) as one pod. Vault runs file storage with auto init/unseal. Postgres is externally hosted. S3 bucket `wmps-ai-testgen` (us-east-1). SMTP via smtp.gmail.com. LiteLLM proxy `wmps-litellm.onwavemaker.com`.
- Probes: API `/health` (startup/readiness/lenient liveness; 100m/256Mi → 1 CPU/512Mi), web `/` readiness, recording `/health`, Vault `/v1/sys/health`; workers have no Service or probe.
- Worker resources (request → limit): discovery 500m/1Gi → 4/4Gi; generation 250m/512Mi → 2/6Gi; execution 500m/1Gi → 2/4Gi; recording 1/2Gi → 4/8Gi.
- **Explorer worker is not deployable yet:** there is no Explorer worker Dockerfile, no `ops/k8s/*explorer*` manifest, no `ops/jenkins/Jenkinsfile-explorer-worker`, no `EXPLORER_*` in the configmap and no docker-compose service. Because `EXPLORER_REPLACES_DISCOVERY` defaults to on, a deployed API answers every add-with-discovery with `DiscoveryRun failed / worker_unavailable` until the worker ships (Dockerfile with Playwright Chromium, k8s Deployment, Jenkinsfile, configmap entries, SMTP) or the configmap sets `EXPLORER_REPLACES_DISCOVERY=0`. The discovery worker must stay deployed either way: it serves `VerifyCredentialsWorkflow`.
- **CI/CD:** GitHub Actions CI (Python: uv sync `--all-packages` → ruff → pyright → alembic upgrade → pytest over `apps` and `packages`, which picks up the Explorer worker and `explorer_core` tests, with a Temporal dev server; Web: oxlint → `tsc -b` → vitest → vite build; API-types drift check). Jenkins per-service CD: docker build → ECR (`<svc>-stage.<BUILD_NUMBER>`) → `kubectl set image`; API pipeline also migrates. Separate SonarQube pipeline.
- **Local dev:** `docker-compose.yml` for Postgres/Temporal/Vault/recording; `scripts/dev-start.*` runs API, workers (including the Explorer worker via `scripts/run-explorer-worker.{sh,cmd}`, which reloads with watchfiles on `apps/workers/explorer/src` and `packages/explorer_core`) and web, logging to `logs/*.log` (`explorer-worker.log`); `dev-stop.sh` stops it. The other workers' `.cmd` scripts call `.venv/Scripts/python.exe` directly. On Windows, watchfiles reloads can leave orphaned workers polling the queue. Real AWS S3 (no MinIO).

## Observability

- Plain stdout logging per service; no OpenTelemetry, Sentry, Prometheus or structured JSON logs.
- Workflow-level view: Temporal Web UI.
- Discovery: `diagnostic_record`, `discovery_error`, coverage report (`/discovery-runs/{id}/report`: reached/blocked/skipped/errored/unreached + diagnostics).
- Explorer: `explorer_event` stream (thoughts, actions, screens, health, phases, questions) drives the live view; `explorer_worker/llm.py` logs a gist of each LLM request and reply; `/explorer/runs/{id}/report` and `/report/download` give a run report (no UI yet).
- Product-level: admin Activity feed (`activity_event`, `GET /activity`, cursor-paginated with facets). Explorer actions are not recorded there.

## Known risks and deliberate shortcuts

| Risk / shortcut | Impact | Upgrade path |
| --- | --- | --- |
| Temporal `start-dev` in prod | Workflow history and Temporal Schedules lost on pod restart; schedule scripts must be re-run | Persistent Temporal (Postgres-backed) or Temporal Cloud |
| All deployables single-replica; Allure needs the run's local dir | No HA; execution can't scale out | Upload project to S3 or pin runs to a host before adding replicas |
| `COOKIE_SECURE=false`, ALB cert ARN commented out | Session cookie can travel over HTTP | Enable TLS cert + `COOKIE_SECURE=true` |
| `SESSION_SECRET_KEY` insecure code default | Forgeable sessions if env unset | Fail fast when unset |
| SignIn dev-credential autofill on clicking the "Welcome back" heading ships in prod (`DEV_LOGIN_ENABLED = true`) | Exposes dev credentials | Gate behind a dev build flag |
| Vault unseal key + root token on the same volume | Volume access = full Vault access | Cloud KMS auto-unseal, scoped tokens |
| Raw Postgres host IP in prod ConfigMap | Infra detail in config | Move to Secret / DNS name |
| No metrics/tracing/alerting | Stuck runs noticed only by users or the 15 min reconciler | OpenTelemetry + alerting |
| Run report built before Finalize | Stuck-pending tests missing from the report | Reorder after Finalize |
| No email on failure/reconcile/manual-heal paths; claim may drop | Some runs send no email | Outbox table |
| Fixed caps: auto-heal 2, 3 generation waves/30 s, one stale cutoff, ~150 s credential check | Not tunable per app | Move to `discovery_settings` |
| English-only rules (credential-check errors, failure explainer) | Non-English apps fall to `unknown`/LLM | Localized rules or LLM-first |
| Inference batches sequential | Slow inference on large apps | Parallel batches |
| `resume.py` and AI safety consult built but unwired | Dead code paths | Wire or delete |
| `execution_policy` table/endpoints and test_run columns vestigial | Confusing surface | Drop in a migration |
| `LIVE_EXPLORATION_UNAVAILABLE`, `SCHEDULE_BACKEND_UNAVAILABLE` not mapped in web | Generic error copy | Add to `errorCodes.ts` |
| Generated-type hand patches in `api.ts` | Contract drift (AD-6) | Regenerate types |
| `docs/archify-docs` architecture JSON stale | Misleading diagram | Regenerate from this spine |
| **Explorer worker has no Dockerfile/k8s/Jenkins while `EXPLORER_REPLACES_DISCOVERY` defaults on** (high) | Every deployed add-with-discovery fails with `worker_unavailable` | Ship the worker, or set the flag to `0` in the configmap |
| No admin/`NotViewerDep` checks on `/explorer`; no Activity events | Members manage role credentials; viewers download tests/report/media; no audit trail | Add `require_admin` to roles/knowledge, `NotViewerDep` to downloads, log to `activity_event` |
| Explorer media as Postgres bytes (`explorer_shot`, `explorer_recording` 1–6 MB per mission, reel) | Database bloat, slow backups | Move to the object store (`ponytail:` in `models.py`) |
| `discovery_engine` flips to `explorer` once any `explorer_run` exists | A crawler app that runs Explorer once loses its Journeys/Scenarios pages and classic Pause/Resume; its crawler journeys stay `candidate`, so generate-suite may cover both sets (not confirmed) | Store the engine on the application |
| `one_at_a_time` from a keyword guess (`sense.py` `keeps_state`) | Wrong guess slows runs or lets parallel tests clobber shared state | Per-app answer from the user |
| Per-process Explorer caches (screen readings, signed-in sessions, static assets, network log) | Worker restart costs time; a deploy mid-run is seen only on cache expiry | Shared cache if restarts become common |
| Known-bug tests never reach Test cases but are in the tests zip (`test.fixme`) | Two different "test sets" for one run | Document or align |
| Any `begin_run` HTTPException (including 409 already running) is recorded as `worker_unavailable` | Misleading failure reason | Map 409 separately |
| Explorer API features with no UI: add mission, recordings, reel, report, tests zip, regenerate, insights, health score; `MISSIONS_ADDED_SIGNAL` and `explorerApi.screens` unused | Dead or hidden surface | Build the screens or remove |
| Explorer bypasses `AIProvider` (AD-3) and `packages/mailer` | Two LLM clients, two email paths | Fold into the ports when Explorer stabilizes |
| Stale text in code: `explorer_core/models.py` docstring ("never reads or writes" classic tables), ReviewScenarios comment, StartCard "Your current Journeys are not affected", CLAUDE.md "Questions tab" (it is a dialog) | Misleads readers | Fix the text |
| `logs/dev-start.out`, `logs/fnol-missions.txt` committed | Dev artifacts in the repo | Remove and ignore `logs/` |

Full list: 82 `ponytail:` comments in tracked source. Explorer's 16: screenshots and recordings in Postgres, keyword knowledge recall (`models.py`); log-instead-of-send email (`notify.py`); in-memory static cache, English-only calendar months, in-memory network log (`browser.py`); per-process screen-reading cache (`mind.py`) and session reuse (`session.py`); repeat passes for task missions only and a duplicate follow-up race fixable by a unique `(run_id, title)` (`missions.py`); file upload described but not generated (`promote.py`); hash routes must start with `/` and `keeps_state` keyword guess (`sense.py`); "found nothing new" treated as a variant and the sign-in landing page can't be proven (`tests_stage.py`).

## Not built / deferred

- Platform SSO / OAuth for Vantage users.
- CI/CD delivery to customer repos (`packages/delivery_adapters`, `packages/ci_instructions` are empty seams).
- Regenerating a journey's scenarios on request (the `attempt`/`current` scaffold exists with no second caller); targeted per-scenario regeneration after test-data edits *is* built.
- Scheduling discovery (only test runs schedule).
- Per-application permissions (roles are org-wide).
- Data resolver "page scan" step.
- Redis/distributed cache; horizontal scaling of any service.
- On-prem / customer-supplied LLM endpoint (the `AIProvider` port keeps it cheap to add).

## Decisions retired

| Original decision (July draft) | Status today |
| --- | --- |
| AD-1: Inference auto-starts `GenerationWorkflow` per candidate journey | Reversed 2026-07-21 — generation is an explicit user trigger |
| Approval gate (approve/reject journeys) | Cut — only rename/delete |
| AD-4 `DeliveryAdapter` / CI instructions | Feature removed 2026-07-15; packages kept as empty seams |
| Full regeneration of a journey (FR-18) | Cut 2026-07-27 |
| Generated tests / download in Python | Superseded — TypeScript `@playwright/test` |
| Generic `Evidence` table | Replaced by typed capture tables (AD-8) |
| "No time budget; exhaustive traversal is the only stop" | Superseded by `max_pages` / max-duration caps with recorded `stop_reason` |
| Resume replays stored exploration steps | Superseded by re-crawl-from-entry design; that code is unwired; run pause/resume is what ships |
| Structured JSON logs + OpenTelemetry correlated by `workflow_id` | Never built — plain stdout logging |
| RFC 7807 error envelope; camelCase API JSON | Never built — FastAPI `detail`, snake_case |
| MinIO for local/CI object storage | Dropped — real S3 everywhere |
| Execution/safety policy gating test runs | Removed on request; table vestigial |
| TypeScript 7.0 for the web | Pinned at 5.9.3 (codegen/tooling compatibility) |
| Analytics dashboards, AI-provider-mode settings UI | Removed; Overview dashboard and Settings page exist with different scope |
| The crawler (AD-14/15) is the discovery engine | Superseded 2026-10-27 — Explorer (AD-22) is the default; the crawler runs only with `EXPLORER_REPLACES_DISCOVERY=0` or for existing crawler runs |
| Every LLM call goes through `AIProvider` (AD-3) | Relaxed — Explorer has its own LiteLLM client |
