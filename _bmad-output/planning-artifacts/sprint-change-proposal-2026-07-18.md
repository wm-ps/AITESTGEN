---
title: "Sprint Change Proposal — Application Model Builder & Crawl Engine Redesign (2026-07-18)"
status: approved
created: 2026-07-18
approved: 2026-07-18
---

## 0. Approval Record

Approved by Harsha, 2026-07-18, as drafted — no deviations. PRD, Architecture, and Epics/Stories updated the same day per §4 below; `sprint-status.yaml` updated per §4.C.

**`[CORRECTION — 2026-07-18, same day]`** This proposal's initial story numbering (below, §2/§4.C) numbered Application Model Builder as **Story 2.6**, coming *after* AI Journey/Capability Inference (**Story 2.5**) — backwards from the actual pipeline order this proposal itself specifies (Discovery → Model Builder → Inference). Corrected: **Application Model Builder is Story 2.5**; **AI Journey/Capability Inference is renumbered to Story 2.6**. The rest of this document (§1–§5 below) has been updated in place to reflect the corrected numbering — treat every "Story 2.5"/"Story 2.6" reference below as already-corrected, not as the original (backwards) draft.

# Sprint Change Proposal — Application Model Builder & Crawl Engine Redesign

## 1. Issue Summary

Harsha proposed a deeper technical redesign of the crawl → discovery → generation pipeline, driven by a written architecture pitch ("Enterprise Application Crawl Engine — Architecture & Technical Design"). The core idea: instead of the crawler capturing flat, generic `Evidence` rows (`type` + JSONB `details`) that AI inference reads directly, insert a new **Application Model Builder** stage that normalizes raw crawl observations into a structured, reusable application model — Pages, Components, Forms, Actions, APIs, Assertions, and Page Transitions, each with automation metadata (preferred + fallback locators, target page, validation rules). AI Journey/Capability inference and Playwright generation then work from this structured model instead of raw per-page JSONB.

This is not a pre-implementation replan. **Epic 2's stories (2.1–2.5 — discovery run start, evidence capture, stop conditions, session expiry, AI inference) are already implemented and sitting in code review.** Real code exists today: [`evidence.py`](../../../packages/domain/src/domain/evidence.py) (flat Evidence table), [`crawler.py`](../../../apps/workers/discovery/src/discovery_worker/crawler.py) (BFS traversal, clicks every standalone button with no representative-action sampling), and `InferenceActivity` (reads raw Evidence directly). Epic 3/4 are `ready-for-dev`, not started.

**Confirmed decisions (this session):**
- Epic 2 is reworked to match the new design, not layered on top or left as-is — the in-review implementation is revised before being accepted, not rolled back after merge (nothing is merged/shipped yet).
- Playwright generation stays AI-generated; the Component Model's locator/automation metadata becomes richer *context* fed to the existing `AIProvider.generate_playwright` call, not a template-driven codegen replacement.

## 2. Impact Analysis

### Epic Impact

| Epic | Impact |
|---|---|
| Epic 1 (Onboarding) | None. FR-1–3 untouched. |
| Epic 2 (Runtime Discovery & AI Journey Inference) | **Rework.** Story 2.2 (evidence capture) gains page-fingerprint dedup, navigation-first prioritization, and representative-action sampling. A **new Story 2.5 (Application Model Builder)** is added — normalizes captured signal into Page/Component/Form/Action/API/Assertion/PageTransition entities. Story 2.6 (AI inference, renumbered from 2.5) is rewired to read the structured Application Model instead of raw Evidence. |
| Epic 3 (Human Curation) | No functional change — curation still operates on Journey/Capability. Optional future enhancement: FR-23's evidence detail panel could render structured Component/locator detail instead of raw JSONB (not required for this change). |
| Epic 4 (Scenario & Playwright Generation) | **Light rework.** Stories 4.1/4.2's external Activity contracts (`ScenarioGenerationActivity`, `PlaywrightGenerationActivity`) are unchanged — only the internal context assembled for the AI call changes (Component Model instead of raw Evidence). No AC rewrite needed beyond a note on context source. |
| Epics 5–7 | Unaffected (already removed 2026-07-15). |

No new epic is needed — this fits inside Epic 2 (new story) plus a light Epic 4 touch. No epic resequencing or priority change.

### Story Impact

- **Story 2.2** (rename candidate: "Autonomous Exploration Captures Evidence") — add page-fingerprint dedup (same logical page reached via multiple paths processed once), navigation-first traversal priority, and representative-action sampling (one "Edit" executed per repeated action pattern, not every grid-row instance).
- **New Story 2.5** ("Application Model Builder — Normalize Evidence into a Structured Application Model") — merges duplicate pages, builds Component/Form/Action/API/Assertion entities with locator metadata, builds the navigation graph, attributes each entity back to its source Evidence.
- **Story 2.6** (AI Journey/Capability Inference, renumbered from 2.5) — rewired to consume the Application Model (Pages/Components/Navigation) built by Story 2.5, rather than raw Evidence directly. `identity_key` computation (AD-13) still applies, now over the structured model.
- **Story 4.1/4.2** — no AC rewrite; a one-line note that AI context now includes Component locator metadata.

Since none of Epic 2's review-stage code is merged/shipped, this is a **revise-before-acceptance**, not a production rollback — no rollback event, no reverted commits.

### Artifact Conflicts

**PRD:**
- §4.2 Runtime Discovery (FR-6): reword to describe crawling as producing input to the Application Model Builder, and make the crawl optimization rules explicit (page-fingerprint dedup, navigation-first, representative-action sampling).
- §4.2 (FR-7 stop condition): clarify "exhaustive traversal" operates at the level of distinct pages and distinct action *patterns* — a repeated identical action (e.g., 4 "Edit" buttons in a grid) is sampled once by design, not left uncovered. This is a wording clarification, not a scope cut; it also **partially narrows PRD §12 Risk item 7** (unbounded exploration) since repeated-action explosion is now bounded — infinite pagination/unbounded page growth remains an accepted risk.
- §4.3 (new FR, e.g. **FR-30**: Application Model Builder): "Platform normalizes captured discovery signal into a structured Application Model (Pages, Components, Forms, Actions, APIs, Assertions, Page Transitions), with automation metadata (preferred/fallback locators) per component, used by both AI inference and Playwright generation."
- §4.3 FR-8 note: AI inference now reads the structured Application Model rather than raw per-page Evidence — same business-language-Journey intent, better-grounded input.
- §5 Non-Goals: unchanged — this is an internal architecture deepening, not a curation/scope change.
- §12 Risk Register: item 7's mitigation text gains a note that representative-action sampling bounds repeated-action explosion (partial mitigation), full risk (unbounded page growth) remains accepted.

**Architecture (`ARCHITECTURE-SPINE.md`):**
- **AD-1** pipeline extended: `DiscoveryActivity` → **`ApplicationModelBuilderActivity` (new)** → `InferenceActivity` → `GenerationWorkflow`. Still bounded inside `DiscoveryWorkflow`; AD-2 (workflows orchestrate only) unaffected.
- **AD-8** (evidence pointer/granularity) rewritten: `Evidence` remains the raw capture layer (unchanged responsibility, tagged `discovery_run_id`). A new layer of normalized entities (Page, Component, Form, FormField, Action, ApiEndpoint, Assertion, PageTransition, ComponentLocator, ValidationRule) is built by the Model Builder from Evidence, each retaining a pointer back to the Evidence row(s) it was derived from — preserving the "live pointer back to evidence" invariant at finer granularity than today's flat model.
- **New AD-14** ("Application Model Builder owns normalization; one writer per entity type"): mirrors AD-7's single-deletion-path pattern — only `ApplicationModelBuilderActivity` may write Page/Component/Form/Action/API/Assertion/PageTransition rows; `DiscoveryActivity` only ever writes raw `Evidence`; `InferenceActivity` only ever writes Journey/Capability, now reading the Application Model instead of Evidence directly.
- **New AD-15** ("Crawl optimization heuristics are deliberate sampling, not incomplete coverage"): documents that page-fingerprint dedup and representative-action selection are intentional AD-level decisions, so FR-7's "exhaustive traversal" isn't misread as "every DOM instance individually exercised."
- **Module Map**: new row — **Application Model Builder** module (`apps/workers/discovery`, `ApplicationModelBuilderActivity`). Responsibility: normalize Evidence into the structured Application Model. Inputs: `Evidence` rows. Outputs: Page/Component/Form/Action/API/Assertion/PageTransition rows. Depends on: `packages/domain`. Isolation: a new normalization rule changes only this module, never Discovery's crawl code or Inference's AI logic.
- **Domain model**: new SQLModel entities + Alembic migrations required for Page, Component, Form, FormField, Action, ApiEndpoint, Assertion, PageTransition, ComponentLocator, ValidationRule.
- **`[RESOLVED 2026-07-18]`** The pitch's "Module" (Application → Modules → Pages) grouping is **not** a separate entity — Harsha confirmed reusing the existing `Capability` entity for this grouping. No `Module` entity is added to `packages/domain`.

**UX:** No new screens required — this is a backend/data-model concern. `DESIGN.md`/`EXPERIENCE.md` need no changes for this MVP slice. Optional future enhancement (not required): render structured Component/locator detail in FR-23's evidence panel instead of raw JSONB.

**Other artifacts:** New unit/integration tests for Model Builder normalization and dedup logic; new Alembic migrations; no CI/CD pipeline, deployment, or monitoring changes.

## 3. Recommended Approach

**Direct Adjustment**, scoped to Epic 2 (rework) + Epic 4 (light context-source note). No rollback event (nothing merged/shipped yet — this is revise-before-acceptance on in-review code), no MVP scope change, no new epic.

- Effort: **Medium-High** — new domain entities + migrations, crawler upgrade (dedup/navigation-priority/representative-action logic), new Model Builder activity, Inference rewiring.
- Risk: **Medium** — touches already-reviewed code (re-review required), but isolated to Epic 2/one new domain layer; Module Map isolation rule (AD-14) keeps the blast radius contained.
- Timeline impact: Epic 2 stories return from `review` to `in-progress`/rework; Epic 3/4 (not started) are unaffected in sequencing.

## 4. Detailed Change Proposals

### 4.A PRD (`prd.md`)

| Section | Change | Rationale |
|---|---|---|
| §4.2 FR-6 | Reword to describe crawl output feeding the Application Model Builder; make dedup/navigation-first/representative-action rules explicit. | Matches new crawl design. |
| §4.2 FR-7 | Add clarifying note: exhaustive traversal is at the level of distinct pages/action patterns, not every repeated DOM instance. | Prevents misreading representative-action sampling as incomplete coverage. |
| §4.3 (new) | Add **FR-30: Application Model Builder** — normalizes Evidence into structured Pages/Components/Forms/Actions/APIs/Assertions/Page Transitions with locator metadata. | Net-new capability this change introduces. |
| §4.3 FR-8 | Note inference now reads the Application Model, not raw Evidence. | Keeps FR-8 accurate to new data flow. |
| §12 Risk item 7 | Add note: representative-action sampling bounds repeated-action explosion; unbounded page growth remains an accepted risk. | Honest partial-mitigation update. |

### 4.B Architecture (`ARCHITECTURE-SPINE.md`)

| Section | Change |
|---|---|
| AD-1 | Extend pipeline to include `ApplicationModelBuilderActivity` between Discovery and Inference. |
| AD-8 | Rewrite to describe Evidence (raw) + new normalized entities (structured), both with evidence-pointer traceability. |
| New AD-14 | Single-writer rule for Application Model entities (Model Builder only). |
| New AD-15 | Crawl optimization heuristics are deliberate sampling, documented against FR-7 misreading. |
| Module Map | Add "Application Model Builder" row. |
| Structural Seed / domain | Add new entities to `packages/domain`; new migrations under `migrations/`. |
| Deferred | Add open question: Module vs. Capability relationship — flagged for Architect confirmation before Story 2.5 build. |

### 4.C Epics & Stories (`epics.md` + implementation-artifacts)

| Story | Change |
|---|---|
| 2.2 Autonomous Exploration Captures Evidence | Add ACs for page-fingerprint dedup, navigation-first traversal, representative-action sampling. Status reverts `review` → rework. |
| **2.5 (new) Application Model Builder** | New story: normalize Evidence into Page/Component/Form/Action/API/Assertion/PageTransition entities with locator metadata, attributed back to source Evidence. Status: `ready-for-dev`. |
| 2.6 AI Journey/Capability Inference `[renumbered from 2.5]` | Rewire input from raw Evidence to the Application Model (Story 2.5's output). Status reverts `review` → rework. |
| 4.1 Generate Scenarios | Add one-line note: AI context now includes Component Model detail, not raw Evidence. No AC rewrite. |
| 4.2 Generate Playwright Test Assets | Add one-line note: AI context now includes Component locator metadata. No AC rewrite. |

`sprint-status.yaml`: revert `2-2` from `review` to `in-progress`; add `2-5-application-model-builder: ready-for-dev`; renumber former `2-5-ai-journey-capability-inference-from-evidence` to `2-6-ai-journey-capability-inference-from-application-model` and revert to `in-progress`.

## 5. Implementation Handoff

**Scope classification: Moderate.** This reshapes an already-in-review epic's internal data model and adds one new story, but doesn't change MVP boundaries, remove any FR, or touch Epics 1/3/5–7 — routes to Product Owner / Developer. The Module-vs-Capability question is resolved (2026-07-18, this session) — no Architect confirmation remains outstanding.

- **Developer agent** — owns: reworking Stories 2.2/2.6 in place, authoring Story 2.5 (grouping via existing `Capability`, no new `Module` entity), updating `sprint-status.yaml`, new domain entities + migrations.
- **Product Owner** — owns: sign-off that FR-30 and the FR-6/FR-7 wording changes accurately reflect intended scope.

**Success criteria:** PRD FR-30 and updated FR-6/7 match the new crawl+model-builder design; Architecture AD-1/AD-8/AD-14/AD-15 and the Module Map are internally consistent; Stories 2.2/2.6 are reworked and Story 2.5 exists before Epic 2 returns to `review`; Epic 4's context-source note is recorded without unnecessary AC churn.

**`[CORRECTION — 2026-07-18, same day]`** File-level renumbering applied after this proposal was first drafted: `2-5-ai-journey-capability-inference-from-evidence.md` → `2-6-ai-journey-capability-inference-from-application-model.md`; the new Application Model Builder story file is `2-5-application-model-builder.md`. See §0.

## 6. Addendum — Evidence table removed (2026-07-18, same day, second correction)

After the renumbering correction above, Harsha pointed out that the generic `Evidence` table (`type` + JSONB `details`) this proposal's original §1–§4 assumed as the capture layer adds no value once typed tables (`Page`/`Component`/`Form`/`Action`/`ApiEndpoint`) exist — it duplicates what those tables already hold. Confirmed decisions (this follow-up session):

- **No `Evidence` table.** `DiscoveryActivity` (Story 2.2) writes directly into five typed, mergeable tables — `Page`, `Form` (+ `FormField`/`ValidationRule`), `Action`, `ApiEndpoint`, `PageTransition` — each scoped by both `application_id` (the tenant key) and `discovery_run_id` (provenance).
- **`application_id` is the scoping key**, not just `discovery_run_id` — this is what makes the Application Model genuinely *reusable*: a page re-visited on a later re-discovery run resolves to the same canonical row, not a fresh duplicate.
- **Raw + canonical, via a self-referencing `merged_into_id`** on `Page`/`Form`/`ApiEndpoint`: null means canonical, set means superseded/merged. `DiscoveryActivity` always writes `merged_into_id = null`; only `ApplicationModelBuilderActivity` (Story 2.5) ever sets it, matching duplicates within *and across* Discovery Runs for the same Application. `Action`/`PageTransition` don't need this — they're raw historical detail, not independently deduped.
- **`Component`/`ComponentLocator`/`Assertion` remain purely derived** — `DiscoveryActivity` never writes them; Story 2.5 synthesizes them from canonical `Action`/`PageTransition`/`ApiEndpoint` data.
- **`journey_id` (set by Story 2.6's `InferenceActivity`) lives only on canonical rows** of `Page`/`Form`/`ApiEndpoint`/`Component` — never on a superseded row, and never on `Action`/`PageTransition` (Component is the attributable, deduped unit; raw Actions are audit detail).

**Impact:** Story 2.2 is reworked a second time (typed capture, not `Evidence` — a deeper change than the first pass's AC additions); Story 2.5's job shifts from "transform Evidence into structure" to "merge duplicate typed captures into canonical rows + derive Component/ComponentLocator/Assertion"; Story 2.6's `InferenceActivity`/`HostedAIProvider` signature changes from `list[Evidence]` to `list[Page]` (canonical only). PRD FR-6/FR-30, Architecture AD-8/AD-13/AD-14 (and the Module Map, Module Contracts, sequence diagram, ERD), `epics.md`, and all three story files updated to match. No further MVP scope or reviewer-facing change — this is a second, deeper round of the same internal architecture deepening described in §1.
