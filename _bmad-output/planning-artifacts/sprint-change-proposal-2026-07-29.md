# Sprint Change Proposal — 2026-07-29

**Trigger:** User-authored design document, "AITestGen — Discovery Engine: Complete Flow Document," proposing a redesign of the crawling/discovery engine's internal decision-making (state identity, action safety, blocked-data handling, cross-session persistence, crash recovery, error taxonomy).

**Constraint (explicit, from requester):** Do not change the existing epic sequence (Epics 1–4 stay as-is). Do not implement or modify code. Where a change cannot fit an existing story, create a new story. Planning documents only.

**Mode:** Batch review (per user selection). Story breakdown: 11 new Epic 2 stories, per user-confirmed granularity.

---

## 1. Issue Summary

The current Discovery engine (Story 2.2's `crawler.py`/`activities.py`, Story 2.5's `ApplicationModelBuilderActivity`) implements a simple BFS crawl with four ad hoc optimizations (page-fingerprint dedup, navigation-first ordering, representative-action/form sampling, broken-destination skipping) and no notion of: page-load readiness beyond a fixed wait, infinite-scroll/pagination termination, a graduated Safe/Destructive/Ambiguous action classification, structured data-resolution with deferral, tabs/dialogs/multi-window/file-upload as first-class widgets, a mechanism to pause a partially-blocked exploration and resume it later, crash recovery beyond Temporal's own retry, or a machine-readable error taxonomy.

The submitted document specifies all of the above as one coherent architecture (Observer → State Identity Engine → Action Extractor → Exploration Planner → Safety Engine / Data Resolver → Execution Decision), explicitly modeled as an extension of — not a replacement for — the existing pipeline (Discovery → Application Model Builder → Inference → Generation, Section 20 confirms this handoff is unchanged).

## 2. Impact Analysis

### Epic Impact

- **Epic 1** (Foundation/Onboarding): one story touched. Story 1.2's Home screen currently shows a single persistent Application card (name, journey/scenario counts, status). Section 16.5's "Save as Project" dashboard (Confirmed/Blocked/Remaining counts, Paused status) extends this card's data model but the actual visual design isn't specified in `DESIGN.md`/`EXPERIENCE.md` — **flagged as a `[GAP]` requiring a UX pass, not resolved here.**
- **Epic 2** (Runtime Discovery): the epic description gains two sentences (Safety Engine, Blocked/Save-as-Project). 11 new stories added (2.9–2.19). Four existing stories amended: 2.2 (two ACs marked superseded), 2.3 (one AC added), 2.5 (one clarifying note), none require re-opening already-`review`/`done` work beyond an additive note.
- **Epic 3** (Curation): no impact — deletion remains the sole exclusion mechanism; Blocked Journeys are a pre-Journey-inference concept (see naming note below) and don't touch the Trusted Knowledge Model's curation rules.
- **Epic 4** (Generation): one story touched. Story 4.1 gains one AC (test-data carry-forward from discovery-time synthetic/unblocking values, Section 20.1).
- **No epic added, removed, or resequenced.**

### Artifact Conflicts

**PRD:**
- **§12 Risk item 6** ("no platform-side guardrail is built in V1, by explicit decision") is **reversed** by the new Safety Engine (FR-39). This is a real scope reversal, not an addition — flagged for explicit sign-off below, per this PRD's own convention of `[NOTE FOR PM]` tags on deliberate deviations.
- **§5 Non-Goals / Open Question 3** ("no system-enforced non-production safeguard") is **unaffected** — that's about verifying the target is non-production; the new Safety Engine is about not blindly executing destructive actions regardless of environment. Both risks coexist; only §12 item 6 changes.
- New FR-35 through FR-47 needed (§4.2 Runtime Discovery); none conflict with existing FR-1–34.
- MVP scope (§6.1) needs one new bullet.

**Architecture:**
- New domain entities required: none of the doc's proposed entities can reuse an existing table without a naming collision — see the **naming collision** callout below.
- New AD entries needed: AD-16 through AD-23 (State Identity Engine, Action Priority, Safety Engine, Data Resolver, Blocked Frontier, Save-as-Project, Crash Recovery, Loop Prevention consolidation).
- AD-15's "navigation-first" rule 5 is **superseded**, not deleted — replaced by the Action Priority Model's Tier-1-before-Tier-2 rule (functionally a refinement, but the label "navigation-first" becomes actively misleading and must be retired).
- **Infra decision (lazy default, flagged for override):** the doc's "runtime cache (Redis/in-memory)" is proposed here as **in-process only** (a plain dict scoped to one `DiscoveryActivity` execution, rebuilt from canonical `Page` rows on Activity start) — no new Redis dependency. This is sufficient because Save-as-Project resume relies on the *permanent* DB's canonical rows (Section 16.3: "nothing already discovered is re-explored" comes from the confirmed Application Model, not the runtime cache), so the cache never needs to survive past one Activity execution. Add Redis later only if a single-process in-memory cache measurably can't keep up.
- **"Project" ≠ new entity:** Section 16's "Project" maps directly onto the existing `Application` entity (already Organization-scoped, already the durable unit re-discovery runs against per FR-15). No new `Project` table. `DiscoveryRun.status` gains a fourth value, `paused`.

**⚠️ Naming collision requiring resolution (flagged, not silently resolved):** the document uses "Journey" for two different things — (1) the existing `Journey` domain entity (an AI-inferred, named business journey, created by `InferenceActivity` *after* discovery completes), and (2) a crawl-time execution path (login → click → click → blocked), which doesn't exist yet as a Journey row when it blocks — Section 15.0's worked example blocks *before* any `Journey` has been inferred at all. Reusing "Journey"/"JourneyStep" for both would be a standing source of engineering confusion. **Default applied in this proposal:** the crawl-time path is named `ExplorationPath`/`ExplorationStep` throughout the new domain model and stories; "Journey" is reserved exclusively for the existing Trusted-Knowledge-Model entity. Flagged for explicit confirmation before implementation.

**UX:** Section 16.5's dashboard and Section 14's "supply missing data / authorize action" review surface have no home in the current 6-screen IA. Flagged as `[GAP]`s on Story 1.2 and new Story 2.17 rather than designed here.

## 3. Recommended Approach

**Direct Adjustment** (per the requester's explicit instruction — the only option evaluated; Rollback and MVP-scope-reduction are not applicable, since nothing already built conflicts with this addition, and MVP scope only grows, it doesn't shrink). Effort: **Large** (13 new FRs, 11 new stories, ~8 new AD entries, 4 new domain entities). Risk: **Medium** — the Safety Engine's PRD-risk reversal and the dashboard `[GAP]`s need explicit stakeholder sign-off before build, but nothing here requires unwinding shipped code.

---

## 4. Detailed Change Proposals

### 4.1 PRD (`prd.md`)

**§4.2 Runtime Discovery — new FRs (insert after FR-33):**

```
#### FR-35: Page Readiness & configurable page load timeout `[ADDED 2026-07-29]`
Before the Runtime Observer captures a snapshot, the platform waits for a page to reach a
"ready" state — DOM-mutation quiescence plus network settling (application-relevant requests
only; polling/analytics patterns recognized and ignored) — up to a configurable maximum wait
ceiling (Page Load Timeout). Reaching the ceiling without settling logs a DISC-004 event
(FR-45) and proceeds with a best-effort snapshot rather than blocking the run.

**Consequences (testable):**
- A configurable Page Load Timeout exists at both a project (Application) default and a
  per-run override; V1 exposes it as a backend/config-level setting only — no UI control is
  built this pass (a future UI can read/write the same setting without further backend change).
- Every infinite-scroll/pagination iteration (FR-36) also gates on this same readiness check.

#### FR-36: Infinite scroll & pagination sampling `[ADDED 2026-07-29]`
After a scroll or "Load More" action, the platform samples a bounded number of iterations
(2-3), validates via the State Identity Engine (FR-37) that newly revealed items fingerprint
as SAME as items already seen in that region, then stops and marks the region "sampled" —
handing control back to the Planner — rather than scrolling/paginating indefinitely. A hard
per-page scroll/pagination budget applies regardless of validation outcome.

**Consequences (testable):**
- A genuinely repeating list (e.g. a claims grid) is sampled, not exhaustively paginated.
- A list whose structure changes every few items still terminates at the hard budget.

#### FR-37: State Identity Engine — SAME / VARIANT / NEW classification `[ADDED 2026-07-29]`
`[SUPERSEDES the page-fingerprint-dedup clause of FR-6 and extends FR-30's Application Model
Builder]` Every observed state (page, dialog, or scrolled-in item) is classified against
previously-seen states via a weighted comparison (route template, heading, action-set overlap,
form-set overlap, nav breadcrumb match, structural similarity) against two configurable
thresholds, yielding SAME (discarded — different data, identical behavior), VARIANT (a new
Page row written, sibling of the route's existing state, via a new `variant_of_page_id`
self-reference — distinct from `merged_into_id`'s "duplicate" meaning), or NEW (a full new
Page/state/actions/transitions written). Ambiguous cases (score between the two thresholds)
may consult the AI provider for a supporting, non-authoritative opinion (mirrors FR-8's
existing AI-assists-deterministic-reasoning pattern).

**Consequences (testable):**
- `/claims/1001` and `/claims/1002`, both status=Pending, classify SAME and are not
  separately explored.
- `/claims/1001` (Draft, Actions: Edit/Submit) and `/claims/1002` (Pending, Actions:
  Approve/Reject) classify VARIANT despite the shared route template, and both remain
  available to Inference (FR-8) as separate testable journeys.
- Comparison thresholds are stored as configuration, not hardcoded, and are tunable per
  Application.

**Notes:** Comparison happens against an in-process runtime cache scoped to one
`DiscoveryActivity` execution (rebuilt from canonical `Page` rows on Activity start) — not a
new persistent cache tier. See Architecture AD-16.

#### FR-38: Action Priority Model `[ADDED 2026-07-29]`
`[SUPERSEDES the "navigation-first" clause of FR-6]` Every candidate action is tagged Tier 1
(in-page: buttons, forms, expand/collapse, filters, in-page tab switches, scroll/"Load More"
triggers) or Tier 2 (navigation-intent: primary nav links, sidebar/menu items, breadcrumb
links). For a given state, all untried Tier 1 actions — including finishing any infinite-scroll
sampling (FR-36) — are processed before any Tier 2 action, so a page is never abandoned before
its own actions are explored. Tiering is decided deterministically (ARIA/landmark role,
route-changing href vs. same-page anchor, layout position) with AI as a fallback for genuinely
ambiguous cases only (mirrors FR-8's pattern).

**Consequences (testable):**
- A page with 3 untried buttons and 1 untried nav link processes all 3 buttons before the nav
  link, even though the previous "navigation-first" rule would have preferred an unvisited
  navigation target.

**Notes:** This is a genuine priority-order reversal from the current AD-15 rule for the
untried-in-page-action-vs-unvisited-nav case specifically — see Architecture note.

#### FR-39: Safety Engine — action classification & post-action verification `[ADDED 2026-07-29]`
`[REVERSES PRD §12 Risk item 6's "no guardrail, accepted risk" decision — flagged for explicit
sign-off, see §12 below]` Every candidate action is classified Safe (View/Expand/Navigate/
Filter/Search/Pagination — executed automatically), Clearly Destructive (Delete/Terminate/
Payment/Transfer — never executed), or Ambiguous/state-changing (Submit/Approve/Reject/Save/
Confirm — deferred to the Blocked Frontier, FR-42, not guessed). Classification is
verb/pattern-based with an AI-assisted opinion for ambiguous language, but the Safety Engine
owns the final verdict; the conservative default under genuine uncertainty is DEFER. After a
Safe action executes, a lightweight before/after indicator comparison (record count, status
field) flags an unexpected change as a safety-classification anomaly in the end-of-run report
— visibility only, does not block the crawl.

**Consequences (testable):**
- A "Delete" button is never clicked by the crawler in V1, regardless of page context.
- A "Submit"/"Approve" action is deferred (Blocked Frontier, "approval" reason) rather than
  executed speculatively.

#### FR-40: Data Resolver — structured input resolution `[ADDED 2026-07-29]`
`[Formalizes and extends the existing generic-value-filling behavior built in Story 2.2]` When
an action needs input, resolution is attempted in strict order: (1) a usable value already
visible on the current page, (2) a value observed earlier in this Discovery Run, (3) safe
synthetic data for generic fields or a placeholder file for a file-upload widget, (4)
business-specific data that can't be synthesized — the action is deferred to the Blocked
Frontier ("data" reason, FR-42) rather than guessed. Every resolved value (including synthetic
ones) is logged against the run for later traceability (FR-45's error/synthetic-data report).

**Consequences (testable):**
- A visible claim number on the current page is reused rather than re-synthesized.
- A field requiring a real Policy Number blocks rather than receiving a fabricated value.

#### FR-41: Widget coverage — tabs, dialogs, multi-window, file upload `[ADDED 2026-07-29]`
The platform detects and handles, via ARIA/accessibility-tree signals first (structural
heuristics as a lower-confidence fallback for non-standard markup): tab groups (each tab a
Tier-1 candidate, FR-38), dialogs/modals/popups (contents observed as a nested state per FR-37,
with reliable detection of the dialog's own close action), new browser tabs/windows (followed
if same-origin/in-scope, deferred with focus returned to the original tab otherwise), and file
upload inputs (routed to the Data Resolver, FR-40, using safe generated placeholder files).

**Consequences (testable):**
- Switching a tab reveals content that gets fingerprinted as its own state, not silently
  ignored.
- A modal's Escape/Cancel/"X" is exercised to safely return to the underlying page rather than
  stranding the crawl inside the dialog.

#### FR-42: Blocked Frontier `[ADDED 2026-07-29]`
An action the Safety Engine (FR-39) defers, or a field the Data Resolver (FR-40) can't resolve,
does not stop the run — it's parked, and the Planner continues elsewhere. Requirements with
identical content (e.g. four pages all needing "Active Policy Number") are aggregated into one
consolidated ask, presented to the user only after autonomous exploration is otherwise
exhausted and the area is meaningful enough — the user may always choose to finish without
supplying it.

**Consequences (testable):**
- Four pages needing the same missing field surface as one request, not four.
- A blocked action never halts exploration of the rest of the Application.

#### FR-43: Blocked mid-exploration — persistence & resume `[ADDED 2026-07-29]`
When a block occurs after several steps have already succeeded, the platform persists the
full step-by-step path from the start of the run to the block point — not just the blocking
step — as an ordered `ExplorationStep` sequence referencing already-confirmed `Page` rows (not
duplicating their content), including the exact input values used at each step (synthetic
values included, verbatim, not "regenerate here"). On resume: the supplied value is validated
first (staleness check), a new browser session is started (no assumption the old one
survived), every already-succeeded step is replayed exactly as stored (or, where a step already
caused an irreversible server-side effect, skipped in favor of navigating directly to its
resulting state, to avoid a non-idempotent replay creating a duplicate record), the new value
is supplied at the blocked step, and exploration continues downstream.

**Consequences (testable):**
- A 7-step path that blocks at step 7 stores all 7 steps; resuming replays 1–6 before
  attempting 7 again.
- A step that already created a real record is not blindly re-executed on replay.

#### FR-44: Save-as-Project — cross-session persistence `[ADDED 2026-07-29]`
`["Project" maps onto the existing Application entity — no new entity]` A user may pause an
entire discovery effort and resume it later, from any session, without re-exploring anything
already confirmed. `DiscoveryRun.status` gains a `paused` value. On resume: the confirmed
Application Model, the list of open Blocked items (FR-42/43), and the remaining exploration
queue are loaded; the platform re-authenticates fresh (no live session assumed); already-
confirmed states are never re-explored.

**Consequences (testable):**
- Pausing and resuming a project days later does not re-crawl already-confirmed pages.
- The dashboard shows Confirmed/Blocked/Remaining counts for a paused project. `[GAP — no
  supporting screen in current UX; see Story 1.2 note]`

#### FR-45: Crash recovery & error handling `[ADDED 2026-07-29]`
Engine-side crashes (process/container restart mid-run) recover automatically via the same
continuous checkpointing Save-as-Project (FR-44) already requires — no separate mechanism.
Target-application-side failures (5xx, broken render, repeated timeouts past the Page Load
Timeout, FR-35) are retried a small bounded number of times, then marked `Errored` (a new,
explicit state category, not silently misclassified as NEW) and the crawl continues elsewhere.
Every error surfaces both a fixed, documented machine-readable code (a starter taxonomy:
DISC-001 engine crash, DISC-002 auth expired, DISC-003 app unresponsive, DISC-004 page load
timeout, DISC-005 navigation lost, DISC-006 blocked-data, informational) and a human-readable
message with a suggested next action.

**Consequences (testable):**
- A worker restart mid-crawl resumes from the last checkpoint rather than restarting the run.
- A page that 500s twice is marked Errored and excluded from the exploration queue, not
  retried forever.

#### FR-46: Loop prevention safeguards `[ADDED 2026-07-29]`
`[Consolidates existing state-dedup/route-normalization behavior with new backstops]` Before
any action executes: state dedup (FR-37), action-history check (already executed this exact
action from this state?), transition-cycle detection (would this recreate A→B→A→B?), route
normalization (parameterized-duplicate sampling), infinite-scroll/pagination budget (FR-36),
and a final depth/action/scroll budget ceiling — in that order — are all deliberate,
configured safeguards, not the primary anti-loop mechanism (FR-36/FR-37 are).

#### FR-47: Test data carry-forward into Scenario Generation `[ADDED 2026-07-29]`
`[Extends FR-16, Epic 4]` Any test data value used to unblock an exploration path during
discovery (FR-43) — a user-supplied unblocking value or a Data-Resolver-synthesized value
(FR-40), including placeholder upload files — is retained and surfaced as the default test-data
value for that same input at Scenario Generation time, when a generated Scenario recreates a
path through that step, rather than regenerated or left blank.

**Consequences (testable):**
- A Scenario recreating a Policy Search step defaults to the same Policy Number value used to
  unblock discovery, not a blank field.
```

**§12 Risk and Mitigations — update item 6:**

```diff
- 6. **Risk**: `FR-6`'s autonomous form/API exercising has no destructive-action guardrail —
-    even in a Non-Production environment, the discovery engine could trigger irreversible
-    side effects... **Mitigation**: **Accepted risk** — V1 relies entirely on the customer
-    providing a properly isolated Non-Production environment (§11); no platform-side
-    guardrail is built in V1, by explicit decision.
+ 6. **Risk**: `[UPDATED 2026-07-29]` `FR-6`'s autonomous form/API exercising previously had no
+    destructive-action guardrail — even in a Non-Production environment, the discovery engine
+    could trigger irreversible side effects (real emails sent, shared test data deleted,
+    fraud-detection tripwires) if that environment isn't fully isolated from real-world
+    systems. **Mitigation**: `[REVERSED 2026-07-29]` No longer an accepted risk — the Safety
+    Engine (FR-39) classifies every candidate action Safe/Destructive/Ambiguous and never
+    executes a Clearly Destructive action; Ambiguous/state-changing actions defer to the
+    Blocked Frontier (FR-42) rather than executing speculatively. **Residual risk**: a
+    genuinely production-facing environment is still not technically verified as
+    non-production (Open Question 3, unchanged) — the Safety Engine narrows *what* the crawler
+    is willing to do, it does not verify *where* it's running.
```

**§6.1 MVP Scope — add bullet:**

```
- `[ADDED 2026-07-29]` The discovery engine's crawl-decision internals gain: page-readiness
  gating with a configurable load timeout, bounded infinite-scroll/pagination sampling, a
  three-way SAME/VARIANT/NEW state classification (FR-37, superseding the simpler
  page-fingerprint dedup), Tier-1-before-Tier-2 action ordering (FR-38, superseding
  navigation-first), a Safe/Destructive/Ambiguous Safety Engine (FR-39), a structured Data
  Resolver with deferral (FR-40), first-class tab/dialog/multi-window/file-upload handling
  (FR-41), a Blocked Frontier with mid-exploration persistence and resume (FR-42/43),
  cross-session Save-as-Project pause/resume (FR-44), crash recovery and a machine-readable
  error taxonomy (FR-45), and consolidated loop-prevention safeguards (FR-46). Test data used
  to unblock discovery carries forward into Scenario Generation defaults (FR-47).
```

**§9 Assumptions Index — append:**

```
- **2026-07-29 [Sprint Change Proposal — Discovery Engine Redesign]**: A user-authored
  Discovery Engine design document triggered FR-35 through FR-47 (page readiness, infinite
  scroll, State Identity Engine, Action Priority Model, Safety Engine, Data Resolver, widget
  coverage, Blocked Frontier + resume, Save-as-Project, crash recovery/error taxonomy, loop
  prevention, test-data carry-forward). This **reverses** §12 Risk item 6's prior "accepted
  risk, no guardrail" decision (now mitigated by the Safety Engine) — flagged for explicit
  sign-off, not a quiet change. Two items are flagged, not resolved, by this pass: (a) a
  naming collision between the document's "Journey" (crawl-time exploration path) and the
  existing `Journey` domain entity (AI-inferred business journey) — resolved here by naming
  the new concept `ExplorationPath`/`ExplorationStep`; (b) Save-as-Project's dashboard
  (Confirmed/Blocked/Remaining counts) and the Blocked-item review/resume surface have no
  home in the current 6-screen UX — flagged as `[GAP]`s on Story 1.2 and new Story 2.17,
  not designed in this pass. No epic added/removed/resequenced; all new scope lives in 11 new
  Epic 2 stories (2.9–2.19) plus AC amendments to Stories 1.2, 2.2, 2.3, 2.5, 4.1. See
  `sprint-change-proposal-2026-07-29.md`.
```

### 4.2 Architecture (`ARCHITECTURE-SPINE.md`)

**New domain entities** (add to Structural Seed's `packages/domain` list and Core-Entity ERD):

- `Page` gains two new nullable columns: `variant_of_page_id` (self-FK — VARIANT sibling, distinct from `merged_into_id`'s "superseded duplicate" meaning) and behavior/scroll-signal metadata needed by the Runtime Observer (enabled/disabled, visible/hidden, validation-message text, scroll position, content height, item count) — stored as columns or a small JSONB `observed_signals`, implementer's choice, not prescribed here.
- `DiscoveryRun.status` gains a fourth value: `paused` (alongside `running | complete | failed`).
- `DiscoveryRun`/`Application` gain a `page_load_timeout_seconds` (nullable int; per-run override on `DiscoveryRun`, project default on `Application`, run value wins when set).
- New table `BlockedTask` (`id`, `application_id` FK, `discovery_run_id` FK, `status` [`blocked_data|blocked_approval|blocked_both|resolved`], `required_description` text, `required_type`, `created_at`, `resolved_at` nullable).
- New table `ExplorationStep` (`id`, `blocked_task_id` FK, `step_order` int, `page_id` FK — references the confirmed `Page`, does not duplicate it, `action_description`, `input_values` JSONB, `created_at`). `UNIQUE(blocked_task_id, step_order)`.
- New table `SyntheticDataEntry` (`id`, `application_id`, `discovery_run_id`, `page_id` nullable FK, `field_name`, `value`, `is_placeholder_file` bool, `created_at`) — logged for every run, not only blocked ones (PRD FR-40/47).
- New table `DiscoveryError` (`id`, `application_id`, `discovery_run_id`, `page_id` nullable FK, `error_code` [DISC-001..006], `message`, `retry_count`, `created_at`).

**New AD entries (insert after AD-15):**

```
### AD-16 — State Identity Engine runs against an in-process runtime cache, not a new
persistent tier `[NEW 2026-07-29]`

- **Binds:** FR-37
- **Prevents:** Introducing Redis (or any new stateful service) before it's proven necessary —
  YAGNI applied to infra, not just code.
- **Rule:** The SAME/VARIANT/NEW comparison runs against a plain in-process cache scoped to one
  `DiscoveryActivity` execution, rebuilt from canonical (`merged_into_id IS NULL`) `Page` rows
  at Activity start. This is sufficient because Save-as-Project resume (AD-20) relies on the
  *permanent* DB's canonical rows for "don't re-explore what's confirmed," never on the runtime
  cache surviving a pause. Add a real distributed cache only if a single-process cache
  measurably can't keep up — not speculatively.

### AD-17 — Action Priority Model supersedes AD-15's navigation-first rule `[NEW 2026-07-29]`

- **Binds:** FR-38 (supersedes FR-6's navigation-first clause, AD-15 rule 5)
- **Prevents:** Two competing action-ordering rules coexisting in the codebase — the old
  "prefer unvisited nav over repeating an already-done same-page action" and the new "finish
  all untried Tier-1 in-page actions before any Tier-2 navigation" disagree on the
  untried-in-page-action-vs-unvisited-nav case, which the old rule never actually addressed but
  which is exactly the case that motivated this change (a page left prematurely before its own
  actions are explored).
- **Rule:** Every candidate action carries a Tier 1 (in-page) or Tier 2 (navigation-intent) tag,
  assigned deterministically (ARIA/landmark role, route-changing href, layout position) with AI
  as a fallback only for genuinely ambiguous cases (mirrors AD-3's AI-assists-deterministic
  pattern). The Exploration Planner exhausts all untried Tier 1 actions on a state — including
  finishing any AD-18 scroll/pagination sampling — before considering any Tier 2 action. AD-15's
  "navigation-first" label is retired; its underlying repeated-interaction-avoidance behavior is
  retained as one of AD-22's loop-prevention backstops, not as a competing priority rule.

### AD-18 — Infinite scroll/pagination is sampled and validated, never crawled to exhaustion
`[NEW 2026-07-29]`

- **Binds:** FR-36
- **Rule:** After a scroll/"Load More" action, a bounded sample (2-3 iterations) is compared via
  AD-16's State Identity Engine; consecutive SAME classifications confirm a repeating pattern,
  at which point the region is marked sampled and control returns to the Planner. A hard
  scroll/pagination budget per page applies regardless of validation outcome (AD-22).

### AD-19 — Safety Engine classification is a distinct step, before Data Resolution
`[NEW 2026-07-29]`

- **Binds:** FR-39
- **Prevents:** An action being executed (or its input resolved) before its safety
  classification is known — resolving data for an action that turns out to be destructive would
  be wasted work at best, a false sense of "we tried" at worst.
- **Rule:** The Exploration Planner asks the Safety Engine before the Data Resolver. Clearly
  Destructive → SKIP immediately, Data Resolver never consulted. Safe or Ambiguous → proceed to
  Data Resolution; an Ambiguous action that *does* resolve its data still lands in the Blocked
  Frontier (AD-20) for approval, it is never executed on the strength of having data alone. A
  Safe action gets a lightweight before/after indicator check post-execution; a detected
  anomaly is logged, visibility-only, never blocking.

### AD-20 — Blocked Frontier persists full exploration paths, referencing confirmed Pages, never
duplicating them `[NEW 2026-07-29]`

- **Binds:** FR-42, FR-43
- **Prevents:** A resumed blocked path being unreconstructable because only the blocking step
  was recorded, or the path record duplicating already-confirmed Page data instead of
  referencing it.
- **Rule:** `BlockedTask` is one row per blocked path; `ExplorationStep` is one row per step in
  it, ordered by `step_order`, each referencing (not duplicating) an already-confirmed `Page` via
  FK, and storing the exact action + input values used (synthetic values included verbatim).
  Aggregation of requirements with identical content into one consolidated ask (FR-42) is
  resolved at read time from open `BlockedTask` rows sharing the same `required_description`,
  not a separate aggregation table. `[NAMING]` This entity is `ExplorationStep`, deliberately not
  `JourneyStep` — it exists before, and independent of, whether `InferenceActivity` ever creates
  a `Journey` from this path; conflating the two names would be a standing source of confusion
  between a crawl-time path and the Trusted Knowledge Model's `Journey` entity.

### AD-21 — Resume replays confirmed steps, skips non-idempotent ones already succeeded
`[NEW 2026-07-29]`

- **Binds:** FR-43
- **Rule:** On resume, the supplied value is validated (staleness check) before any replay
  starts; a new browser session is always started (no assumption the blocking session
  survived); each `ExplorationStep` is replayed via its stored action/inputs, except a step
  that already caused a known-irreversible server-side effect (e.g. a "Create Order" submit),
  which is instead skipped in favor of navigating directly to its already-reached resulting
  Page — preventing a duplicate real-world record from a blind re-submit. Where this
  cannot be generalized across target applications, flag it as an app-specific open question at
  implementation time (matches the document's own acknowledged gap) rather than guessing.

### AD-22 — Save-as-Project pause/resume maps onto the existing Application entity; no new
Project table `[NEW 2026-07-29]`

- **Binds:** FR-44
- **Prevents:** A parallel "Project" concept duplicating what `Application` (already
  Organization-scoped, already the durable re-discovery unit per AD-13/FR-15) already provides.
- **Rule:** `DiscoveryRun.status` gains `paused`. Every fingerprint-cache lookup (AD-16),
  `BlockedTask`, and remaining-exploration-queue entry is scoped by the existing
  `application_id` — pausing/resuming is a matter of filtering by that ID, not a new grouping
  mechanism. On resume: re-authenticate fresh (no live session assumed, matching AD-11's
  existing session-expiry philosophy), load canonical `Page`/`Journey` rows and open
  `BlockedTask` rows, and never re-explore an already-canonical state.

### AD-23 — Crash recovery is continuous checkpointing; errors are typed, not silent
`[NEW 2026-07-29]`

- **Binds:** FR-45
- **Rule:** Every `Page`/`Action`/`ApiEndpoint`/`PageTransition` write (already real-time per
  AD-8) doubles as the engine's crash checkpoint — no separate checkpoint mechanism. On worker
  restart, `DiscoveryActivity` resumes from the last confirmed-safe point via the same
  `paused`-aware resume path as AD-22, treating any action in-flight at crash time as
  unconfirmed and re-verifying rather than assuming success. A target-application failure (5xx,
  broken render, or a DISC-004 timeout past AD-1[FR-35]'s Page Load Timeout) is retried a small
  bounded number of times, then written as a `DiscoveryError` row (not a `Page` row, not
  misclassified as NEW) and the crawl continues elsewhere. Every `DiscoveryError` carries both a
  fixed `error_code` (DISC-001..006 starter taxonomy) and a human-readable message —
  machine-readable for logs/support correlation, human-readable for the UI, never one without
  the other.
```

**AD-15 — add a one-line supersession note at the top:**

```
`[PARTIALLY SUPERSEDED 2026-07-29 — see AD-17]` Rule 5 ("navigation-first") is superseded by the
Action Priority Model (AD-17/FR-38) for the untried-in-page-action-vs-unvisited-nav case; rules
1-4 (page-fingerprint dedup, representative-action/form sampling, error-destination handling,
button-triggered-navigation-continuation) are unaffected and remain in force, now read
alongside AD-16's SAME/VARIANT/NEW classification (FR-37) rather than as the sole dedup
mechanism.
```

**Module Map — new row:**

```
| **Discovery Decision Engine** `[NEW 2026-07-29]`<br>`apps/workers/discovery` (Exploration
Planner, State Identity Engine, Safety Engine, Data Resolver) | Classify observed states
(SAME/VARIANT/NEW), tag/order candidate actions by priority tier, classify action safety,
resolve action input, decide EXECUTE/DEFER/SKIP | FR-36–FR-42, FR-46 | Observed page/action
signal from `DiscoveryActivity` | Execution decisions; `BlockedTask`/`ExplorationStep`/
`SyntheticDataEntry` rows on DEFER | `packages/domain` (AD-16, AD-19, AD-20) | A new safety
verb, comparison threshold, or resolution rule is isolated here — never touches the crawl-walk
mechanics (page traversal, form-filling primitives) `DiscoveryActivity` itself owns. |
```

**Deferred section — append:**

```
- **`[NEW — 2026-07-29]` Redis/distributed runtime cache**: deliberately not built now (AD-16) —
  an in-process cache scoped to one `DiscoveryActivity` execution is the V1 default. Revisit
  only if profiling shows a single-process cache is the actual bottleneck.
- **`[NEW — 2026-07-29]` Save-as-Project dashboard UX & Blocked-item review/resume UI**: FR-44's
  Confirmed/Blocked/Remaining dashboard and FR-42/43's "supply missing data / authorize action"
  surface have no equivalent in the current 6-screen IA (`DESIGN.md`/`EXPERIENCE.md`). Flagged
  on Story 1.2 (dashboard) and new Story 2.17 (review/resume) — not designed in this
  architecture pass; needs a UX design pass before implementation.
- **`[NEW — 2026-07-29]` Non-idempotent-replay generalization**: AD-21's "skip a step that
  already caused an irreversible effect" rule cannot be fully generalized across arbitrary
  target applications from architecture alone — flagged as an app-specific judgment call at
  implementation time, per the source document's own acknowledged gap (its Section 15.4).
```

### 4.3 Epics (`epics.md`)

**Epic 2 description — append one sentence:**

```
`[UPDATED 2026-07-29]` The Discovery module's internal crawl-decision engine gains page-readiness
gating, bounded infinite-scroll sampling, a three-way state-identity classification, tiered
action ordering, a Safe/Destructive/Ambiguous Safety Engine, structured data resolution with
deferral, first-class widget coverage (tabs/dialogs/multi-window/file-upload), a Blocked
Frontier with cross-session pause/resume (Save-as-Project), and crash recovery with a
machine-readable error taxonomy — see `sprint-change-proposal-2026-07-29.md`. No change to the
FR-14 discovery-gates-generation pipeline or Epic 3/4's curation/generation flow.
```

**FR Coverage Map — append:**

```
FR-35–FR-46: Epic 2 - Discovery engine redesign (page readiness, infinite scroll, State Identity
  Engine, Action Priority Model, Safety Engine, Data Resolver, widget coverage, Blocked
  Frontier + resume, Save-as-Project, crash recovery/error taxonomy, loop prevention)
  `[ADDED 2026-07-29]` — Stories 2.9-2.19
FR-47: Epic 4 - Test data carry-forward from discovery into Scenario Generation defaults
  `[ADDED 2026-07-29]` — Story 4.1 amendment
```

**New Story blocks (insert into Epic 2, after Story 2.8):**

> *(Each new story below is added to `epics.md` in full; full Tasks/Dev-Notes-level implementation-artifact files are created later via `bmad-create-story` when each is picked up, per this repo's existing convention — e.g. how Story 4.3 was handled on 2026-07-27.)*

```
### Story 2.9: Page Readiness & Infinite Scroll/Pagination Sampling `[ADDED 2026-07-29]`

As a user, I want the platform to wait for a page to genuinely finish loading before capturing
it, and to sample rather than endlessly scroll/paginate a repeating list, so that discovery
captures complete, accurate snapshots without stalling on unbounded content.

**Acceptance Criteria:**
- Given a page transition, when the Observer is about to capture a snapshot, then it waits for
  DOM-mutation quiescence and network settling (application-relevant requests only) up to a
  configurable Page Load Timeout (project default + per-run override), proceeding with a
  best-effort snapshot and a DISC-004 log entry if the ceiling is reached first (FR-35).
- Given a scroll/"Load More" action, when newly revealed items fingerprint as SAME as
  already-seen items for a bounded number of consecutive samples, then the region is marked
  sampled and exploration continues elsewhere; a hard per-page scroll/pagination budget applies
  regardless (FR-36).

### Story 2.10: State Identity Engine — SAME/VARIANT/NEW Classification `[ADDED 2026-07-29]`

As a user, I want the platform to tell genuinely new application behavior apart from the same
behavior with different data, so that discovery doesn't miss real variants or waste effort
re-exploring duplicates.

**Acceptance Criteria:**
- Given an observed state, when compared against previously-seen states sharing the same route
  template, then a weighted score (heading/action-set/form-set/nav/structural similarity)
  against two configurable thresholds yields SAME (discarded), VARIANT (new sibling Page row via
  `variant_of_page_id`), or NEW (full new Page/actions/transitions) (FR-37).
- Given a score between the two thresholds, when the classification is genuinely ambiguous, then
  the AI provider may supply a supporting, non-authoritative opinion — the State Identity Engine
  still owns the final verdict.
- Given the comparison runs during an active crawl, when checking prior states, then it reads
  from an in-process cache scoped to this Discovery Run's Activity execution (AD-16), not a new
  persistent cache tier.

### Story 2.11: Exploration Planner & Action Priority Tiering `[ADDED 2026-07-29]`

As a user, I want the platform to fully explore a page's own actions before navigating away from
it, so that no page's behavior is left partially understood because the crawler moved on too
soon.

**Acceptance Criteria:**
- Given a candidate action, when it is tagged, then it is classified Tier 1 (in-page) or Tier 2
  (navigation-intent) deterministically (ARIA/landmark role, href target, layout position), with
  AI as a fallback only for genuinely ambiguous cases (FR-38).
- Given a state with untried Tier 1 actions, when the Planner selects the next action, then every
  untried Tier 1 action (including finishing Story 2.9's scroll sampling) is exhausted before any
  Tier 2 action is attempted.
- Given all of a candidate action's specialist checks (State Identity, action history,
  transition-cycle, Safety Engine, Data Resolver), when the Planner combines their answers, then
  it reaches exactly one Execution Decision — EXECUTE / DEFER / SKIP — executed in tier order.

### Story 2.12: Safety Engine — Action Classification & Post-Action Verification `[ADDED
2026-07-29]`

As a user, I want the platform to never perform a clearly destructive action and to defer
ambiguous ones for explicit authorization, so that discovery can't cause irreversible side
effects in the target environment.

**Acceptance Criteria:**
- Given a candidate action, when classified, then it is Safe (executed automatically), Clearly
  Destructive (never executed), or Ambiguous/state-changing (deferred to the Blocked Frontier,
  Story 2.15, not guessed) (FR-39).
- Given genuine uncertainty even after an AI-assisted opinion, when the Safety Engine can't
  confidently classify Safe, then it defaults to DEFER, never EXECUTE.
- Given a Safe action just executed, when a before/after indicator comparison (record count,
  status field) shows an unexpected change, then it is flagged as a safety-classification
  anomaly in the end-of-run report — visibility only, does not block the crawl.

### Story 2.13: Data Resolver — Structured Input Resolution `[ADDED 2026-07-29]`

As a user, I want the platform to reuse real or safely-synthesized data before ever guessing
business-specific values, so that generated coverage uses trustworthy inputs and never
fabricates data it shouldn't.

**Acceptance Criteria:**
- Given an action needing input, when resolving a value, then the platform tries, in order: a
  value visible on the current page, a value observed earlier this run, safe synthetic data (or
  a placeholder file for uploads) for generic fields, then defers to the Blocked Frontier for
  business-specific data it can't resolve (FR-40).
- Given any value is used (including synthetic), when the action executes, then the value is
  logged against the run for later traceability (Story 2.18's reporting).

### Story 2.14: Widget Coverage — Tabs, Dialogs, Multi-Window, File Upload `[ADDED 2026-07-29]`

As a user, I want the platform to correctly handle tabs, modals, new browser windows, and file
uploads across any frontend framework, so that discovery doesn't silently skip or get stranded
by common enterprise UI patterns.

**Acceptance Criteria:**
- Given a tab-group widget (ARIA `role="tablist"`/`"tab"`), when detected, then each tab is a
  Tier-1 candidate action whose resulting content is observed and fingerprinted as its own state
  (FR-41).
- Given an action opens a dialog/modal/popup, when its contents are observed, then they are
  fingerprinted as a nested state, and the dialog's own close action (Escape/"X"/Cancel) is
  reliably detected and exercised to safely return to the underlying page.
- Given an action opens a new browser tab/window, when it is same-origin and in-scope, then it
  is followed as a linked sub-flow; when cross-origin or out-of-scope, it is deferred and focus
  returns to the original tab.
- Given a `type="file"` input, when encountered, then it is routed to the Data Resolver (Story
  2.13) for a safe generated placeholder file, logged the same as any synthetic value.
- Given an element with no standard ARIA role, when detected, then structural heuristics apply
  as a fallback, flagged with lower confidence for later review.

### Story 2.15: Blocked Frontier — Aggregated Deferral `[ADDED 2026-07-29]`

As a user, I want blocked exploration areas that need the same missing data consolidated into
one request, so that I'm not asked the same question once per page.

**Acceptance Criteria:**
- Given the Planner reaches a DEFER decision, when a `BlockedTask` is created or updated, then
  it is checked against existing open requirements with identical required content and
  aggregated rather than duplicated (FR-42).
- Given a blocked area, when autonomous exploration is otherwise exhausted and the area is
  meaningful, then one consolidated request is presented, with an explicit option to finish
  without supplying it.
- Given a DEFER from the Safety Engine (approval needed) versus the Data Resolver (data needed),
  when a `BlockedTask` is written, then both use the identical `BlockedTask` structure and resume
  path — only `required_type` differs; a single blocked path may carry both requirements at once.

### Story 2.16: Blocked Mid-Exploration — Path Persistence & Resume `[ADDED 2026-07-29]`

As a user, I want a blocked exploration path's full route from the start of the run to be
remembered, so that supplying the missing data later resumes exactly where it left off instead
of losing everything already discovered along the way.

**Acceptance Criteria:**
- Given a block occurs after N successful steps, when the `BlockedTask` is written, then all N
  steps are persisted as ordered `ExplorationStep` rows referencing their already-confirmed
  `Page` (not duplicating it), including the exact input values used at each step, verbatim
  (FR-43).
- Given a user supplies the missing value, when resume begins, then the value is validated first
  (staleness check), a new browser session starts (no assumption the old one survived), and every
  already-succeeded step is replayed via its stored action/inputs — except a step that already
  caused a known-irreversible effect, which is instead skipped in favor of navigating directly to
  its resulting Page, to avoid creating a duplicate record.
- Given a resumed path reaches its previously-blocked step, when the new value/authorization is
  supplied, then the `BlockedTask` is marked Resolved and exploration continues downstream.
- Given a single exploration path, when it blocks a second time later in its own continuation,
  then the same `BlockedTask`/step-list record is extended, not replaced with a new, unrelated
  record.

### Story 2.17: Save-as-Project — Cross-Session Pause & Resume `[ADDED 2026-07-29]`

As a user, I want to pause an entire in-progress discovery effort and resume it later without
losing progress or re-exploring what's already confirmed, so that missing test data doesn't
force me to finish everything in one sitting.

**Acceptance Criteria:**
- Given a running Discovery Run, when the user pauses it, then `DiscoveryRun.status` is set to
  `paused`; the confirmed Application Model, open `BlockedTask`s, and the remaining exploration
  queue are all already durable (no new persistence mechanism needed beyond what Stories
  2.15/2.16/2.2 already write) (FR-44).
- Given a paused project, when the user resumes it (same or different session), then the
  platform re-authenticates fresh, loads the confirmed model and open Blocked items, and does
  not re-explore any already-canonical state.
- `[GAP — flagged, not designed here]` The dashboard surfacing Confirmed/Blocked/Remaining
  counts and Paused status (per the source document's worked example) has no equivalent screen
  in the current 6-screen IA (`DESIGN.md`/`EXPERIENCE.md`) — needs a UX pass before this AC's
  frontend half can be built; see Story 1.2's amendment note.

### Story 2.18: Crash Recovery & Error Taxonomy `[ADDED 2026-07-29]`

As an operator, I want engine crashes to recover automatically and target-application failures
to be logged with both a machine-readable code and a plain-language explanation, so that
transient infrastructure or target-app issues don't silently corrupt or truncate a discovery
run's results.

**Acceptance Criteria:**
- Given an engine-side crash (process/container restart mid-run), when the worker restarts, then
  `DiscoveryActivity` resumes from the last checkpointed (already-committed typed row) position,
  treating any in-flight action at crash time as unconfirmed and re-verifying rather than
  assuming success — no separate checkpoint mechanism beyond existing real-time typed-row writes
  (FR-45).
- Given a target-application failure (5xx, broken render, or a Story 2.9 Page Load Timeout),
  when it recurs after a small bounded number of retries, then the branch is written as a
  `DiscoveryError` row (`Errored`, not misclassified as NEW or silently dropped) and exploration
  continues elsewhere.
- Given any `DiscoveryError`, when surfaced, then it carries both a fixed `error_code`
  (DISC-001..006 starter taxonomy) and a human-readable message with a suggested next action —
  the end-of-run report lists Errored branches alongside Blocked and Skipped-Unsafe items.

### Story 2.19: Loop Prevention Consolidation `[ADDED 2026-07-29]`

As a user, I want all of the discovery engine's anti-loop safeguards to run consistently before
any action executes, so that a pathological page pattern can't stall a run even when the primary
sampling mechanisms (State Identity, infinite-scroll sampling) don't catch it.

**Acceptance Criteria:**
- Given a candidate action about to execute, when the Planner checks it, then it applies, in
  order: state dedup (Story 2.10), action-history check, transition-cycle detection
  (A→B→A→B), route normalization (parameterized-duplicate sampling), the infinite-scroll/
  pagination budget (Story 2.9), and a final depth/action/scroll budget ceiling (FR-46).
- Given these checks are backstops, when Story 2.9/2.10's primary sampling mechanisms already
  prevent a specific loop, then this story does not duplicate that logic — it adds the checks
  not already covered (action-history tracker, transition-cycle detection are the two genuinely
  new pieces here).
```

**Story 2.2 — add supersession note (append to its existing header note):**

```
`[PARTIALLY SUPERSEDED 2026-07-29]` AC 4 (page-fingerprint dedup) and AC 6
(representative-action sampling) remain in force as crawl-time, in-run optimizations, but are
now read alongside Story 2.10's State Identity Engine (SAME/VARIANT/NEW), which is the
authoritative cross-state comparison going forward. AC 5 (navigation-first) is superseded by
Story 2.11's Action Priority Model for the untried-in-page-action-vs-unvisited-nav case — see
`sprint-change-proposal-2026-07-29.md` and Architecture AD-17.
```

**Story 2.3 — add one AC (Completion reporting):**

```
**`[ADDED 2026-07-29]` Given** a Discovery Run reaches `DiscoveryRun.status=complete`
**Then** the completion report includes counts of Blocked items (Story 2.15), Skipped-Unsafe
items (Story 2.12), and Errored branches (Story 2.18), alongside confirmed states/journeys —
none of these categories block completion; a run can legitimately complete with open items in
any of them (FR-42/FR-45).
```

**Story 2.5 — add clarifying note (no AC change):**

```
`[NOTE — 2026-07-29]` Story 2.10's State Identity Engine (SAME/VARIANT/NEW) runs *during* the
crawl, against an in-process cache — it does not replace this story's cross-run
`merged_into_id` canonicalization, which still runs after Discovery completes and additionally
catches duplicates across separate Discovery Runs (e.g. re-discovery) that the in-run cache
never saw. The two mechanisms are complementary: Story 2.10 avoids over-exploring within one
run; this story still owns cross-run canonicalization.
```

**Story 1.2 — add `[GAP]` note (no AC change to the existing Home behavior):**

```
`[GAP — flagged 2026-07-29, not resolved here]` Story 2.17 (Save-as-Project) specifies a
dashboard showing Confirmed/Blocked/Remaining-to-Explore counts and a "Paused — Action Needed"
status for a paused project. The current Home screen's single persistent Application card (this
story's 2026-07-27 AC) has no such counts or paused-state treatment. Needs a UX design pass
before Story 2.17's frontend half can be built — do not read this note as authorizing ad hoc UI
invention against it.
```

**Story 4.1 — add one AC (test-data carry-forward):**

```
**`[ADDED 2026-07-29]` Given** a generated Scenario recreates an exploration path that passed
through a step which used discovery-time test data (a user-supplied unblocking value, Story
2.16, or a Data-Resolver-synthesized value, Story 2.13, including a placeholder upload file)
**Then** that same value is surfaced as the default Test Data value for that step, not
regenerated or left blank (FR-47).
```

### 4.4 `sprint-status.yaml`

Add under `epic-2:` (all `backlog` — no implementation-artifact story file exists yet; created
later via `bmad-create-story` when picked up, per this repo's existing convention):

```yaml
  2-9-page-readiness-infinite-scroll-pagination: backlog   # ADDED 2026-07-29
  2-10-state-identity-engine: backlog                       # ADDED 2026-07-29
  2-11-exploration-planner-action-priority-tiering: backlog # ADDED 2026-07-29
  2-12-safety-engine: backlog                                # ADDED 2026-07-29
  2-13-data-resolver: backlog                                 # ADDED 2026-07-29
  2-14-widget-coverage: backlog                                # ADDED 2026-07-29
  2-15-blocked-frontier: backlog                                # ADDED 2026-07-29
  2-16-blocked-mid-exploration-persistence-resume: backlog      # ADDED 2026-07-29
  2-17-save-as-project: backlog                                  # ADDED 2026-07-29
  2-18-crash-recovery-error-taxonomy: backlog                     # ADDED 2026-07-29
  2-19-loop-prevention-consolidation: backlog                      # ADDED 2026-07-29
```

Add a `last_updated`/header changelog line noting this proposal, matching existing convention.

---

## 5. Implementation Handoff

**Scope classification: Moderate-to-Major.** No epic added/removed/resequenced and no existing
shipped code is invalidated (Moderate-shaped), but two items genuinely need stakeholder sign-off
before build, not just backlog reorganization (Major-shaped):

1. **§12 Risk item 6 reversal** (Safety Engine) — a deliberate PRD decision is being undone;
   whoever owns risk acceptance for this PRD should explicitly re-confirm, not just inherit it
   via a backlog addition.
2. **Two UX `[GAP]`s** (Save-as-Project dashboard, Blocked-item review/resume surface) need a
   UX design pass (Sally/`bmad-ux`) before Stories 2.15/2.16/2.17's frontend halves, and Story
   1.2's amendment, can be implemented — they are not designed in this pass.

**Recommended routing:**
- PRD/Architecture/Epics edits above → **Developer agent**, direct implementation of the
  planning-doc changes (this is a documentation change, not a code change — safe for direct
  application once approved).
- Full story-file creation (Tasks/Dev Notes/References) for Stories 2.9–2.19 → **`bmad-create-
  story`**, one at a time, when each is picked up for development (matching how Story 4.3 was
  handled).
- The two flagged sign-offs above → **Product Manager**, before any of Stories 2.12, 2.15,
  2.16, 2.17 move past `backlog`.
