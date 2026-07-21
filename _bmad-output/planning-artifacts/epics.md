---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - "_bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md"
  - "_bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md"
  - "_bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md"
updated: "2026-07-15 — see sprint-change-proposal-2026-07-15.md: Story 6.2 relocated into Story 3.1. Follow-up same day: FR-28 (Journey edit) cut; FR-10/FR-11 (Approve/Reject) cut and FR-14 rewritten — generation now starts immediately on discovery, with no approval gate. Final follow-up same day: Epic 5 (CI/CD Delivery), Epic 6's cut stories (6.1/6.3/6.4), and Epic 7 (Deployment) removed in full — none had any supporting screen in the current UX, and Epic 7's on-prem deployment is confirmed parked for a later release, not a current-scope item. Stories 3.2/3.3, 5.1-5.3, 6.1 files deleted; Story 3.5 trimmed to re-discovery dedup only.
  2026-07-18 — see sprint-change-proposal-2026-07-18.md: Application Model Builder introduced (new FR-30). Story 2.2 gains crawl-optimization ACs (page-fingerprint dedup, navigation-first, representative-action sampling); new Story 2.5 (Application Model Builder) added; AI Journey/Capability Inference renumbered 2.5 → 2.6 and rewired to read the new Application Model instead of raw Evidence. Stories 4.1/4.2 gain a one-line AI-context note, no AC rewrite. sprint-status.yaml: 2-2 reverted review → in-progress for rework; 2-5 renumbered/renamed to 2-6 and reverted to in-progress.
  2026-07-18 [correction] — initial numbering had Application Model Builder as Story 2.6, after the AI Inference story (2.5) that depends on it, backwards from the actual pipeline order (Discovery → Model Builder → Inference). Corrected: Application Model Builder is Story 2.5, AI Inference is Story 2.6.
  2026-07-18 [follow-up, same day] — the generic `Evidence` table concept is removed in full: Story 2.2 now writes typed rows directly (`Page`/`Form`/`FormField`/`ValidationRule`/`Action`/`ApiEndpoint`/`PageTransition`), each scoped by `application_id` (making the model genuinely reusable across re-discovery, not just per-run) plus `discovery_run_id` (provenance). Story 2.5 resolves duplicates via a self-referencing `merged_into_id` and derives `Component`/`ComponentLocator`/`Assertion`. PRD FR-6/FR-30, Architecture AD-8/AD-13/AD-14, and Stories 2.2/2.5/2.6 updated to match.
  2026-07-19 [crawl engine follow-up] — Story 2.2 gains ACs 7-9, all within FR-6's existing scope: button-triggered navigation is now followed onward instead of dead-ending at the click; forms with an identical shape/starting values (hidden fields included) are sampled representatively across pages; a broken/error (network failure or 4xx/5xx) destination is skipped rather than captured; and AC 6's representative-action sampling is bounded to a small number of distinct labels per page, page-body content before nav/header/footer chrome. PRD FR-6/FR-7/§12 item 7 and Architecture AD-15 updated to match."
---

# Application Intelligence Platform - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Application Intelligence Platform (AITestGen), decomposing the requirements from the PRD, UX Design contract, and Architecture Spine into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-1: User can onboard an Application by providing its URL, environment designation, and access credentials.
FR-2: Access credentials must correspond to a Dedicated Test Account provisioned by the customer, not a real end-user identity.
FR-3: Platform establishes a session prior to discovery either by (a) performing a standard/manual username-password login flow itself, or (b) reusing a pre-authenticated session (storage state) supplied by the customer for SSO/MFA-protected Applications; a Discovery Run whose session has expired fails gracefully and surfaces a re-authentication prompt.
*(FR-4 "Configurable discovery scope" and FR-5 "Discovery time budget" removed 2026-07-15 — confirmed removed concepts, not a missing-UI gap. Discovery Runs always cover the full Application with no time-budget cap; accepted-risk tradeoff, see PRD §12 Risk item 7.)*
FR-6: `[UPDATED 2026-07-15]` Platform autonomously navigates pages, exercises UI actions and forms, and invokes APIs across the entire Application (no configurable scope), capturing pages, navigation paths, actions, forms, API calls, and state transitions. `[UPDATED 2026-07-18]` Applies page-fingerprint dedup, navigation-first prioritization, and representative-action sampling (see FR-30).
FR-7: `[UPDATED 2026-07-15]` A Discovery Run terminates when no new pages/actions/state transitions are found (exhaustive traversal) — no time-budget stop condition exists. `[CLARIFIED 2026-07-18]` "Exhaustive" is at the level of distinct pages/action patterns, not every repeated DOM instance (FR-6's representative-action sampling).
FR-8: Platform uses AI to transform captured discovery signals into candidate Business Capabilities and Journeys expressed in business language; every candidate Journey is associated with the specific pages/actions/API calls that produced it. `[UPDATED 2026-07-18]` Reads canonical Application Model rows (FR-30) — never a superseded/duplicate one.
FR-30 `[ADDED 2026-07-18]`: Platform normalizes captured discovery signal into a structured Application Model — Pages, Components, Forms, Actions, APIs, Assertions, Page Transitions — with per-component locator metadata (preferred + fallback locators, target page). Both AI inference (FR-8) and Playwright generation (FR-17) consume this model. See `sprint-change-proposal-2026-07-18.md`.
FR-9: `[UPDATED 2026-07-15]` Discovered Journeys and Capabilities are presented to a human reviewer for curation (rename, delete) — presentation is not a gate; a Journey is already in the Trusted Knowledge Model and feeding Scenario Generation (FR-14) before a reviewer looks at it.
FR-10: `[CUT 2026-07-15]` Previously: reviewer can approve a discovered Journey/Capability, adding it to the Trusted Knowledge Model. Cut — there is no gate to approve past; every discovered Journey is in the Trusted Knowledge Model immediately (FR-14).
FR-11: `[CUT 2026-07-15]` Previously: reviewer can reject a discovered Journey/Capability, excluding it from the Trusted Knowledge Model. Cut as redundant with Delete (FR-13), now the sole exclusion mechanism.
FR-12: Reviewer can rename a discovered Journey/Capability.
FR-13: Reviewer can delete a discovered Journey/Capability — the sole way a Journey/Capability is excluded from the Trusted Knowledge Model as of 2026-07-15. Out-of-scope note: merging/splitting/editing remain unsupported (FR-28 cut same day it was added).
FR-14: `[REWRITTEN 2026-07-15]` Every discovered, non-deleted Journey/Capability automatically enters the Trusted Knowledge Model and feeds Scenario Generation and Analytics immediately upon discovery — no separate approval step; deletion (FR-13) is the only exclusion mechanism.
FR-15: Re-running discovery on a previously discovered Application flags only newly-discovered Journeys/Capabilities (existence check only, not change detection) for human review; already-known Journeys are not automatically re-surfaced.
FR-16: Platform generates integration test Scenarios for each discovered Journey, covering both happy-path and negative/edge-case scenarios. `[UPDATED 2026-07-15]` Generation starts immediately upon discovery, not gated on approval.
FR-17: Platform converts generated Scenarios into executable Playwright Test Assets.
FR-18: When a customer triggers regeneration of Test Assets for a Journey, platform regenerates Scenarios and Test Assets from scratch (full regeneration only, not incremental). Updated 2026-07-15: Scenarios are now editable/removable pre-generation (FR-29).
FR-28 `[ADDED then CUT 2026-07-15]`: Reviewer can edit a discovered Journey via a per-row action menu, in addition to rename/delete. Cut the same day it was added — its exact edit surface (name/description vs. constituent steps) was never confirmed in the UX review, and product decided not to build it.
FR-29 `[ADDED 2026-07-15]`: Reviewer can rename, edit, or remove a generated Scenario before Playwright generation. `[GAP]` whether edits feed generation or are display-only is unconfirmed.

**`[REMOVED 2026-07-15]`** FR-19–22 and FR-24–27 are removed in full — no supporting screen exists in the current reference prototype's IA for any of them, and (for FR-26/27) on-prem deployment is confirmed parked for a later release. See `sprint-change-proposal-2026-07-15.md` for the original history. FR-23 is the one exception: retained and relocated (see its entry).

FR-23: `[RETAINED, RELOCATED 2026-07-15]` Platform provides Journey-detail — a view of a Journey's screens, actions, and API calls captured during discovery. As of 2026-07-15, served inline in the discovery-review screen's detail panel (selecting a candidate), not a standalone Journey Explorer screen.

### NonFunctional Requirements

NFR-1 (Security): Standard enterprise-grade secret handling for stored discovery credentials — encryption at rest and in transit, least-privilege service accounts. No bespoke certification requirement specified for V1.
NFR-2 (Reliability): `[UPDATED 2026-07-15]` A Discovery Run must complete (exhaustive traversal) or fail gracefully (e.g., session expiry) — no time-budget timeout state exists.
NFR-3: `[REMOVED 2026-07-15]` Previously "Data locality (on-prem)," tied to FR-27 (removed — on-prem deployment parked for a later release).
NFR-4 (Accessibility): WCAG 2.1/2.2 AA is the accessibility floor across the entire desktop surface — behavioral commitments (focus visibility, keyboard operability, contrast), not a compliance badge.
NFR-5 (Platform scope): Desktop web app only — no mobile or tablet form factor / responsive parity in V1.

### Additional Requirements

- No starter/greenfield template is specified by Architecture; instead a structural seed (`apps/web`, `apps/api`, `apps/workers/discovery`, `apps/workers/generation`, `packages/domain`, `packages/workflows`, `packages/ai_provider`, `packages/delivery_adapters`, `packages/ci_instructions`, `packages/secrets_client`, `migrations/`) is fixed — Epic 1 Story 1 should scaffold this structure directly rather than starting from an external template.
- Paradigm: Durable Orchestrated Pipeline with Ports & Adapters — Temporal Workflows carry coordination only (no I/O); Temporal Activities are the only place side effects (browser automation, LLM calls, DB writes, Git operations) happen (AD-1, AD-2).
- `DiscoveryWorkflow` is bounded and terminates by writing candidate Journeys/Capabilities to Postgres with `status=candidate`; human review is ordinary CRUD via `apps/api`, never a Temporal Signal/Update on a long-lived workflow (AD-1).
- `[UPDATED 2026-07-15]` `InferenceActivity` starting an independent `GenerationWorkflow` per candidate Journey it creates, with workflow ID `generation-{journey_id}-1` — immediately upon discovery, with no human approval gate (AD-1, AD-9).
- All AI/LLM calls must go through one `AIProvider` port (`packages/ai_provider`); no Activity may import a vendor AI SDK directly (AD-3).
- `[NOT CURRENTLY ACTIVE — 2026-07-15]` The `DeliveryAdapter`/`packages/ci_instructions` port design (AD-4) is retained in the Structural Seed as a forward-compatible architectural seam, but CI/CD Delivery (Epic 5) is removed — no story builds against this port in the current scope.
- Discovery credentials and SSO/MFA session state must never touch primary storage in plaintext — read/written only via `packages/secrets_client`, backed by Vault or cloud KMS envelope encryption; `packages/domain` models store only a secret reference (AD-5).
- The API's generated OpenAPI spec is the only contract between `apps/web` and `apps/api` — frontend TypeScript types are generated from the FastAPI/Pydantic OpenAPI spec; no hand-written duplicate request/response shape is permitted (AD-6).
- `[UPDATED 2026-07-15]` The Trusted Knowledge Model has exactly one deletion path: only `apps/api`'s delete endpoint may transition a Journey/Capability's status to `deleted`; workers may only write `candidate` or downstream generation status (AD-7). There is no more `approved`/`rejected` state — every non-deleted Journey/Capability is part of the Trusted Knowledge Model from the moment it's discovered.
- `[UPDATED 2026-07-18]` There is no generic `Evidence` table. `DiscoveryActivity` writes typed rows directly (`Page`, `Form`/`FormField`/`ValidationRule`, `Action`, `ApiEndpoint`, `PageTransition`), each tagged `application_id` + `discovery_run_id`; `ApplicationModelBuilderActivity` merges duplicates (within and across Discovery Runs) via a self-referencing `merged_into_id`, and derives `Component`/`ComponentLocator`/`Assertion` from canonical rows; `InferenceActivity` attributes `journey_id` only onto canonical rows. `Journey.discovery_run_id` is immutable; `Scenario`/`TestAsset` rows carry `generation_run_id` plus a `current: bool` flag, with prior attempts soft-superseded (never deleted) on regeneration (AD-8).
- Large binary artifacts (screenshots) are never stored inline in Postgres — `Page.object_storage_key` holds an object-storage key/reference; structured metadata lives directly as typed columns in Postgres (AD-8).
- Every side-effecting Activity (form submission, PR/commit creation) must be idempotent under Temporal's at-least-once retry, using a deterministic check-before-acting key derived from its inputs. `[UPDATED 2026-07-15]` `InferenceActivity`'s candidate-creation step is keyed by the same `identity_key` used for re-discovery dedup (AD-13); its `GenerationWorkflow`-start is naturally idempotent via Temporal's duplicate-workflow-ID rejection, with no separate reconciliation sweep needed (AD-9).
- `[UPDATED 2026-07-15]` `DiscoveryRun.status` must be a first-class, queryable field (`running | complete | failed`) — completeness is never inferred from presence/absence of other data (AD-10). No `incomplete` value exists — there is no time-budget stop condition to produce one (FR-7).
- Session expiry mid-crawl must be detected as a distinct condition from a normal stop condition, terminating the run with `status=failed`, `failure_reason=session_expired`, surfaced by `apps/api` as a re-authentication prompt distinguishable from other `failed` causes (AD-11).
- `Organization` is a first-class tenant-boundary entity; every `apps/api` query must be scoped by the authenticated user's Organization through one central mechanism, never left to individual endpoints (AD-12).
- Each candidate Journey needs a deterministic `identity_key` computed from its underlying evidence shape (not its AI-generated display name); re-discovery dedup/suppression for FR-15 compares against this key and never alters existing attribution (AD-13).
- Stack versions to build against: Python 3.14.6, FastAPI (current stable), SQLModel (current stable), Alembic (current stable), PostgreSQL 18.4, Temporal Python SDK (current GA), Playwright Python 1.57+, React 19.x, Vite 8.1.x, TypeScript 7.0 GA (verify AD-6's OpenAPI→TS codegen tooling supports it before adopting, else pin TypeScript 5.9 as fallback).
- Platform's own CI (build/test/lint of this codebase) runs on GitHub Actions; every `apps/*` service ships as its own container image; traces/metrics use OpenTelemetry, correlated by Temporal `workflow_id` (matching structured-log correlation).
- Deferred by explicit architecture decision (not to be designed against in V1 stories): SaaS vs. on-prem deployment topology and where Temporal itself runs; the object-storage backend provider; direct-commit regeneration conflict handling; a non-production technical safeguard; confidence/risk-scoring reintroduction; reviewer prioritization/importance-marking; tenant billing/plan model.
- Blocking dependency: the SSO/MFA session-state capture mechanism (PRD Open Question 8) is unresolved and blocks detailed design/build of the Onboarding flow's auth step (FR-3) — stories touching this step must treat the mechanism as a placeholder pending that decision.
- `[CUT 2026-07-15]` The live pending-review count indicator and New/Dupe candidate-row badges are confirmed cut — the nav rail they depended on is retired, and neither was confirmed present in the current reference prototype. See Story 3.1.

### UX Design Requirements

UX-DR1: Implement the full design-token system (color, typography, spacing, radius) as CSS custom properties with true light/dark parity — `:root` sets light values + `color-scheme: light`, a `@media (prefers-color-scheme: dark)` block overrides for OS dark preference, and explicit `:root[data-theme="dark"]`/`[data-theme="light"]` attribute selectors let an in-app toggle override the OS preference. No component may hardcode a color outside the token layer.
UX-DR2: `[SUPERSEDED 2026-07-15 — see Story 1.2]` Originally: build a persistent app shell — fixed-width (236px) nav rail plus fluid main column — with links grouped under five section labels, and Settings/sign-out pinned to the rail foot. No nav rail exists in the current IA; replaced by a top bar (brand mark, avatar menu) plus a pipeline stepper (Story 2.1). Settings itself is removed (Epic 7 cut).
UX-DR3: `[CUT 2026-07-15]` Live pending-review count badge — was tied to the now-retired nav rail; no on-screen replacement is being built. See `sprint-change-proposal-2026-07-15.md` and Story 3.1.
UX-DR4: Build the two-pane Review Journeys pattern — a scannable queue-row list plus a sticky (340px, sticky on scroll) evidence panel that loads the selected row's full evidence trail (pages/actions/API calls) rendered in monospace.
UX-DR5: `[UPDATED 2026-07-15]` Build the Discover Journeys row component with two curation actions — Rename, Delete. `[CUT 2026-07-15]` Approve/Reject are cut (no gate — see epics.md Epic 3); there is no "decided row" state to mute/dim, since nothing requires a per-row decision anymore.
UX-DR6: Build the badge component with variants `approved`, `rejected`, `type-happy`, `type-negative`, `generated` — every variant is a tinted-wash background plus saturated text of the same hue, never a solid fill. `[CUT 2026-07-15]` `new`/`dupe` variants are not built — see Story 3.1.
UX-DR7: `[TRIMMED 2026-07-15]` Build the status-pill component with a pulsing dot for in-progress states. (Originally also specified an amber "Incomplete" transition on time-budget cutoff — removed, no time-budget concept exists; FR-7's only outcome is "Running" → "Complete." Also previously dropped an "Applications table row" variant — no Application-list view is confirmed in the current IA.)
UX-DR8: `[REMOVED 2026-07-15]` Capability card component (App Overview) — the App Overview screen is cut (Epic 6 removed), no replacement.
UX-DR9: `[REMOVED 2026-07-15]` KPI tile and hero-stat strip components (Dashboard, Applications) — both screens are cut (Epic 6/Applications-list removed), no replacement.
UX-DR10: Build the Add Application stepper — only the active step renders its full form body; completed steps collapse to a one-line summary, pending steps show only their title; a completed step is not clickable to jump back to. `[GAP — flagged 2026-07-15, see Story 1.3]` This stepper pattern was itself superseded by a single consolidated Connect App form; re-verify whether any of this UX-DR still applies to a real screen.
UX-DR11: `[REMOVED 2026-07-15]` Originally: option-card/provider-card selection control for Add Application's auth-method choice, and Connect to CI/CD's export-mode/provider choices. Both are gone — auth-method is now a plain `<select>` (Story 1.4's 2026-07-15 update), and Connect to CI/CD is cut (Epic 5 removed).
UX-DR12: `[TRIMMED 2026-07-15]` Build the code-viewer + native `<details>`/`<summary>` disclosure component for generated Playwright code, with light syntax tinting (keywords/strings/comments) — closed by default for every block except the first/most-relevant one per screen; opening one disclosure never closes others. (Originally also covered CI/CD pipeline snippets — removed, Epic 5 cut.)
UX-DR13: `[TRIMMED 2026-07-15]` Build the toggle-switch component for genuine binary settings only (e.g., notification preferences) — immediate on/off, no confirmation step, never repurposed as a selection control. (Originally cited AI-provider mode as an example use — removed, Epic 7 cut; no Settings screen exists for this control to live on regardless.)
UX-DR14: `[SUPERSEDED 2026-07-15 — see Story 3.5]` Originally: build an empty-state component (dashed-border panel, circular check icon, one-line factual confirmation) shown only when a queue/list is fully triaged, with an Approved/Rejected count summary on Review Journeys specifically. No longer applicable to Discover Journeys — there is no forced per-row decision to "fully triage" (Approve/Reject cut), so no empty-state trigger condition exists there. Retained as a general-purpose component definition in case another screen needs a true empty state later.
UX-DR15: `[SUPERSEDED 2026-07-15]` Originally: an 11-screen IA — Login; Applications, Add Application, Discovery Progress, App Overview, Review Journeys, Generated Scenarios, Generated Tests, Connect to CI/CD, Dashboard, Settings — linear flow through all of them. Replaced by the current 6-screen IA: Sign In → Home (3 action cards) → Connect App → Discover Journeys → Review Scenarios → Generate Suite (a single-Application 4-step guided pipeline, per Story 1.2/2.1's 2026-07-15 updates). Applications, App Overview, Generated Tests (as a standalone screen), Connect to CI/CD, Dashboard, and Settings have no current-IA equivalent.
UX-DR16: `[UPDATED 2026-07-15]` Implement the breadcrumb/app-name context rule — show the current Application's name (plus environment badge) in the top bar on all four pipeline-step screens (Connect App, Discover Journeys, Review Scenarios, Generate Suite), since each is inherently scoped to a single Application; suppress it on Sign In and Home, the only pre-/cross-Application screens. (Originally listed Discovery Progress, App Overview, Generated Tests, Connect to CI/CD, Settings, Applications, and Dashboard — most of those screens no longer exist; see UX-DR15.)
UX-DR17: `[TRIMMED 2026-07-15]` Implement state-pattern behavior for: Discovery running (live-feed list, newest first) vs. complete; review-queue in-progress vs. resolved-row (muted, badge-only) vs. cleared (empty state) `[largely superseded, see UX-DR14/Story 3.5]`. (Originally also covered time-budget-incomplete — removed, no time-budget concept exists, see Story 2.3 — and CI/CD provider "Connected" label and Dashboard coverage-gap flag — both removed, Epic 5/6 cut.)
UX-DR18: `[UPDATED 2026-07-15]` Enforce the accessibility floor across every new screen/component — WCAG 2.1/2.2 AA; visible focus ring on every interactive element (buttons, top-bar/pipeline-stepper links, inputs, selects, textareas, `<summary>` triggers); tab order matches visual order (list before detail panel on Discover Journeys). (Originally also cited nav-rail links and option/provider cards — both removed; see UX-DR2, UX-DR11.)
UX-DR19: Enforce the label/caption contrast rule everywhere new text is added — all real label/caption/metadata text routes through the `ink-muted` token (~5:1 AA contrast); the `ink-faint` token is reserved exclusively for decorative, non-text marks (disabled affordances, placeholder dashes) and must never carry real copy.
UX-DR20: Enforce voice-and-tone constraints in all authored UI copy — no exclamation points, emoji, or celebratory language anywhere; capitalize Application, Capability, Journey, Scenario, Test Asset, and Trusted Knowledge Model as proper nouns consistently; state errors/hints/constraints as fact + why, never apology-only or unexplained.
UX-DR21: Enforce the hard product constraint that no AI confidence, risk, or importance signal (score, percentage, star rating, priority flag) may appear anywhere near discovered/inferred content (Journeys, Capabilities, Scenarios) — this applies to every new screen, not just the ones in the approved prototype.
UX-DR22: Enforce the "no merge/split/composition-edit" constraint — no future Journey-review screen or component may offer a merge, split, or inline edit of what pages/actions/API calls compose a Journey; a reviewer resolves a duplicate candidate by deleting it, never by merging or editing it (no `dupe` badge is built — see Story 3.1; edit is cut — see Story 3.4).
UX-DR23: `[SUPERSEDED — see Story 4.1's 2026-07-15 update]` Originally: Generated Scenarios remain view-only, no checkbox selection, per-scenario approval, or action buttons on a scenario row, since the only approval gate was at the Journey level. No longer holds: per-scenario rename/edit/remove is supported (FR-29), and there is no more Journey-level approval gate at all (FR-10/FR-11 cut) — generation starts immediately on discovery.
UX-DR24: Reserve monospace typography (`font-mono`) exclusively for raw captured evidence and generated code (routes, API call signatures, timestamps, file paths, Playwright code) — never for authored UI copy (labels, headings, hints, empty-state text), even where a technical look might seem appropriate.

### FR Coverage Map

FR-1: Epic 1 - Application onboarding (URL, environment, credentials)
FR-2: Epic 1 - Dedicated Test Account credential requirement
FR-3: Epic 1 - Authentication via login flow or storage-state reuse
*(FR-4 and FR-5 — removed 2026-07-15, confirmed removed concepts, not deferred. See Story 1.5's removal below.)*
FR-6: Epic 2 - Autonomous exploration capturing pages/actions/APIs/state, always full-Application, with crawl-optimization rules (2026-07-18)
FR-7: Epic 2 - Discovery stop condition (exhaustive traversal only, no time-budget branch)
FR-8: Epic 2 - AI journey/capability inference with evidence association, now via the Application Model (FR-30)
FR-30: Epic 2 - Application Model Builder `[ADDED 2026-07-18]` — Story 2.5
FR-9: Epic 3 - Discover Journeys curation presentation
FR-10: `[CUT 2026-07-15]` Approve action — no longer built
FR-11: `[CUT 2026-07-15]` Reject action — no longer built
FR-12: Epic 3 - Rename action
FR-13: Epic 3 - Delete action (sole exclusion mechanism as of 2026-07-15)
FR-14: Epic 2 - Discovery gates downstream use (Trusted Knowledge Model) — `GenerationWorkflow` starts immediately per candidate (moved from Epic 3's former Approve action)
FR-15: Epic 3 - New-journey flagging on re-discovery
FR-16: Epic 4 - Scenario generation (happy-path + negative), starts immediately on discovery
FR-17: Epic 4 - Playwright Test Asset generation
FR-18: Epic 4 - Full regeneration on request
FR-28: `[ADDED then CUT 2026-07-15]` Edit a discovered Journey — no longer built
FR-29: Epic 4 - Edit/remove a generated Scenario `[ADDED 2026-07-15]`
FR-23: Epic 3 `[RETAINED, RELOCATED]` - Journey step/evidence detail, now inline in the discovery-review screen (was Epic 6 - Journey Explorer)

*(FR-19–22 and FR-24–27 — removed 2026-07-15 along with Epics 5, 6 [partially], and 7. See `sprint-change-proposal-2026-07-15.md` for history.)*

NFR-1 (Security): Epic 1 - Secret handling for stored discovery credentials
NFR-2 (Reliability): Epic 2 - Graceful completion (exhaustive traversal) or failure (e.g., session expiry)
NFR-4 (Accessibility): Cross-cutting - WCAG 2.1/2.2 AA applied within every epic's UI stories
NFR-5 (Platform scope): Cross-cutting - Desktop-only constraint applied within every epic's UI stories

## Epic List

### Epic 1: Foundation, Auth & Application Onboarding
A user can sign in, and onboard an Application (URL, environment, Dedicated Test Account credentials) — ready for its first Discovery Run. Establishes the structural seed scaffold, Organization tenancy, credential handling via SecretsClient, and the app shell/design-token foundation everything else builds on. `[UPDATED 2026-07-15]` No discovery scope or time-budget configuration — both removed (FR-4/FR-5); Discovery Runs always cover the full Application.
**FRs covered:** FR-1, FR-2, FR-3

### Epic 2: Runtime Discovery & AI Journey Inference
A user can start a Discovery Run, watch live progress (running/complete/failed-session-expired), and see AI-inferred candidate Journeys/Capabilities, each traceable to captured evidence. `[UPDATED 2026-07-15]` Every candidate Journey immediately enters the Trusted Knowledge Model and starts Scenario/Playwright generation as soon as it's created — no approval gate (FR-14, moved from the former Approve action). No `incomplete` status — a Discovery Run only ever completes (exhaustive traversal) or fails, since no time-budget cap exists. `[UPDATED 2026-07-18]` Raw discovery signal is normalized into a structured Application Model (Story 2.5, FR-30) before AI inference (Story 2.6) reads it — see `sprint-change-proposal-2026-07-18.md`.
**FRs covered:** FR-6, FR-7, FR-8, FR-14, FR-30

### Epic 3: Human Curation & Trusted Knowledge Model `[RENAMED 2026-07-15, was "Human Review & Trusted Knowledge Model"]`
`[REWRITTEN 2026-07-15]` A reviewer curates discovered candidates — rename what's mislabeled, delete what doesn't belong — and inspects any candidate's discovered step/evidence detail inline. There is no approve/reject gate: every discovered Journey is already in the Trusted Knowledge Model and generating coverage before a reviewer looks at it (see Epic 2); deletion is the only exclusion mechanism. Re-running discovery only flags genuinely new Journeys.
**FRs covered:** FR-9, FR-12, FR-13, FR-15, FR-23 (relocated 2026-07-15). `[CUT 2026-07-15]` FR-10 (Approve), FR-11 (Reject) — no story files retained (removed 2026-07-15); FR-28 (Edit) — see Story 3.4.

### Epic 4: Scenario & Playwright Test Generation
`[UPDATED 2026-07-15]` Every discovered Journey automatically produces happy-path/negative Scenarios (rename/edit/removable pre-generation as of 2026-07-15) and executable Playwright Test Assets, generated as a named Test Suite, regenerable from scratch on request — generation starts immediately on discovery, not on approval.
**FRs covered:** FR-16, FR-17, FR-18, FR-29 (added 2026-07-15)

*(Epic 5 "CI/CD Delivery," Epic 6 "Analytics & Executive Dashboards," and Epic 7 "Deployment & AI Provider Configuration" removed in full 2026-07-15 — none had any supporting screen in the current UX, and Epic 7's on-prem deployment is a confirmed parked-for-later-release decision, not current scope. Epic 6's Journey Explorer (FR-23) survives, relocated into Epic 3's Story 3.1. See `sprint-change-proposal-2026-07-15.md` for the original history.)*

## Epic 1: Foundation, Auth & Application Onboarding

A user can sign in, and onboard an Application (URL, environment, Dedicated Test Account credentials) — ready for its first Discovery Run.

### Story 1.1: Repository & Service Scaffold

As a developer,
I want the repository scaffolded to the architecture's fixed module boundaries with the core stack wired end-to-end,
So that every subsequent feature has a consistent, contract-safe structure to build within.

**Acceptance Criteria:**

**Given** an empty repository
**When** the scaffold is applied
**Then** the directory structure matches the Architecture Spine's Structural Seed exactly: `apps/web`, `apps/api`, `apps/workers/discovery`, `apps/workers/generation`, `packages/domain`, `packages/workflows`, `packages/ai_provider`, `packages/delivery_adapters`, `packages/ci_instructions`, `packages/secrets_client`, `migrations/`
**And** `apps/api` runs on FastAPI with SQLModel entities backed by PostgreSQL 18.4 and Alembic migrations, and exposes a generated OpenAPI spec
**And** `apps/web` runs on React 19 + Vite + TypeScript, with its API types generated from `apps/api`'s OpenAPI spec (AD-6) — no hand-written duplicate request/response type exists
**And** a Temporal (Python SDK) connection is wired from `apps/api` and at least one worker process, sufficient to start and complete a trivial no-op workflow
**And** the platform's own CI (build/lint/test) runs on GitHub Actions on every push

### Story 1.2: Sign In & Organization-Scoped Workspace

*Updated 2026-07-15 — IA changed from persistent nav-rail shell to top-bar + Home landing; see `sprint-change-proposal-2026-07-15.md`.*

As a user,
I want to sign in and land in a workspace scoped to my Organization,
So that my Applications and data are isolated from any other customer's.

**Acceptance Criteria:**

**Given** a registered user belonging to an Organization
**When** they sign in
**Then** they land on Home, showing three action cards (Start a New Project, Managed Applications, Watch a Product Demo) beneath a top bar (brand mark + product name, left; user-initials avatar, right)
**And** the design-token system is applied with full light/dark parity (`:root` light defaults, `@media (prefers-color-scheme: dark)` override, explicit `data-theme` override) — no component hardcodes a color
**And** clicking the avatar opens a menu showing the user's name, email, and a Log out action
**And** every API query the user's session triggers is scoped to their Organization via one central scoping mechanism (AD-12) — a second Organization's data is never returned
**And** the Home screen omits the top-bar Application-name breadcrumb (UX-DR16) — it is inherently pre-Application
**And** every interactive element (buttons, links, avatar menu) has a visible focus ring and is keyboard-operable
**And** the token system's `ink-muted` value is the only token used for real label/caption/metadata text anywhere in the shell, with `ink-faint` reserved exclusively for decorative marks — this rule, plus the no-exclamation-points/no-celebratory-language voice-and-tone rule, is treated as a standing constraint every later story's UI copy must follow, not a one-time fix

*(Superseded 2026-07-15 — retained for history only: the prior AC described a persistent 236px nav rail with links grouped under Workspace/Onboard/Understand/Automate/Prove, Settings and sign-out pinned to the rail foot. No nav rail exists in the current IA; top-level navigation is the pipeline stepper introduced in Story 2.1.)*

### Story 1.3: Onboard an Application — Basic Details

*Updated 2026-07-15 — the 3-step wizard is replaced by a single-page Connect App form; see `sprint-change-proposal-2026-07-15.md`.*

As a QA Director or Engineering Leader,
I want to register a new Application by providing its URL, environment designation, and Dedicated Test Account credentials,
So that it becomes available for discovery configuration.

**Acceptance Criteria:**

**Given** a signed-in user on Home
**When** they choose "Start a New Project" (or "Managed Applications") and submit Application name, Base URL, environment, credentials, and authentication method (Story 1.4) on the single Connect App form
**Then** an `Application` record is created, scoped to their Organization, and the submitted credentials are written only through `packages/secrets_client` (Vault/KMS-backed), never stored in plaintext in Postgres or logs (FR-2, AD-5, NFR-1)
**And** the credentials field is explicitly labeled as requiring a Dedicated Test Account, not a real end-user identity (FR-2)
**And** the Connect App screen shows the current Application's name and environment badge in the top bar once submitted, per the (2026-07-15) breadcrumb rule
**And** `[ABSORBED FROM REMOVED STORY 1.5, 2026-07-15]` submitting returns the user to the pipeline's Discover Journeys step, where discovery begins immediately against the full Application — no scope/time-budget configuration exists (FR-4/FR-5 removed)

*(Superseded 2026-07-15: the prior AC described a multi-step wizard stepper where only the active step's form renders. Connect App is now one consolidated form with a single "Connect Application" submit — no internal stepper.)*

### Story 1.4: Configure Application Authentication Method

*Updated 2026-07-15 — "Authentication method" is now a plain `<select>` field on the single Connect App form, not a wizard step with option cards.*

As a user onboarding an Application,
I want to choose how the platform authenticates to it — standard login or a reusable pre-authenticated session,
So that SSO/MFA-protected apps can still be discovered.

**Acceptance Criteria:**

**Given** a user filling out the Connect App form
**When** they select "Username & Password" from the Authentication method dropdown
**Then** username/password fields are captured and stored via SecretsClient for later use establishing a session before discovery
**Given** the user instead needs SSO/MFA session-reuse
**When** they provide the reusable session state through the (explicitly provisional, per PRD Open Question 8) placeholder mechanism
**Then** that session state is stored via SecretsClient as a secret reference, never in plaintext
**And** the UI does not claim the platform performs a SAML/OAuth/OIDC handshake or MFA-code retrieval itself

**`[GAP — flagged 2026-07-15]`** The current reference prototype's Connect App form shows only a generic Authentication method `<select>` with no visible SSO/MFA session-handoff option or field. PRD Open Question 8 remains unresolved — do not read this absence as "SSO/MFA support was cut." Needs explicit confirmation (from a fuller prototype export or direct product decision) before this story is built, specifically for the SSO/MFA branch of the AC above.

*(Story 1.5 "Configure Discovery Scope & Time Budget" removed in full 2026-07-15 — FR-4/FR-5 confirmed removed concepts, not a UI gap; see PRD §9. Its remaining substance — submitting the Connect App form navigates to Discover Journeys and starts discovery on the full Application — is absorbed into Story 1.3's AC, the story that already owns form submission.)*

## Epic 2: Runtime Discovery & AI Journey Inference

A Discovery Run starts automatically on Application creation; the user watches live progress and sees AI-inferred candidate Journeys/Capabilities, each traceable to captured evidence.

### Story 2.1: Start a Discovery Run `[UPDATED 2026-07-15]`

*Trigger changed 2026-07-15 — Discovery now starts automatically when the Connect App form is submitted (Story 1.3), not via a separate manual "Start Discovery Run" action. There is no confirmed Applications/Discovery Progress screen with its own start button (see Story 1.5's removal and Story 1.3's absorbed AC).*

As a user,
I want a Discovery Run to start as soon as I've onboarded an Application,
So that the platform begins mapping its business journeys without an extra step.

**Acceptance Criteria:**

**Given** an Application was just created (Story 1.3's Connect App submission)
**When** the creation request completes
**Then** a `DiscoveryRun` record is created with `status=running`, and a bounded `DiscoveryWorkflow` is started for it (AD-1) — the workflow contains no direct I/O, only calls to Activities (AD-2)
**And** the Discovery Progress screen shows a status pill reading "Running" with a pulsing dot

### Story 2.2: Autonomous Exploration Captures the Application Model `[RENAMED 2026-07-18, was "...Captures Evidence"]`

*Updated 2026-07-15 — no configurable scope; Discovery always explores the entire Application (FR-4 removed). Rewritten 2026-07-18 — reworked (reverted from `review` to `in-progress`): writes typed rows (`Page`/`Form`/`FormField`/`ValidationRule`/`Action`/`ApiEndpoint`/`PageTransition`) directly, not a generic `Evidence` record — the flat capture concept is removed in full, not merely renamed. Adds crawl-optimization ACs. See `sprint-change-proposal-2026-07-18.md`; Story 2.5 merges/derives from what this story captures. Extended 2026-07-19 — three further crawl-engine refinements (ACs 7-9): button-triggered navigation is now followed onward instead of dead-ending, forms with an identical shape/starting values are sampled representatively across pages, and broken/error destinations are skipped rather than captured.*

As a user,
I want the platform to autonomously explore my Application,
So that a structured record of it is captured as the basis for journey mapping.

**Acceptance Criteria:**

1. **`[REWRITTEN 2026-07-18]` Given** a running Discovery Run, **when** `DiscoveryActivity` navigates pages, exercises UI actions and forms, and invokes APIs across the entire Application, **then** each observation is written directly as a typed row — a page visit as `Page`, a form as `Form` (+ `FormField`/`ValidationRule`), a UI action as `Action`, an API call as `ApiEndpoint`, a navigation as `PageTransition` — every row tagged with both `application_id` and `discovery_run_id`, and (where the column exists) `merged_into_id = null` (FR-6, FR-30, AD-8, AD-14). There is no intermediate generic capture record.
2. Large binary artifacts (screenshots) are referenced via `Page.object_storage_key` (an object-storage key), never stored inline in Postgres.
3. The Discovery Progress screen's live-feed list shows the most recently captured pages/actions/API calls, newest first, in monospace, appended as discovery proceeds.
4. **`[ADDED 2026-07-18]`** **Given** the same logical page is reachable via more than one navigation path, **when** the crawler computes a page fingerprint, **then** that page is explored and captured once, not once per path (page-fingerprint deduplication) — a crawl-time optimization, distinct from Story 2.5's cross-run `merged_into_id` resolution (FR-6, AD-15).
5. **`[ADDED 2026-07-18]`** **Given** a page exposes both unexplored navigation links and already-explored interaction targets, **when** the crawler chooses what to do next, **then** it prioritizes unexplored navigation paths before repeating interactions on an already-visited page (navigation-first) (FR-6, AD-15).
6. **`[ADDED 2026-07-18]`** **Given** a page contains a repeated identical action pattern (e.g., an "Edit" button repeated once per grid row), **when** the crawler encounters it, **then** it exercises one representative instance of that action pattern, not every individual instance (representative-action sampling) — consistent with FR-7/AD-15's clarification that "exhaustive" applies at the level of distinct pages/action patterns (FR-7, AD-15). **`[UPDATED 2026-07-19]`** Bounded to a small number of distinct action labels per page, page-body content before nav/header/footer chrome.
7. **`[ADDED 2026-07-19]`** **Given** a page is reachable only via a non-link action, **when** that action navigates to a same-origin destination, **then** the destination is enqueued for further crawling and the navigation recorded as a `PageTransition` — previously such destinations were captured but never explored further (FR-6, AD-15).
8. **`[ADDED 2026-07-19]`** **Given** a `Form` with an identical shape and starting field values (hidden fields included) is reachable identically from more than one page, **when** the crawler encounters it again, **then** it is captured once (representative-form sampling, mirrors AC 6) (FR-6, AD-15).
9. **`[ADDED 2026-07-19]`** **Given** a destination fails to load or responds 4xx/5xx, **when** the crawler reaches it, **then** it is marked visited and skipped — no `Page` row, no further exploration (FR-6, FR-7, AD-15).

### Story 2.3: Discovery Completion `[RENAMED 2026-07-15, was "Discovery Stop Conditions & Completeness Status"]`

*Rewritten 2026-07-15 — FR-5 (time budget) removed; there is no time-budget stop condition, no `incomplete` status, and no accompanying amber status-pill state. A Discovery Run only ever completes via exhaustive traversal or fails (Story 2.4). This is an accepted-risk tradeoff — see PRD §12 Risk item 7 (no safety cap against unbounded exploration).*

As a user,
I want a Discovery Run to stop once exploration is exhaustive,
So that I know the map reflects everything discovery found.

**Acceptance Criteria:**

**Given** a running Discovery Run
**When** no new pages, actions, or state transitions are found
**Then** `DiscoveryRun.status` is set to `complete` (FR-7, AD-10)
**And** completeness is read directly from `DiscoveryRun.status` everywhere it's shown, never inferred from the presence or absence of other data

### Story 2.4: Session Expiry Handling

As a user,
I want to be told plainly when a Discovery Run fails because my session expired,
So that I can re-authenticate rather than mistake it for a normal, if small, result.

**Acceptance Criteria:**

**Given** a running Discovery Run whose session has expired mid-crawl (detected via an auth-redirect)
**When** `DiscoveryActivity` detects this condition
**Then** it terminates the run with `DiscoveryRun.status=failed`, `failure_reason=session_expired` — a condition distinct from a normal stop condition (AD-11)
**And** the platform surfaces a re-authentication prompt keyed specifically off `session_expired`, visually distinguishable from any other `failed` cause (FR-3). `[UPDATED 2026-07-15]` No longer needs to be distinguished from `incomplete` — that status no longer exists (FR-5 removed).

### Story 2.5: Application Model Builder `[ADDED 2026-07-18]` `[RENUMBERED 2026-07-18, was Story 2.6]`

*Renumbered ahead of AI Journey/Capability Inference (now Story 2.6) — this story must run first in the actual pipeline (Discovery → Model Builder → Inference), and the original 2.5/2.6 assignment had that backwards. See `sprint-change-proposal-2026-07-18.md`.*

As a user,
I want the platform to merge duplicate captures into one reusable, canonical Application Model,
So that journey inference and test generation work from reliable, deduplicated structure — and re-discovering an Application I've already mapped doesn't produce a pile of duplicates.

**Acceptance Criteria:**

1. **`[REWRITTEN 2026-07-18]` Given** typed rows captured by Story 2.2 (`Page`/`Form`/`Action`/`ApiEndpoint`/`PageTransition`, `merged_into_id = null`), **when** `ApplicationModelBuilderActivity` runs after `DiscoveryActivity` completes and before `InferenceActivity` starts (AD-1, AD-14), **then** rows representing the same logical page/form/API — whether captured in this run or an earlier Discovery Run against the same Application — are resolved to one canonical row per Application: every duplicate's `merged_into_id` is set to point at the canonical row, and the canonical row itself keeps `merged_into_id = null`.
2. `Component` and `ComponentLocator` rows are derived (never raw-captured) for **every automatable element, not only clickable ones** — grouping canonical `Action` rows on the same canonical `Page` by label/selector shape for buttons/links, *and* one `Component` per canonical `FormField` for form inputs — each `Component` carrying a preferred locator plus one or more alternative/fallback locators, and its target page where applicable. `FormField` gets a nullable `component_id` back-reference to its derived `Component`.
3. `Assertion` rows are derived from canonical `PageTransition`/`ApiEndpoint` outcomes attached to a canonical `Page`, with an optional `component_id` when the assertion targets a specific element rather than a page/API-level outcome.
4. Only `ApplicationModelBuilderActivity` ever sets an existing row's `merged_into_id`, and only it writes `Component`/`ComponentLocator`/`Assertion` rows — `DiscoveryActivity` never resolves duplicates or writes these three, and `InferenceActivity` only ever reads canonical rows (AD-14).

**`[RESOLVED 2026-07-18]`** The Application Model's page-grouping concept is served by the existing `Capability` entity — no separate `Module` entity is introduced.

### Story 2.6: AI Journey/Capability Inference from the Application Model `[RENUMBERED 2026-07-18, was Story 2.5]`

*Updated 2026-07-18 — reworked (reverted from `review` to `in-progress`) to read the Application Model built by Story 2.5 instead of raw Evidence directly, and renumbered after it (was Story 2.5, incorrectly numbered ahead of its own dependency); see `sprint-change-proposal-2026-07-18.md`.*

As a user,
I want the platform to turn captured discovery evidence into candidate Business Capabilities and Journeys in business language,
So that I have something meaningful to review instead of a raw crawl log.

**Acceptance Criteria:**

**Given** a Discovery Run that has completed, with its Application Model built (Story 2.5)
**When** `InferenceActivity` runs, calling the AI provider exclusively through the `AIProvider` port (AD-3, no direct vendor SDK import)
**Then** candidate `Journey`/`Capability` rows are written with `status=candidate` and a business-language name — never a raw route/page identifier (FR-8)
**And** each candidate Journey's supporting canonical Application Model rows (Page/Form/ApiEndpoint/Component — never a superseded/merged row) are attributed to it via `journey_id`, set by `InferenceActivity` (AD-8, AD-14)
**And** each candidate Journey gets a deterministic `identity_key` computed from its evidence shape, not its AI-generated name (AD-13)
**And** `Journey.discovery_run_id` is set once, at creation, and is immutable

## Epic 3: Human Curation & Trusted Knowledge Model `[RENAMED 2026-07-15, was "Human Review & Trusted Knowledge Model"]`

`[REWRITTEN 2026-07-15]` A reviewer curates discovered candidates (rename, delete) in the Discover Journeys screen; every discovered Journey is already in the Trusted Knowledge Model and generating coverage before the reviewer looks at it (Epic 2) — deletion is the only exclusion mechanism, not a gate. `[UPDATED 2026-07-21]` Epic 3 for V1 is Stories 3.1 and 3.4 only — cross-run re-discovery refinement (formerly Story 3.5) is out of scope for this version, to be revisited later. `InferenceActivity`'s existing `identity_key` find-or-create (Story 2.6) already prevents duplicate Journey rows on a re-discovery match; refining what happens beyond that on a match is the deferred work.

### Story 3.1: Discover Journeys — Candidate List & Detail Panel

*Renamed/updated 2026-07-15 (was "Review Queue"): this is now the pipeline's step 2 ("Discover Journeys"), and folds in FR-23 (Journey detail, relocated from the deferred Epic 6 Journey Explorer). No persistent nav rail exists — see Story 1.2.*

As a reviewer,
I want to see all candidate Journeys in a list and inspect the discovered detail behind any one of them,
So that I can judge each inference against what discovery actually captured.

**Acceptance Criteria:**

**Given** candidate Journeys exist for an Application
**When** the reviewer reaches the Discover Journeys pipeline step
**Then** each candidate row shows its business-language name and a step count (FR-9)
**And** selecting a row loads that Journey's discovered step-by-step detail — each step's route, method, and stage badge (e.g. "Login," "MFA Verification") — into a detail panel on the right, replacing any prior selection (FR-23, relocated)
**And** no confidence, risk, or importance score/percentage/star/flag appears anywhere on a candidate row or in the detail panel

**`[RESOLVED 2026-07-15]`** Three items previously flagged as gaps are now settled: **`New`/`Dupe` badges are cut** (not built), the **live pending-count indicator is cut** (its only home, the nav rail, is retired — no on-screen replacement is being built), and the **detail panel is sticky on scroll**, retaining its 340px width; its content changes only when the reviewer selects a different candidate row, never as a side effect of scrolling.

*(Stories 3.2 "Approve" and 3.3 "Reject" removed 2026-07-15 — no approval gate exists; every discovered Journey enters the Trusted Knowledge Model and starts generation immediately (FR-14). `GenerationWorkflow`-start logic lives in Story 2.6 (renumbered from 2.5, 2026-07-18); Delete (Story 3.4) is the sole exclusion mechanism.)*

### Story 3.4: Rename & Delete a Journey/Capability

*Updated 2026-07-15 — Edit (FR-28) was added, then cut the same day: its exact editable surface was never confirmed in the UX review, and product decided not to build it. Reverted to Rename & Delete only.*

As a reviewer,
I want to rename or delete a discovered Journey/Capability,
So that the Trusted Knowledge Model reflects names I trust and excludes what doesn't belong.

**Acceptance Criteria:**

**Given** a candidate Journey/Capability
**When** the reviewer renames it via the row's `⋯` menu
**Then** the new name is saved and displayed everywhere the Journey/Capability appears (FR-12)
**Given** a candidate Journey/Capability
**When** the reviewer deletes it (via the `⋯` menu)
**Then** it is excluded from the Trusted Knowledge Model — along with any Scenarios/Test Assets already generated for it — from Generate Suite compilation and Analytics (FR-13); this does not cancel an in-flight or completed `GenerationWorkflow`, consistent with FR-18's regeneration being the only way to redo generation for a kept Journey

## Epic 4: Scenario & Playwright Test Generation

`[UPDATED 2026-07-15]` Every discovered Journey automatically produces happy-path/negative Scenarios and executable Playwright Test Assets, viewable, and regenerable from scratch on request — generation starts immediately on discovery (Epic 2), not on approval.

### Story 4.1: Generate Scenarios for a Discovered Journey `[RENAMED 2026-07-15, was "...for an Approved Journey"]`

*Updated 2026-07-15 — Scenarios are no longer view-only; adds FR-29 (edit/remove). Trigger updated same day: generation starts on discovery, not approval (FR-10/FR-11 cut — see Epic 3).*

As a user,
I want a discovered Journey to automatically get integration test Scenarios covering both happy-path and negative cases,
So that the map becomes actionable test coverage, not just documentation.

**Acceptance Criteria:**

**Given** a Journey for which `InferenceActivity` started a `GenerationWorkflow` at creation (AD-1)
**When** `ScenarioGenerationActivity` runs, calling the AI provider only through the `AIProvider` port
**Then** `Scenario` rows are created for the Journey, covering both happy-path and negative/edge-case scenarios (FR-16)
**And** the Review Scenarios screen lists them with `Happy Path`/`Negative Path`/`Edge Case` badges, each with a `⋯` menu offering rename/edit/remove (FR-29)
**And** selecting a scenario shows its Test steps, a Test data table, and Expected result in a detail panel

**`[GAP — flagged 2026-07-15]`** Whether an edited Scenario's Test data/steps actually feed Playwright generation, or the edit is display-only, is unconfirmed — flag for engineering before implementing the edit action's persistence behavior.

**`[NOTE — 2026-07-18]`** `ScenarioGenerationActivity`'s AI context now draws on canonical Application Model rows (Story 2.5) rather than raw Evidence (removed) — no AC change, only richer input to the same `AIProvider` call.

*(Superseded 2026-07-15 — retained for history: the prior AC required Scenarios be strictly view-only with no checkbox/action button on any row (UX-DR23). This rule no longer holds — see FR-29 and `EXPERIENCE.md#Review & Trust Model`.)*

### Story 4.2: Generate Playwright Test Assets via a Named Test Suite

*Updated 2026-07-15 — reframed from a standalone "Generated Tests" code-review screen into "Generate Suite," the pipeline's 4th step. Underlying `TestAsset` generation is unchanged.*

As a user,
I want each generated Scenario converted into an executable Playwright test as part of a named, generated Test Suite,
So that I have real, runnable regression coverage for the Journey.

**Acceptance Criteria:**

**Given** generated Scenarios for a Journey
**When** `PlaywrightGenerationActivity` runs
**Then** a `TestAsset` row is created per Scenario, carrying the generated Playwright code, a `generation_run_id`, and `current=true` (FR-17, AD-8)
**And** the Generate Suite screen lets the user name the suite and confirm a target environment before generating, showing a summary (journey count, scenario count) alongside the generate action

**`[NOTE — 2026-07-18]`** `PlaywrightGenerationActivity`'s AI context now includes the Application Model's Component locator metadata (preferred + fallback locators) — no AC change, richer input to the same `AIProvider` call.

**`[NOTE FOR PM/ENG — 2026-07-15]`** The Generate Suite screen also shows an "Execution" choice (`Run immediately`/`Schedule for later`/`Save without running`) — this is a confirmed UI placeholder only; do not build execution/scheduling behavior against it (see architecture Deferred section). The screen the user sees immediately after clicking "Generate Test Suite" (i.e., whether the prior code-viewer + `<details>` disclosure pattern survives) was not reachable during UX review — `[GAP]`, retained as last-confirmed spec pending re-verification.

### Story 4.3: Full Regeneration of Test Assets on Request

As a user,
I want to trigger a full regeneration of a Journey's Scenarios and Test Assets,
So that I get fresh coverage after the Journey or my understanding of it has changed.

**Acceptance Criteria:**

**Given** a discovered Journey with existing, `current=true` Scenarios and Test Assets
**When** the user triggers regeneration
**Then** a new `GenerationWorkflow` attempt runs `ScenarioGenerationActivity` and `PlaywrightGenerationActivity` from scratch — never as an incremental diff/patch (FR-18)
**And** the new attempt's `Scenario`/`TestAsset` rows are written with `current=true`, while the prior attempt's rows flip to `current=false` (soft-superseded, retained for audit, never deleted) (AD-8)
**And** the regeneration Activity is idempotent under Temporal's at-least-once retry — a retried attempt does not produce duplicate current rows (AD-9)

*(Epic 5 "CI/CD Delivery" [Stories 5.1-5.3], Epic 6 "Analytics & Executive Dashboards" [Stories 6.1, 6.3, 6.4 — 6.2 relocated into Story 3.1], and Epic 7 "Deployment & AI Provider Configuration" [Stories 7.1-7.2] removed in full 2026-07-15. None had any supporting screen in the current UX; Epic 7's on-prem deployment is additionally a confirmed parked-for-later-release product decision. See `sprint-change-proposal-2026-07-15.md` for the original history and rationale.)*
