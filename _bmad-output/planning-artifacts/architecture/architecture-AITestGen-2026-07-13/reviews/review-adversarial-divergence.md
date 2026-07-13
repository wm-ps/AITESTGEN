---
title: Adversarial Divergence Review — Architecture Spine
target: ../ARCHITECTURE-SPINE.md
method: "Two units, one level down" — construct pairs of engineers who each obey every AD/Convention to the letter, find where they still produce incompatible systems.
status: findings
created: '2026-07-13'
---

# Adversarial Divergence Review — Application Intelligence Platform Spine

## Verdict

The spine is architecturally sound on *placement* (every AD correctly says which package/layer owns a concern) but is silent on the two things that actually cause independently-built units to diverge in a Temporal-orchestrated, external-side-effect-heavy system: **retry/idempotency contracts for Activities that touch the outside world**, and **the precise write/update semantics of the AD-8 evidence pointer across the Journey→Scenario→TestAsset lineage and across regeneration/re-discovery**. Both gaps are exploitable by two spec-compliant engineers to produce genuinely incompatible, and in one case customer-visible-duplicate-PR-producing, systems.

---

## Finding 1 — No idempotency/retry contract for Activities with external side effects [CRITICAL]

**AD violated in spirit, not in letter:** AD-2 ("Activities own all I/O") and AD-4 (CIDeliveryActivity behind DeliveryAdapter) both say *where* side-effecting code lives. Neither says *what happens when Temporal retries that code after a partial failure.* Temporal's default contract is: an Activity is retried as a whole (from its start) on failure/timeout/worker-crash, unless the Activity itself implements idempotency (e.g., via a deterministic idempotency key, a "check before act" pattern, or Activity heartbeat + resumable checkpointing). The spine never states this obligation, never assigns an idempotency key to any entity, and the domain model (`Application, DiscoveryRun, Capability, Journey, Scenario, TestAsset, Evidence, CIConfig`) has no field that a retry-safe implementation could dedup against (no `external_ref`, `delivery_attempt_id`, `commit_sha`, `pr_number`, or similar).

**Concrete pair — two engineers each building a `DeliveryAdapter` (AD-4 compliant):**
- Engineer A builds the GitHub Actions adapter. Reading the sequence diagram literally (`GW->>GIT: Create PR ... GIT-->>GW: Delivery confirmation ... GW->>DB: Mark Test Asset delivered`), they implement `create_pr()` as an unconditional "open a new PR" call — nothing in AD-4 or the spine tells them to check for an existing PR first.
- Engineer B builds the GitLab adapter defensively, searching for an open MR on a conventional branch name before creating one, because they anticipate retries.
- **Point of incompatibility:** When `CIDeliveryActivity` succeeds at "create PR" but the subsequent `DB: Mark Test Asset delivered` write fails (DB blip, pod restart, network partition — exactly the "partial failure" scenario named in this review's brief), Temporal retries `CIDeliveryActivity` from the top. On a GitHub-configured Application this creates a **second PR** for the same Test Asset; on a GitLab-configured Application it does not. Both engineers are AD-4-compliant — the spine simply never says which behavior is correct, so "compliant" doesn't mean "compatible." Worse: even Engineer B's defensive fix has no contract to hook into — there's no spine-mandated branch-naming convention, PR-title convention, or idempotency key on `TestAsset`/`CIConfig` to dedup against, so their "fix" is a private guess, not a shared contract.
- **Same root cause, second instance (apps/api ↔ apps/workers, matching the prompt's own example pair):** The review-endpoint engineer implements `POST /journeys/{id}/approve` per AD-7/AD-1 as `DB: status=approved` then `TMP: Start GenerationWorkflow`. Nothing says what to do if the DB write succeeds but the Temporal start call fails (or vice versa — engineer could equally have ordered the calls the other way, which the sequence diagram doesn't forbid). A Journey can end up `approved` with no `GenerationWorkflow` ever started, and nothing in the spine defines a reconciliation path. `FR-24` coverage analytics ("which approved Journeys have a generated Test Asset") cannot distinguish "silently dropped" from "still processing," because no status/timestamp/outbox convention exists for this boundary.
- **Third instance, more dangerous than duplicate PRs:** `DiscoveryActivity` itself is long-running and exercises forms/APIs with real side effects (per PRD Risk Register item 6 — no destructive-action guardrail even in non-prod). If a Discovery Activity times out mid-crawl and Temporal retries it, does it resume from a checkpoint or restart the crawl from page 1, re-submitting forms it already exercised (real emails, real state-changing API calls)? The spine gives Temporal Activities the exclusive right to perform I/O (AD-2) but no guidance on whether that I/O must be safe to repeat. This is the same gap, applied to the platform's single most operationally dangerous Activity.

**Why this is critical, not a nitpick:** it's not a missing implementation detail an engineer can safely infer — the two "correct" inferences (naive retry vs. defensive dedup) produce materially different, customer-visible outcomes (duplicate PRs, duplicate commits, double-submitted production-adjacent side effects), and neither engineer violated a single AD or Convention to get there.

**Recommendation for the next design pass:** Add an AD (or extend AD-2/AD-4) that states: (a) every Activity with an external side effect must be idempotent under at-least-once retry, (b) the mechanism is a deterministic idempotency key derived from domain-entity IDs (e.g., `TestAsset.id` + attempt count, or a Temporal-provided deterministic key), and (c) that key/convention lives in `packages/domain` so both adapter authors and the analytics/API authors share it.

---

## Finding 2 — AD-8's `discovery_run_id` is ambiguous for rows a DiscoveryWorkflow never produced [CRITICAL]

**The rule as written:** AD-8 says *"Every `Journey`, `Scenario`, and `TestAsset` row carries the `discovery_run_id` (and, transitively, `workflow_id`) of the run/workflow that produced it. The Journey Explorer (FR-23) reads this pointer directly."*

**The contradiction:** A `Journey` row is produced by a `DiscoveryWorkflow` — `discovery_run_id` is a natural, literal fit. But `Scenario` and `TestAsset` rows are produced by a `GenerationWorkflow` (per the Structural Seed and the Components diagram — `ScenarioGenerationActivity`/`PlaywrightGenerationActivity` live in `apps/workers/generation`, dispatched by `GenerationWorkflow`, which per AD-1 is parameterized only by `journey_id`, not by any `discovery_run_id`). AD-8's own phrase — "the run/workflow that produced it" — is not one thing for these rows: the *workflow* that produced a Scenario is a `GenerationWorkflow`; the *discovery run* that (transitively, via the parent Journey) explains its evidence is a `DiscoveryRun`. The field is literally named `discovery_run_id`, but for Scenario/TestAsset it can't hold "the workflow that produced it" (that's a GenerationWorkflow run, which is not a DiscoveryRun) *and* satisfy "reads this pointer directly" for evidence purposes at the same time.

**Concrete pair:**
- Engineer A (builds `ScenarioGenerationActivity` persistence) reads AD-8 as "propagate the lineage": copy the parent Journey's `discovery_run_id` down onto every `Scenario`/`TestAsset` row at write time (a join against `Journey.discovery_run_id`), so `discovery_run_id` always resolves to an actual `DiscoveryRun` and Evidence stays traceable.
- Engineer B (builds the Journey Explorer per FR-23/AD-8, "reads this pointer directly — never reconstructs evidence from a separate index") reads AD-8 as "the row's own producing run," and — since a Scenario literally wasn't produced by a `DiscoveryWorkflow` — stores/expects `discovery_run_id` to be null on Scenario/TestAsset with only `workflow_id` populated (pointing at the `GenerationWorkflow`'s run id), treating evidence traceability as "walk up to the parent Journey yourself."
- **Point of incompatibility:** Engineer B's Journey Explorer, built to "read this pointer directly," either breaks (null/foreign-workflow-id where it expects a valid DiscoveryRun) or silently shows wrong evidence (a GenerationWorkflow run has no discovery signal at all — pages/actions/API calls — to show). Engineer A's data is actually correct for the UI's needs, but nothing in the spine forced convergence on that interpretation; both are literal, defensible readings of one sentence.

**Regeneration sharpens this (FR-18, directly requested):** FR-18 regenerates Scenarios/TestAssets "from scratch" *without* re-running discovery — no new `DiscoveryRun` is created. The ERD models `DISCOVERY_RUN ||--o{ JOURNEY` as a fixed, creation-time relationship; nothing shows `Journey.discovery_run_id` as mutable, and no AD assigns anyone responsibility for updating it. That part is actually *not* ambiguous — the Journey's own evidence pointer is correctly immutable and stays put across regeneration. The ambiguity is entirely on the **derived** rows: on regeneration, does the new `Scenario`/`TestAsset` row inherit the *original* Journey's `discovery_run_id` (Engineer A's interpretation) or is it (re)computed some other way, and — separately — what happens to the **old** `Scenario`/`TestAsset` rows from the prior generation? The spine never says whether they're deleted, soft-deleted, or left as orphaned duplicates (see Finding 4). **Nobody is named as responsible** for either question; AD-7 assigns write-ownership for *approval-state* transitions only, and AD-8 assigns the *existence* of the pointer, not its update semantics across regeneration.

**Recommendation:** AD-8 should explicitly state (a) that `discovery_run_id` on Scenario/TestAsset is *inherited* from the parent Journey at write time, is never independently computed, and is re-copied on every regeneration; and (b) name the write-owner (`ScenarioGenerationActivity`) responsible for setting it, mirroring the precision AD-7 already gives to approval-state ownership.

---

## Finding 3 — GenerationWorkflow identity/reuse policy unspecified: regeneration (FR-18) vs. double-approval race [HIGH]

AD-1 states: *"Each individual approval starts a new, independent, short-lived `GenerationWorkflow(journey_id)`."* This reads naturally as "the workflow ID is derived from `journey_id`" — a common, idiomatic Temporal pattern used specifically to make double-clicks/duplicate-approve-calls idempotent (Temporal rejects starting a second workflow with an ID already in use, by default).

**Concrete pair:**
- Engineer A (review-endpoint owner) implements the approve action this way: `workflow_id = f"generation-{journey_id}"`, relying on Temporal's default ID-collision rejection to make double-approval safe (a legitimate, spine-consistent reading of AD-1's literal notation).
- Engineer B (regeneration-feature owner, FR-18) later implements "regenerate" by calling the exact same start-workflow path — it's the same GenerationWorkflow, just re-triggered. Since a GenerationWorkflow already completed under `generation-{journey_id}` from the original approval, Engineer B's regeneration call collides with Temporal's default reuse policy and **fails outright** ("workflow already running/already exists"), unless a `WorkflowIdReusePolicy` (e.g., `ALLOW_DUPLICATE`) is explicitly set — a detail the spine never mentions.
- If Engineer B instead works around this by suffixing the workflow ID with a timestamp/nonce to dodge the collision, Engineer A's double-click-safety property silently disappears — concurrent approve-clicks on the same Journey now spawn two parallel GenerationWorkflows, each independently calling the AI provider and `CIDeliveryActivity`, compounding Finding 1's duplicate-PR risk.
- **Point of incompatibility:** both engineers correctly implemented "start a `GenerationWorkflow(journey_id)`" per AD-1's literal text; one makes regeneration impossible, the other makes double-approval unsafe. The spine doesn't specify which property (dedup-on-approve vs. re-run-on-regenerate) takes precedence, or the ID scheme/reuse policy that reconciles both.

**Recommendation:** Specify the Temporal workflow ID scheme explicitly (e.g., `generation-{journey_id}-{generation_number}`) and the reuse policy, so both approve-idempotency and regenerate-on-request are simultaneously satisfiable.

---

## Finding 4 — No versioning/soft-delete semantics for regenerated Scenario/TestAsset rows [MEDIUM]

The ERD shows `JOURNEY ||--o{ SCENARIO` and `SCENARIO ||--o| TEST_ASSET` with no version/superseded/`is_current` field named anywhere in the domain model list. FR-18 mandates regeneration is always full ("from scratch"), which — combined with the 1-to-many Journey→Scenario relationship — raises an unaddressed question: does regeneration delete the prior generation's rows, or accumulate a new set alongside the old?

**Concrete pair:**
- Engineer A (coverage analytics, FR-24: "which approved Journeys have a generated Test Asset") implements the check as `EXISTS(SELECT 1 FROM test_asset WHERE journey_id = ...)` — any TestAsset ever produced counts as "covered," including a stale one from a generation superseded weeks ago.
- Engineer B (CI delivery / regeneration path) treats the prior generation's rows as dead once a new `PlaywrightGenerationActivity` run completes, and — absent an explicit spine instruction — deletes or ignores them going forward, or leaves them in place as silent duplicates.
- **Point of incompatibility:** if B deletes old rows mid-flight while A's dashboard query is a straight existence check with no join to "latest generation," a regeneration-in-progress can show a Journey as transiently *uncovered* to an Engineering Leader mid-release-review (FR-24/UJ-2's exact use case) — or, if B doesn't delete, A's dashboard silently double-counts stale TestAssets as current coverage. Neither engineer violated a rule; no rule exists to violate.

**Recommendation:** Add a convention (or extend AD-8) naming the regeneration write pattern — e.g., "regeneration soft-supersedes prior Scenario/TestAsset rows via a `superseded_at`/`generation_number` field; only the latest generation counts for FR-24 coverage and FR-23 evidence display."

---

## Finding 5 — Journey "identity" for FR-15 re-discovery dedup is undefined, with a downstream AD-8 consequence [MEDIUM]

FR-15 requires re-running discovery to flag only journeys "not seen in a prior run" — an existence/equality check against the Trusted Knowledge Model. The spine assigns this to `InferenceActivity` (Component diagram) but specifies no identity key (name match? page-sequence hash? AI-driven semantic similarity against existing approved Journeys?). This matters architecturally, not just as an implementation detail, because it interacts directly with AD-8: if a re-discovery run (`DiscoveryRun-2`) produces a candidate the system judges identical to an already-approved Journey originally evidenced by `DiscoveryRun-1`, does `Journey.discovery_run_id` get re-parented to `DiscoveryRun-2` (fresher evidence) or stay pointing at `DiscoveryRun-1` (evidence provenance, immutable)? The ERD's `DISCOVERY_RUN ||--o{ JOURNEY` is drawn as a fixed creation-time edge with no re-parenting path, but AD-8's "traceable path back to the discovery signal that produced it" arguably wants the *freshest* evidence, not the *first* evidence. Two engineers implementing the FR-15 dedup logic and the "evidence pointer update on match" logic independently (plausible as separate story slices) could pick opposite defaults with no spine rule to arbitrate, and no single AD names an owner for updating (or refusing to update) the pointer on a matched re-discovery.

---

## Summary Table

| # | Finding | Severity | Root cause |
| --- | --- | --- | --- |
| 1 | No idempotency/retry contract for side-effecting Activities (CIDelivery, Discovery, approve→start-workflow boundary) | Critical | AD-2/AD-4 govern *placement* of I/O, not its retry-safety |
| 2 | AD-8's `discovery_run_id` ambiguous for Scenario/TestAsset (produced by GenerationWorkflow, not DiscoveryWorkflow) | Critical | AD-8's own wording conflates "discovery run" and "producing workflow" |
| 3 | GenerationWorkflow ID scheme/reuse policy unspecified — regenerate (FR-18) vs. double-approve dedup conflict | High | AD-1's `GenerationWorkflow(journey_id)` notation underspecifies workflow-ID/reuse-policy contract |
| 4 | No versioning/soft-delete semantics for regenerated Scenario/TestAsset rows | Medium | FR-18 "from scratch" regeneration has no persistence contract in the spine |
| 5 | Journey identity/equality semantics for FR-15 re-discovery dedup undefined; evidence-pointer re-parenting on match unowned | Medium | FR-15 assigned to InferenceActivity with no identity-key convention; interacts with AD-8 |
