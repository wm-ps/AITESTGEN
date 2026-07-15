---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - "_bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md"
  - "_bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md"
  - "_bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md"
  - "_bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md"
updated: "2026-07-15 — see sprint-change-proposal-2026-07-15.md: Epic 5, most of Epic 6, and Epic 7 deferred post-V1; Epic 3/4 gain edit/remove actions (FR-28/29); Story 6.2 relocated into Story 3.1."
---

# Application Intelligence Platform - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Application Intelligence Platform (AITestGen), decomposing the requirements from the PRD, UX Design contract, and Architecture Spine into implementable stories.

## Requirements Inventory

### Functional Requirements

FR-1: User can onboard an Application by providing its URL, environment designation, and access credentials.
FR-2: Access credentials must correspond to a Dedicated Test Account provisioned by the customer, not a real end-user identity.
FR-3: Platform establishes a session prior to discovery either by (a) performing a standard/manual username-password login flow itself, or (b) reusing a pre-authenticated session (storage state) supplied by the customer for SSO/MFA-protected Applications; a Discovery Run whose session has expired fails gracefully and surfaces a re-authentication prompt.
FR-4: User can define a Discovery Scope (e.g., limit to specific sections/paths) rather than defaulting to full-Application discovery.
FR-5: User can configure a maximum time budget for a Discovery Run, as a safety cap against unbounded exploration.
FR-6: Platform autonomously navigates pages, exercises UI actions and forms, and invokes APIs within the configured Discovery Scope, capturing pages, navigation paths, actions, forms, API calls, and state transitions.
FR-7: A Discovery Run terminates when either (a) no new pages/actions/state transitions are found (exhaustive traversal), or (b) the configured maximum time budget is reached; a time-budget termination produces a partial result set clearly marked incomplete.
FR-8: Platform uses AI to transform captured discovery signals into candidate Business Capabilities and Journeys expressed in business language; every candidate Journey is associated with the specific pages/actions/API calls that produced it.
FR-9: Discovered Journeys and Capabilities are presented to a human reviewer before being treated as part of the Trusted Knowledge Model.
FR-10: Reviewer can approve a discovered Journey/Capability, adding it to the Trusted Knowledge Model.
FR-11: Reviewer can reject a discovered Journey/Capability, excluding it from the Trusted Knowledge Model.
FR-12: Reviewer can rename a discovered Journey/Capability.
FR-13: Reviewer can delete a discovered Journey/Capability. Out-of-scope note narrowed 2026-07-15: merging/splitting remain unsupported; editing is now supported (FR-28).
FR-14: Only approved Journeys/Capabilities enter the Trusted Knowledge Model and feed Scenario Generation and Analytics.
FR-15: Re-running discovery on a previously discovered Application flags only newly-discovered Journeys/Capabilities (existence check only, not change detection) for human review; already-approved Journeys are not automatically re-surfaced.
FR-16: Platform generates integration test Scenarios for each approved Journey, covering both happy-path and negative/edge-case scenarios.
FR-17: Platform converts generated Scenarios into executable Playwright Test Assets.
FR-18: When a customer triggers regeneration of Test Assets for a Journey, platform regenerates Scenarios and Test Assets from scratch (full regeneration only, not incremental). Updated 2026-07-15: Scenarios are now editable/removable pre-generation (FR-29).
FR-28 `[ADDED 2026-07-15]`: Reviewer can edit a discovered Journey via a per-row action menu, in addition to approve/reject/rename/delete. `[GAP]` exact edit surface unconfirmed.
FR-29 `[ADDED 2026-07-15]`: Reviewer can rename, edit, or remove a generated Scenario before Playwright generation. `[GAP]` whether edits feed generation or are display-only is unconfirmed.

**`[DEFERRED POST-V1 — 2026-07-15]`** FR-19 through FR-27 below are deferred out of V1 scope — no supporting screen exists in the current reference prototype's IA for any of them. Retained verbatim as a record of original intent; see `sprint-change-proposal-2026-07-15.md`. FR-23 is the one exception: retained and relocated (see its entry).

FR-19: Platform can export generated Playwright Test Assets to the customer's source repository via either (a) creating a pull/merge request, or (b) direct commit to a branch — chosen per Application, mutually exclusive modes.
FR-20: Platform supports repository/pipeline targets for GitHub Actions, GitLab CI, Jenkins, and Azure DevOps.
FR-21: Platform provides instructions/a template, specific to the Application's configured CI/CD provider, for the customer to manually wire generated tests into their CI pipeline's test-run step.
FR-22: Platform provides a Capability Map view — a business-language map of approved Capabilities; rejected/deleted candidates never appear.
FR-23: `[RETAINED, RELOCATED 2026-07-15]` Platform provides Journey-detail — a view of a Journey's screens, actions, and API calls captured during discovery. As of 2026-07-15, served inline in the discovery-review screen's detail panel (selecting a candidate), not a standalone Journey Explorer screen.
FR-24: Platform provides coverage analytics showing which approved Journeys have a generated Test Asset and which do not (generated-vs-not only, no live CI pass/fail read-back).
FR-25: Platform provides an executive dashboard rolling up Capability, coverage, and Journey views across multiple Applications, supporting multi-application onboarding from V1 launch.
FR-26: Platform supports hosted SaaS and on-premises/VPN-based deployment.
FR-27: In on-premises deployment, the entire platform — including AI/LLM processing — runs inside the customer's network, using AI provider API keys/endpoints supplied by the customer.

### NonFunctional Requirements

NFR-1 (Security): Standard enterprise-grade secret handling for stored discovery credentials — encryption at rest and in transit, least-privilege service accounts. No bespoke certification requirement specified for V1.
NFR-2 (Reliability): A Discovery Run must complete or fail gracefully within its configured time budget; partial results are retained and clearly marked incomplete on timeout.
NFR-3 (Data locality, on-prem): On-prem deployment must keep all data and AI processing inside the customer's network (ties to FR-27).
NFR-4 (Accessibility): WCAG 2.1/2.2 AA is the accessibility floor across the entire desktop surface — behavioral commitments (focus visibility, keyboard operability, contrast), not a compliance badge.
NFR-5 (Platform scope): Desktop web app only — no mobile or tablet form factor / responsive parity in V1.

### Additional Requirements

- No starter/greenfield template is specified by Architecture; instead a structural seed (`apps/web`, `apps/api`, `apps/workers/discovery`, `apps/workers/generation`, `packages/domain`, `packages/workflows`, `packages/ai_provider`, `packages/delivery_adapters`, `packages/ci_instructions`, `packages/secrets_client`, `migrations/`) is fixed — Epic 1 Story 1 should scaffold this structure directly rather than starting from an external template.
- Paradigm: Durable Orchestrated Pipeline with Ports & Adapters — Temporal Workflows carry coordination only (no I/O); Temporal Activities are the only place side effects (browser automation, LLM calls, DB writes, Git operations) happen (AD-1, AD-2).
- `DiscoveryWorkflow` is bounded and terminates by writing candidate Journeys/Capabilities to Postgres with `status=candidate`; human review is ordinary CRUD via `apps/api`, never a Temporal Signal/Update on a long-lived workflow (AD-1).
- Each Journey approval starts an independent `GenerationWorkflow` with workflow ID `generation-{journey_id}-{attempt}`, where `attempt` is incremented transactionally by `apps/api` in the same write that sets `status=approved` (AD-1, AD-9).
- All AI/LLM calls must go through one `AIProvider` port (`packages/ai_provider`); no Activity may import a vendor AI SDK directly (AD-3).
- CI/CD delivery must go through one `DeliveryAdapter` port keyed by the Application's configured Git host (GitHub, GitLab, Azure Repos) — never by CI system; manual pipeline-wiring instructions are a separate concern owned by `packages/ci_instructions`, keyed by CI system (GitHub Actions/GitLab CI/Jenkins/Azure Pipelines), independent of Git host (AD-4).
- Discovery credentials and SSO/MFA session state must never touch primary storage in plaintext — read/written only via `packages/secrets_client`, backed by Vault or cloud KMS envelope encryption; `packages/domain` models store only a secret reference (AD-5).
- The API's generated OpenAPI spec is the only contract between `apps/web` and `apps/api` — frontend TypeScript types are generated from the FastAPI/Pydantic OpenAPI spec; no hand-written duplicate request/response shape is permitted (AD-6).
- The Trusted Knowledge Model has exactly one writer path: only `apps/api`'s review endpoints may transition a Journey/Capability's status to `approved`/`rejected`; workers may only write `candidate` or downstream generation status (AD-7).
- Every inferred artifact keeps a live pointer back to its evidence at the right granularity: `Evidence` rows are tagged `discovery_run_id` at capture and attributed `journey_id` by `InferenceActivity`; `Journey.discovery_run_id` is immutable; `Scenario`/`TestAsset` rows carry `generation_run_id` plus a `current: bool` flag, with prior attempts soft-superseded (never deleted) on regeneration (AD-8).
- Large binary evidence artifacts (screenshots, DOM snapshots) are never stored inline in Postgres — `Evidence` holds an object-storage key/reference; structured metadata lives in Postgres (AD-8).
- Every side-effecting Activity (form submission, PR/commit creation) must be idempotent under Temporal's at-least-once retry, using a deterministic check-before-acting key derived from its inputs; the approve endpoint's `status=approved` write and `GenerationWorkflow` start happen in the same request, with a startup reconciliation sweep for orphaned approvals (AD-9).
- `DiscoveryRun.status` must be a first-class, queryable field (`running | complete | incomplete | failed`) — completeness is never inferred from presence/absence of other data (AD-10).
- Session expiry mid-crawl must be detected as a distinct condition from a normal stop condition, terminating the run with `status=failed`, `failure_reason=session_expired`, surfaced by `apps/api` as a re-authentication prompt distinguishable from `incomplete` or other failures (AD-11).
- `Organization` is a first-class tenant-boundary entity; every `apps/api` query must be scoped by the authenticated user's Organization through one central mechanism, never left to individual endpoints (AD-12).
- Each candidate Journey needs a deterministic `identity_key` computed from its underlying evidence shape (not its AI-generated display name); re-discovery dedup/suppression for FR-15 compares against this key and never alters existing attribution (AD-13).
- Stack versions to build against: Python 3.14.6, FastAPI (current stable), SQLModel (current stable), Alembic (current stable), PostgreSQL 18.4, Temporal Python SDK (current GA), Playwright Python 1.57+, React 19.x, Vite 8.1.x, TypeScript 7.0 GA (verify AD-6's OpenAPI→TS codegen tooling supports it before adopting, else pin TypeScript 5.9 as fallback).
- Platform's own CI (build/test/lint of this codebase) runs on GitHub Actions; every `apps/*` service ships as its own container image; traces/metrics use OpenTelemetry, correlated by Temporal `workflow_id` (matching structured-log correlation).
- Deferred by explicit architecture decision (not to be designed against in V1 stories): SaaS vs. on-prem deployment topology and where Temporal itself runs; the object-storage backend provider; direct-commit regeneration conflict handling; a non-production technical safeguard; confidence/risk-scoring reintroduction; reviewer prioritization/importance-marking; tenant billing/plan model.
- Blocking dependency: the SSO/MFA session-state capture mechanism (PRD Open Question 8) is unresolved and blocks detailed design/build of the Onboarding flow's auth step (FR-3) — stories touching this step must treat the mechanism as a placeholder pending that decision.
- Implementation-only choice, no architectural constraint either way: whether the nav rail's live pending-review count badge is delivered via client-side refetch/decrement or a push channel (WebSocket/SSE) is left to the implementer.

### UX Design Requirements

UX-DR1: Implement the full design-token system (color, typography, spacing, radius) as CSS custom properties with true light/dark parity — `:root` sets light values + `color-scheme: light`, a `@media (prefers-color-scheme: dark)` block overrides for OS dark preference, and explicit `:root[data-theme="dark"]`/`[data-theme="light"]` attribute selectors let an in-app toggle override the OS preference. No component may hardcode a color outside the token layer.
UX-DR2: Build the persistent app shell — fixed-width (236px) nav rail plus fluid main column (content capped at 1180px) — with links grouped under five section labels (Workspace, Onboard, Understand, Automate, Prove), active-link highlighting, and Settings/sign-out pinned to the rail foot below a divider.
UX-DR3: Add a live pending-review count badge to the Review Journeys nav-rail link only, updating as items are triaged.
UX-DR4: Build the two-pane Review Journeys pattern — a scannable queue-row list plus a sticky (340px, sticky on scroll) evidence panel that loads the selected row's full evidence trail (pages/actions/API calls) rendered in monospace.
UX-DR5: Build the review-row component with exactly four actions for undecided rows — Approve, Rename, Reject, Delete; a decided row (approved/rejected) removes all four action buttons entirely (not disabled) and mutes/dims its title.
UX-DR6: Build the badge component with variants `new`, `dupe`, `approved`, `rejected`, `type-happy`, `type-negative`, `generated` — every variant is a tinted-wash background plus saturated text of the same hue, never a solid fill.
UX-DR7: Build the status-pill component with a pulsing dot for in-progress states; on Discovery Progress, it must automatically transition from "Running" to an amber "Incomplete" state the moment a Discovery Run's time budget is reached (FR-7), without a separate visual pattern. `[UPDATED 2026-07-15: dropped "Applications table row" — no Application-list view is confirmed in the current IA.]`
UX-DR8: Build the Capability card component (App Overview) — bordered static rollup showing Capability name, journey-count pill, one-line description, and a nested list of approved Journeys with a status dot and test-count in monospace; clicking a nested Journey name is not an interaction in V1.
UX-DR9: Build KPI tile and hero-stat strip components (Dashboard, Applications) using tabular-nums numeric formatting; a hero-stat strip may color at most one number with the signal accent (the item most deserving first attention), all others in default ink color.
UX-DR10: Build the Add Application stepper — only the active step renders its full form body; completed steps collapse to a one-line summary, pending steps show only their title; a completed step is not clickable to jump back to.
UX-DR11: Build the option-card/provider-card selection control (real `<input type="radio">` under a styled card) for: Add Application's auth-method choice, and Connect to CI/CD's export-mode and provider choices — exactly one selection per group, selecting a new option deselects the previous one.
UX-DR12: Build the code-viewer + native `<details>`/`<summary>` disclosure component for generated Playwright code and CI/CD pipeline snippets, with light syntax tinting (keywords/strings/comments) — closed by default for every block except the first/most-relevant one per screen; opening one disclosure never closes others.
UX-DR13: Build the toggle-switch component for genuine binary settings only (e.g., AI-provider mode, notification preferences) — immediate on/off, no confirmation step, never repurposed as a selection control.
UX-DR14: Build the empty-state component (dashed-border panel, circular check icon, one-line factual confirmation) shown only when a queue/list is fully triaged; on Review Journeys specifically, include an Approved/Rejected count summary.
UX-DR15: Implement the 11-screen information architecture with function-first screen names — Login (pre-shell); Applications, Add Application, Discovery Progress, App Overview, Review Journeys, Generated Scenarios, Generated Tests, Connect to CI/CD, Dashboard, Settings (in-shell) — and the primary linear flow Applications → Add Application → Discovery Progress → App Overview → Review Journeys → Generated Scenarios → Generated Tests → Connect to CI/CD → Dashboard.
UX-DR16: Implement the breadcrumb/app-name context rule — show the current Application's name in the top-bar crumb only on Application-scoped screens (Discovery Progress, App Overview, Review Journeys, Generated Scenarios, Generated Tests, Connect to CI/CD, Settings); suppress it on Applications, Add Application, and Dashboard.
UX-DR17: Implement state-pattern behavior for: Discovery running (live-feed list, newest first) vs. time-budget-incomplete; review-queue in-progress vs. resolved-row (muted, badge-only) vs. cleared (empty state); CI/CD provider connected ("Connected" label); and Dashboard coverage-gap (inline "N pending test" warning flag per PRD UJ-2).
UX-DR18: Enforce the accessibility floor across every new screen/component — WCAG 2.1/2.2 AA; visible focus ring on every interactive element (buttons, nav-rail links, inputs, selects, textareas, `<summary>` triggers); real keyboard-operable `<input type="radio">` under styled option/provider cards (never a `<div onclick>` substitute); tab order matches visual order (list before evidence panel on Review Journeys).
UX-DR19: Enforce the label/caption contrast rule everywhere new text is added — all real label/caption/metadata text routes through the `ink-muted` token (~5:1 AA contrast); the `ink-faint` token is reserved exclusively for decorative, non-text marks (disabled affordances, placeholder dashes) and must never carry real copy.
UX-DR20: Enforce voice-and-tone constraints in all authored UI copy — no exclamation points, emoji, or celebratory language anywhere; capitalize Application, Capability, Journey, Scenario, Test Asset, and Trusted Knowledge Model as proper nouns consistently; state errors/hints/constraints as fact + why, never apology-only or unexplained.
UX-DR21: Enforce the hard product constraint that no AI confidence, risk, or importance signal (score, percentage, star rating, priority flag) may appear anywhere near discovered/inferred content (Journeys, Capabilities, Scenarios) — this applies to every new screen, not just the ones in the approved prototype.
UX-DR22: Enforce the "no merge/split/composition-edit" constraint — no future Journey-review screen or component may offer a merge, split, or inline edit of what pages/actions/API calls compose a Journey; duplicate candidates are flagged with a `dupe` badge and rejected, never merged.
UX-DR23: Enforce that Generated Scenarios remain view-only — no checkbox selection, per-scenario approval, or action buttons on a scenario row; the only approval gate is at the Journey level.
UX-DR24: Reserve monospace typography (`font-mono`) exclusively for raw captured evidence and generated code (routes, API call signatures, timestamps, file paths, Playwright code) — never for authored UI copy (labels, headings, hints, empty-state text), even where a technical look might seem appropriate.

### FR Coverage Map

FR-1: Epic 1 - Application onboarding (URL, environment, credentials)
FR-2: Epic 1 - Dedicated Test Account credential requirement
FR-3: Epic 1 - Authentication via login flow or storage-state reuse
FR-4: Epic 1 - Configurable discovery scope
FR-5: Epic 1 - Discovery time budget
FR-6: Epic 2 - Autonomous exploration capturing pages/actions/APIs/state
FR-7: Epic 2 - Discovery stop conditions (exhaustive vs. time-budget incomplete)
FR-8: Epic 2 - AI journey/capability inference with evidence association
FR-9: Epic 3 - Review queue presentation
FR-10: Epic 3 - Approve action
FR-11: Epic 3 - Reject action
FR-12: Epic 3 - Rename action
FR-13: Epic 3 - Delete action
FR-14: Epic 3 - Approval gates downstream use (Trusted Knowledge Model)
FR-15: Epic 3 - New-journey flagging on re-discovery
FR-16: Epic 4 - Scenario generation (happy-path + negative)
FR-17: Epic 4 - Playwright Test Asset generation
FR-18: Epic 4 - Full regeneration on request
FR-28: Epic 3 - Edit a discovered Journey `[ADDED 2026-07-15]`
FR-29: Epic 4 - Edit/remove a generated Scenario `[ADDED 2026-07-15]`
FR-19: Epic 5 `[DEFERRED POST-V1]` - Export mode choice (PR vs. direct commit)
FR-20: Epic 5 `[DEFERRED POST-V1]` - CI/CD provider support (GitHub Actions, GitLab CI, Jenkins, Azure DevOps)
FR-21: Epic 5 `[DEFERRED POST-V1]` - Manual pipeline wiring instructions
FR-22: Epic 6 `[DEFERRED POST-V1]` - Capability Map view
FR-23: Epic 3 `[RETAINED, RELOCATED]` - Journey step/evidence detail, now inline in the discovery-review screen (was Epic 6 - Journey Explorer)
FR-24: Epic 6 `[DEFERRED POST-V1]` - Coverage analytics
FR-25: Epic 6 `[DEFERRED POST-V1]` - Multi-application executive dashboard
FR-26: Epic 7 `[DEFERRED POST-V1]` - Two deployment models (SaaS + on-prem)
FR-27: Epic 7 `[DEFERRED POST-V1]` - On-prem data locality / customer-supplied AI endpoint

NFR-1 (Security): Epic 1 - Secret handling for stored discovery credentials
NFR-2 (Reliability): Epic 2 - Graceful completion/failure within time budget
NFR-3 (Data locality): Epic 7 - On-prem data/AI processing stays in-network
NFR-4 (Accessibility): Cross-cutting - WCAG 2.1/2.2 AA applied within every epic's UI stories
NFR-5 (Platform scope): Cross-cutting - Desktop-only constraint applied within every epic's UI stories

## Epic List

### Epic 1: Foundation, Auth & Application Onboarding
A user can sign in, and onboard an Application (URL, environment, Dedicated Test Account credentials, discovery scope, time budget) — ready for its first Discovery Run. Establishes the structural seed scaffold, Organization tenancy, credential handling via SecretsClient, and the app shell/design-token foundation everything else builds on.
**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-5

### Epic 2: Runtime Discovery & AI Journey Inference
A user can start a Discovery Run, watch live progress (running/incomplete/failed-session-expired), and see AI-inferred candidate Journeys/Capabilities, each traceable to captured evidence.
**FRs covered:** FR-6, FR-7, FR-8

### Epic 3: Human Review & Trusted Knowledge Model
A reviewer can approve/reject/rename/edit/delete candidates in the Review queue, and inspect any candidate's discovered step/evidence detail inline; approved items enter the Trusted Knowledge Model; re-running discovery only flags genuinely new Journeys.
**FRs covered:** FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-23 (relocated 2026-07-15), FR-28 (added 2026-07-15)

### Epic 4: Scenario & Playwright Test Generation
Approving a Journey automatically produces happy-path/negative Scenarios (rename/edit/removable pre-generation as of 2026-07-15) and executable Playwright Test Assets, generated as a named Test Suite, regenerable from scratch on request.
**FRs covered:** FR-16, FR-17, FR-18, FR-29 (added 2026-07-15)

### Epic 5: CI/CD Delivery `[DEFERRED POST-V1 — 2026-07-15]`
A user configures a Git host and CI system per Application and gets generated tests delivered via PR or direct commit, plus provider-specific manual wiring instructions. Deferred: no supporting screen in current scope, real delivery/execution mechanism undecided — see `sprint-change-proposal-2026-07-15.md`.
**FRs covered:** FR-19, FR-20, FR-21

### Epic 6: Analytics & Executive Dashboards `[MOSTLY DEFERRED POST-V1 — 2026-07-15]`
Capability Map, coverage analytics, and a multi-application executive dashboard are deferred — no supporting screen in current scope. Journey Explorer (FR-23) moved to Epic 3, relocated inline.
**FRs covered:** FR-22, FR-24, FR-25 (all deferred)

### Epic 7: Deployment & AI Provider Configuration `[DEFERRED POST-V1 — 2026-07-15]`
An organization can run hosted SaaS or configure the platform to use its own AI provider endpoint/keys for on-prem, in-network processing. Deferred: Settings, the only confirmed UI entry point, is cut from current scope — flagged for explicit reconfirmation given these are compliance/data-residency NFRs, not a convenience feature.
**FRs covered:** FR-26, FR-27

## Epic 1: Foundation, Auth & Application Onboarding

A user can sign in, and onboard an Application (URL, environment, Dedicated Test Account credentials, discovery scope, time budget) — ready for its first Discovery Run.

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
**When** they choose "Start a New Project" (or "Managed Applications") and submit Application name, Base URL, environment, and credentials on the single Connect App form
**Then** an `Application` record is created, scoped to their Organization, and the submitted credentials are written only through `packages/secrets_client` (Vault/KMS-backed), never stored in plaintext in Postgres or logs (FR-2, AD-5, NFR-1)
**And** the credentials field is explicitly labeled as requiring a Dedicated Test Account, not a real end-user identity (FR-2)
**And** the Connect App screen shows the current Application's name and environment badge in the top bar once submitted, per the (2026-07-15) breadcrumb rule

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

### Story 1.5: Configure Discovery Scope & Time Budget

**`[GAP — flagged 2026-07-15]`** The current reference prototype's Connect App form does not show Discovery Scope or Time Budget fields anywhere. Unlike the confirmed-cut screens (Applications list, App Overview, Dashboard, CI/CD, Settings), these fields were never explicitly identified as cut — they may simply be below the fold, in a later-added "Advanced" section, or genuinely dropped. **Do not build or drop this story on the current evidence** — re-verify against a fuller prototype export first. AC below is retained unchanged from the prior revision as the last-confirmed spec pending that check.

As a user onboarding an Application,
I want to set a discovery scope and a maximum time budget,
So that discovery stays bounded to what I intend and within a safety cap.

**Acceptance Criteria:**

**Given** a user on the Connect App form
**When** they optionally restrict scope to specific sections/paths, and set a maximum time budget
**Then** those values are saved on the `Application` record, defaulting to full-Application scope if left unspecified (FR-4, FR-5)
**And** submitting returns the user to the pipeline's Discover Journeys step, where the new Application's discovery begins
**And** the breadcrumb/context rule is honored: Connect App carries no Application-name breadcrumb until submission (no Application exists yet)

## Epic 2: Runtime Discovery & AI Journey Inference

A user can start a Discovery Run, watch live progress, and see AI-inferred candidate Journeys/Capabilities, each traceable to captured evidence.

### Story 2.1: Start a Discovery Run

As a user,
I want to start a Discovery Run against an onboarded Application,
So that the platform begins mapping its business journeys.

**Acceptance Criteria:**

**Given** an onboarded Application
**When** the user starts a Discovery Run from the Applications or Discovery Progress screen
**Then** a `DiscoveryRun` record is created with `status=running`, and a bounded `DiscoveryWorkflow` is started for it (AD-1) — the workflow contains no direct I/O, only calls to Activities (AD-2)
**And** the Discovery Progress screen shows a status pill reading "Running" with a pulsing dot

### Story 2.2: Autonomous Exploration Captures Evidence

As a user,
I want the platform to autonomously explore my Application within its configured scope,
So that raw discovery signal is captured as the basis for journey mapping.

**Acceptance Criteria:**

**Given** a running Discovery Run with a configured scope
**When** `DiscoveryActivity` navigates pages, exercises UI actions and forms, and invokes APIs within that scope
**Then** each captured page, action, form, API call, and state transition is written as an `Evidence` row tagged with `discovery_run_id` (FR-6, AD-8)
**And** large binary artifacts (screenshots, DOM snapshots) are referenced via an object-storage key, never stored inline in Postgres
**And** the Discovery Progress screen's live-feed list shows the most recently captured pages/actions/API calls, newest first, in monospace, appended as discovery proceeds

### Story 2.3: Discovery Stop Conditions & Completeness Status

As a user,
I want a Discovery Run to stop when exploration is exhaustive or its time budget is reached, and to see clearly whether the result is complete,
So that I never mistake a partial map for a finished one.

**Acceptance Criteria:**

**Given** a running Discovery Run
**When** no new pages, actions, or state transitions are found
**Then** `DiscoveryRun.status` is set to `complete` (FR-7, AD-10)
**Given** a running Discovery Run instead reaches its configured time budget before exhaustive traversal
**When** the time budget elapses
**Then** `DiscoveryRun.status` is set to `incomplete`, and the status pill automatically transitions from "Running" to an amber "Incomplete" state — the same status-pill component, not a separate visual pattern
**And** completeness is read directly from `DiscoveryRun.status` everywhere it's shown, never inferred from the presence or absence of other data

### Story 2.4: Session Expiry Handling

As a user,
I want to be told plainly when a Discovery Run fails because my session expired,
So that I can re-authenticate rather than mistake it for a normal, if small, result.

**Acceptance Criteria:**

**Given** a running Discovery Run whose session has expired mid-crawl (detected via an auth-redirect)
**When** `DiscoveryActivity` detects this condition
**Then** it terminates the run with `DiscoveryRun.status=failed`, `failure_reason=session_expired` — a condition distinct from a normal stop condition (AD-11)
**And** the platform surfaces a re-authentication prompt keyed specifically off `session_expired`, visually distinguishable from an `incomplete` (time-budget) run and from any other `failed` cause (FR-3)

### Story 2.5: AI Journey/Capability Inference from Evidence

As a user,
I want the platform to turn captured discovery evidence into candidate Business Capabilities and Journeys in business language,
So that I have something meaningful to review instead of a raw crawl log.

**Acceptance Criteria:**

**Given** a Discovery Run that has completed or gone incomplete, with captured Evidence
**When** `InferenceActivity` runs, calling the AI provider exclusively through the `AIProvider` port (AD-3, no direct vendor SDK import)
**Then** candidate `Journey`/`Capability` rows are written with `status=candidate` and a business-language name — never a raw route/page identifier (FR-8)
**And** each candidate Journey's supporting `Evidence` rows are attributed to it via `journey_id`, set by `InferenceActivity` (AD-8)
**And** each candidate Journey gets a deterministic `identity_key` computed from its evidence shape, not its AI-generated name (AD-13)
**And** `Journey.discovery_run_id` is set once, at creation, and is immutable

## Epic 3: Human Review & Trusted Knowledge Model

A reviewer can approve/reject/rename/delete candidates in the Review queue; approved items enter the Trusted Knowledge Model; re-running discovery only flags genuinely new Journeys.

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

**`[GAP — flagged 2026-07-15]`** `New`/`Dupe` badges, a live pending-count indicator, and sticky-on-scroll behavior for the detail panel were part of the prior revision's spec but were not confirmed present in the current reference prototype. Retained as last-confirmed spec pending re-verification — do not assume they're gone, but don't assume they survived unchanged either.

### Story 3.2: Approve a Journey/Capability

As a reviewer,
I want to approve a discovered Journey/Capability,
So that it enters the Trusted Knowledge Model and downstream generation can begin.

**Acceptance Criteria:**

**Given** an undecided candidate Journey/Capability
**When** the reviewer clicks Approve
**Then** only `apps/api`'s review endpoint transitions its status to `approved` — no worker or other code path may perform this transition (FR-10, FR-14, AD-7)
**And** in the same request, the endpoint increments the Journey's `attempt` counter and starts an independent `GenerationWorkflow` with workflow ID `generation-{journey_id}-{attempt}` (AD-1) — a duplicate/double-click approval is a no-op because Temporal rejects the duplicate workflow ID (AD-9)
**And** the row immediately drops its four action buttons (not disabled — removed) and its title mutes, reflecting its new `Approved` badge

### Story 3.3: Reject a Journey/Capability

As a reviewer,
I want to reject a discovered Journey/Capability — including a duplicate flagged by the platform,
So that redundant or invalid candidates never enter the Trusted Knowledge Model.

**Acceptance Criteria:**

**Given** an undecided candidate Journey/Capability, including one carrying a `Dupe` badge
**When** the reviewer clicks Reject
**Then** its status transitions to `rejected` via the same single review-endpoint writer path (FR-11, AD-7), and it is excluded from the Trusted Knowledge Model
**And** no merge or split action is offered anywhere in this flow — a duplicate is resolved by rejecting or editing it (FR-28), never by combining it with another Journey

### Story 3.4: Rename, Edit & Delete a Journey/Capability

*Updated 2026-07-15 — adds Edit (FR-28), previously out of scope.*

As a reviewer,
I want to rename, edit, or delete a discovered Journey/Capability,
So that the Trusted Knowledge Model reflects names and content I trust.

**Acceptance Criteria:**

**Given** an undecided candidate Journey/Capability
**When** the reviewer renames it via the row's `⋯` menu
**Then** the new name is saved and displayed everywhere the Journey/Capability appears (FR-12)
**Given** an undecided candidate Journey/Capability
**When** the reviewer chooses Edit from the `⋯` menu
**Then** they can modify it and the change is saved (FR-28) — **`[GAP]`** the exact editable surface (name/description only, vs. constituent steps) is unconfirmed; do not build against an assumed field set without a follow-up UX pass
**Given** an undecided candidate Journey/Capability
**When** the reviewer deletes it (via the `⋯` menu)
**Then** it is removed from the review queue and never enters the Trusted Knowledge Model (FR-13)

### Story 3.5: Discover Journeys Empty State & New-Journey Flagging on Re-Discovery

**`[GAP — flagged 2026-07-15]`** The empty-state treatment below is retained unchanged from the prior revision as last-confirmed spec — it was not reachable in the current reference prototype (never seen with zero remaining candidates). Re-verify before treating as final.

As a reviewer,
I want a clear confirmation once I've triaged every candidate, and to see only genuinely new Journeys on a re-discovery run,
So that I never have to re-review something I've already decided on.

**Acceptance Criteria:**

**Given** the reviewer has decided on every candidate in the queue
**When** the last undecided row is resolved
**Then** the queue's list is replaced by an empty-state panel showing a factual confirmation line plus an Approved/Rejected count pair (FR-9, UX-DR14)
**Given** discovery is re-run on a previously discovered Application
**When** `InferenceActivity` produces new candidates
**Then** only candidates whose `identity_key` does not match any existing Journey in the Application are surfaced in the review queue (FR-15, AD-13) — already-approved Journeys are never automatically re-surfaced, and a suppressed match does not alter the existing Journey's `discovery_run_id` or evidence attribution

## Epic 4: Scenario & Playwright Test Generation

Approving a Journey automatically produces happy-path/negative Scenarios and executable Playwright Test Assets, viewable, and regenerable from scratch on request.

### Story 4.1: Generate Scenarios for an Approved Journey

*Updated 2026-07-15 — Scenarios are no longer view-only; adds FR-29 (edit/remove).*

As a user,
I want an approved Journey to automatically get integration test Scenarios covering both happy-path and negative cases,
So that the map becomes actionable test coverage, not just documentation.

**Acceptance Criteria:**

**Given** a Journey whose approval started a `GenerationWorkflow`
**When** `ScenarioGenerationActivity` runs, calling the AI provider only through the `AIProvider` port
**Then** `Scenario` rows are created for the Journey, covering both happy-path and negative/edge-case scenarios (FR-16)
**And** the Review Scenarios screen lists them with `Happy Path`/`Negative Path`/`Edge Case` badges, each with a `⋯` menu offering rename/edit/remove (FR-29)
**And** selecting a scenario shows its Test steps, a Test data table, and Expected result in a detail panel

**`[GAP — flagged 2026-07-15]`** Whether an edited Scenario's Test data/steps actually feed Playwright generation, or the edit is display-only, is unconfirmed — flag for engineering before implementing the edit action's persistence behavior.

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

**`[NOTE FOR PM/ENG — 2026-07-15]`** The Generate Suite screen also shows an "Execution" choice (`Run immediately`/`Schedule for later`/`Save without running`) — this is a confirmed UI placeholder only; do not build execution/scheduling behavior against it (see architecture Deferred section). The screen the user sees immediately after clicking "Generate Test Suite" (i.e., whether the prior code-viewer + `<details>` disclosure pattern survives) was not reachable during UX review — `[GAP]`, retained as last-confirmed spec pending re-verification.

### Story 4.3: Full Regeneration of Test Assets on Request

As a user,
I want to trigger a full regeneration of a Journey's Scenarios and Test Assets,
So that I get fresh coverage after the Journey or my understanding of it has changed.

**Acceptance Criteria:**

**Given** an approved Journey with existing, `current=true` Scenarios and Test Assets
**When** the user triggers regeneration
**Then** a new `GenerationWorkflow` attempt runs `ScenarioGenerationActivity` and `PlaywrightGenerationActivity` from scratch — never as an incremental diff/patch (FR-18)
**And** the new attempt's `Scenario`/`TestAsset` rows are written with `current=true`, while the prior attempt's rows flip to `current=false` (soft-superseded, retained for audit, never deleted) (AD-8)
**And** the regeneration Activity is idempotent under Temporal's at-least-once retry — a retried attempt does not produce duplicate current rows (AD-9)

## Epic 5: CI/CD Delivery `[DEFERRED POST-V1 — 2026-07-15]`

**Deferred out of V1 scope as of 2026-07-15** — the Connect to CI/CD screen this epic depended on is cut from the current reference prototype's IA; Generate Suite's replacement "Execution" control is a confirmed placeholder with no real mechanism yet. Do not schedule these stories for dev-story until the real delivery/execution mechanism is designed. Stories below are retained verbatim as a record of V1's original intent. See `sprint-change-proposal-2026-07-15.md`.

A user configures a Git host and CI system per Application and gets generated tests delivered via PR or direct commit, plus provider-specific manual wiring instructions.

### Story 5.1: Configure Git Host & Export Mode per Application

As a user,
I want to choose my Application's Git host and export mode (pull request vs. direct commit),
So that generated tests land in my repository the way my team actually works.

**Acceptance Criteria:**

**Given** a user on the Connect to CI/CD screen
**When** they select a Git host (GitHub, GitLab, or Azure Repos) and an export mode via provider/option cards
**Then** the choice is saved on the Application's `CIConfig`, with exactly one Git host and one export mode selected at a time (FR-19)
**And** an Application configured for PR mode never receives a direct commit, and vice versa — the two modes are mutually exclusive per Application

### Story 5.2: Deliver Test Assets via Pull Request or Direct Commit

As a user,
I want generated Test Assets automatically delivered to my configured Git host,
So that the tests reach my real repository without manual copy-paste.

**Acceptance Criteria:**

**Given** a `TestAsset` ready for delivery and an Application with a configured Git host and export mode
**When** `CIDeliveryActivity` runs
**Then** it calls only the `DeliveryAdapter` interface, selected by the Application's configured Git host — never by its CI system (FR-19, AD-4)
**And** it checks for an existing PR/commit using a deterministic key derived from `journey_id` + `attempt` before acting, so a retried delivery reuses its own prior effect instead of duplicating it (AD-9)
**And** once delivered, the Connect to CI/CD screen's provider card shows a "Connected" status label

### Story 5.3: Select CI System & Receive Manual Wiring Instructions

As a user,
I want instructions specific to my CI system for wiring generated tests into my pipeline's test-run step,
So that I can complete the last mile into my real regression process myself.

**Acceptance Criteria:**

**Given** a user selects a CI system (GitHub Actions, GitLab CI, Jenkins, or Azure Pipelines) for their Application
**When** they view the wiring instructions
**Then** `CIInstructionsGenerator` renders a template specific to that CI system, independent of which Git host the Application delivers to (FR-20, FR-21, AD-4) — e.g., a Jenkins-on-GitHub Application gets the GitHub `DeliveryAdapter` plus Jenkins-flavored instructions
**And** the instructions render inside a `<details>` disclosure, closed by default unless it is the first/most-relevant block on the screen

## Epic 6: Analytics & Executive Dashboards `[MOSTLY DEFERRED POST-V1 — 2026-07-15]`

Capability Map, coverage analytics, and a multi-application executive dashboard let QA/Engineering leadership see what's understood, tested, and gapped. **Story 6.2 (Journey Explorer) has moved to Epic 3** (Story 3.1), relocated inline into the discovery-review flow — it is not deferred. Stories 6.1, 6.3, 6.4 are deferred out of V1 scope as of 2026-07-15: no supporting screen exists in the current reference prototype's IA for any of them, and PRD UJ-2 (which 6.4 realized) is deferred alongside. Retained verbatim as a record of V1's original intent. See `sprint-change-proposal-2026-07-15.md`.

### Story 6.1: Capability Map `[DEFERRED POST-V1]`

As a QA Director or Engineering Leader,
I want a business-language map of an Application's approved Capabilities,
So that I can show what the application actually does without anyone having had to document it by hand.

**Acceptance Criteria:**

**Given** an Application with approved Capabilities
**When** the user opens App Overview
**Then** every approved Capability appears as a card showing its name, a journey-count pill, a one-line description, and a nested list of its approved Journeys with a status dot and test-count in monospace (FR-22)
**And** rejected or deleted candidates never appear in this view

### Story 6.2: Journey Explorer — `[MOVED to Story 3.1, 2026-07-15]`

Superseded — see Story 3.1 ("Discover Journeys — Candidate List & Detail Panel") in Epic 3, which now delivers FR-23 inline rather than as a standalone explorer screen. Original AC retained below for history only.

As a QA Director or Engineering Leader,
I want to open any approved Journey and see the exact screens, actions, and API calls that back it,
So that I can trust the map traces back to real, observed behavior.

**Acceptance Criteria (superseded):**

**Given** an approved Journey
**When** the user selects it in the Journey Explorer
**Then** the specific pages, actions, and API calls captured for it during discovery are shown (FR-23)

### Story 6.3: Coverage Analytics `[DEFERRED POST-V1]`

As an Engineering Leader,
I want to see which approved Journeys have a generated Test Asset and which don't,
So that I know what's covered before a release.

**Acceptance Criteria:**

**Given** an Application with approved Journeys, some with and some without a current Test Asset
**When** the user views coverage analytics
**Then** each Journey shows whether a `current=true` Test Asset exists for it — never a live pass/fail status from the customer's CI, since the platform has no read-back channel from it (FR-24)

### Story 6.4: Multi-Application Executive Dashboard `[DEFERRED POST-V1]`

As an Engineering Leader,
I want a single dashboard rolling up Capability, coverage, and Journey views across all my Applications,
So that I can make a release decision backed by evidence rather than a gut call.

**Acceptance Criteria:**

**Given** an Organization with one or more onboarded Applications
**When** the user opens Dashboard
**Then** KPI tiles and a hero-stat strip show portfolio-level counts (approved Journeys, Test Assets generated, Applications onboarded), with tabular-nums formatting and at most one number accent-colored as the item most deserving attention
**And** an Application row with at least one approved Journey lacking a generated Test Asset shows an inline warning flag (e.g., "N pending test") next to its coverage figures (FR-25)
**And** the Dashboard screen omits the top-bar Application-name breadcrumb, since it is inherently cross-Application

## Epic 7: Deployment & AI Provider Configuration `[DEFERRED POST-V1 — 2026-07-15]`

**Deferred out of V1 scope as of 2026-07-15** — Settings, the only confirmed UI entry point for Story 7.1, is cut from the current reference prototype's IA. Flagged explicitly (not silently folded into the general deferral pattern) because FR-26/27 are compliance/data-residency NFRs, not a convenience dashboard — reconfirm with product ownership before treating the underlying on-prem/data-locality *requirement* (not just its UI) as deferred, especially if any on-prem commitment has already been made externally. See `sprint-change-proposal-2026-07-15.md`.

An organization can run hosted SaaS or configure the platform to use its own AI provider endpoint/keys for on-prem, in-network processing.

### Story 7.1: Configure AI Provider Mode `[DEFERRED POST-V1 — no confirmed UI home]`

As an organization administrator,
I want to switch the platform between hosted AI processing and my own AI provider endpoint/keys,
So that I can meet my organization's data-residency requirements.

**Acceptance Criteria:**

**Given** an administrator on the Settings screen
**When** they toggle AI-provider mode between hosted and customer-supplied
**Then** the setting is saved per Organization, and all subsequent AI calls resolve through the existing `AIProvider` port — no Inference or Generation Activity code changes when the mode changes (FR-26, FR-27, AD-3)
**And** the toggle behaves as an immediate on/off setting, with no confirmation step, using the standard toggle-switch component

### Story 7.2: Enforce In-Network AI Processing for On-Prem Mode `[DEFERRED POST-V1 — depends on 7.1]`

As an organization running on-prem,
I want every AI/LLM call to stay inside my network when customer-supplied mode is active,
So that no customer data or AI processing leaves my network.

**Acceptance Criteria:**

**Given** an Organization configured for customer-supplied AI provider mode
**When** any Inference, Scenario Generation, or Playwright Generation Activity runs
**Then** it resolves the `AIProvider` port to the customer-endpoint implementation exclusively — no call is routed to the hosted vendor endpoint (FR-27, NFR-3)
**And** this holds regardless of the deferred SaaS/on-prem infrastructure topology decision — the enforcement is at the port-selection level, not the deployment-infra level
