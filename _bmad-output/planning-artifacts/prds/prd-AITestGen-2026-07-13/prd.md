---
title: "Application Intelligence Platform — V1 PRD"
status: final
created: 2026-07-13
updated: 2026-07-15
---

# PRD: Application Intelligence Platform (V1)
*Working title — confirm.*

## 0. Document Purpose

This PRD scopes **V1** of the Application Intelligence Platform for engineering, design, and QA stakeholders building and validating the first release. It builds on the approved [Product Brief](../../briefs/brief-AITestGen-2026-07-12/brief.md) — this PRD does not restate the market/competitive rationale in full; deeper competitive positioning, the V2/V3 vision arc, and rejected-alternative reasoning live in `addendum.md` alongside this document. Functional Requirements are grouped by feature and numbered globally (FR-1 … FR-N) for stable downstream reference. Inline `[ASSUMPTION]` tags mark inferences made during drafting that need explicit confirmation; §9 indexes any that remain open, plus `[NOTE FOR PM]` callouts flagging deliberate deviations from the approved brief. As of this draft, all inline assumptions raised during discovery have been resolved into explicit decisions — §9 currently holds disclosure notes, not open assumptions.

**This PRD deliberately deviates from the approved brief in four places** — all flagged inline with `[NOTE FOR PM]` and indexed in §9: cutting all AI confidence/risk scoring (§5), cutting the reviewer's "merge duplicates" action (§4.4 FR-13), cutting reviewer prioritization/importance-marking (§5), and cutting CI/CD delivery of any kind, automated or manual (§5, removed 2026-07-15 — originally a manual-process compromise, now removed in full). None are silent — each needs explicit sign-off from whoever owns the brief before this PRD is treated as final.

## 1. Vision

The Application Intelligence Platform turns a running web application into a business-language map of what it actually does — discovered automatically, confirmed by a human, and converted into running regression coverage. Where existing test-automation tools execute journeys someone already told them about, V1 answers the prior question: *what are all the business journeys this application supports, right now, as built?*

Given only a URL and dedicated test credentials — no source code or repository access — V1 explores a non-production instance of a customer's application the way a thorough tester would, infers candidate business capabilities and journeys from what it observes, and immediately compiles every discovered Journey into generated integration test scenarios and executable Playwright tests — there is no approval gate between discovery and generation. `[RESOLVED 2026-07-15]` A human reviewer (typically a QA Director or Engineering Leader) curates the result afterward: renaming what's mislabeled and deleting what doesn't belong (§4.4) — V1's curation toolset doesn't support merging, splitting, or editing what makes up a Journey. Deleting a Journey excludes it, and anything already generated for it, from downstream compilation. A per-Journey detail view lets a reviewer inspect the screens, actions, and API calls behind any candidate. `[NOTE FOR PM — 2026-07-15]` The Capability Map, coverage analytics, multi-application executive dashboard, and CI/CD delivery views described in earlier planning are **deferred post-V1** as of this revision — see §6, §9, and `sprint-change-proposal-2026-07-15.md` for the full rationale.

V1 does not claim technical discovery superiority (see brief's *What Makes This Different*); it wins pilots on the strength of the business-journey framing, a fast time-to-coverage with retroactive human curation rather than an approval bottleneck, and a credible roadmap. `[NOTE FOR PM — 2026-07-15]` This is a deliberate repositioning from "human-in-the-loop trust gate" (the original brief's framing) to "immediate generation, human curates after" — see §9 and §12 Risk item 2 for the tradeoff this accepts. The deeper technical moat — source-code correlation and change-impact prediction — arrives in V2 and V3.

## 2. Target User

### 2.1 Jobs To Be Done

- **Engineering Leader** (economic buyer): "I need to walk into a release conversation and say, with evidence, what could break and what's covered — not just hope nothing does."
- **QA Director** (primary daily user, champion): "I need a trustworthy, living map of this application's journeys and a running test suite I didn't have to author from scratch — and the authority to correct what the AI got wrong."
- **Secondary (real users, not V1 design targets):** CTO (portfolio-level visibility), Product Owner (factual inventory vs. spec), Architect (structural/dependency understanding, grows in relevance at V2), Test Teams (live with the generated suite day to day).

V1 is built and sold around the **Engineering Leader + QA Director** relationship first; the other three are real users but not the primary design target for this release.

### 2.2 Non-Users (V1)

- Teams building **mobile or native** applications — V1's discovery approach is web-only.
- Teams that cannot provide a **non-production environment** and **dedicated test credentials** — this is a hard onboarding precondition, not a nice-to-have.
- Teams that cannot provide **either** a standard username/password login **or** a reusable authenticated session state for SSO/MFA-protected apps (FR-3) — V1 does not implement SAML/OAuth/OIDC handshakes or MFA-code retrieval itself.

### 2.3 Key User Journeys

- **UJ-1. Maria reviews her application's first discovered map.** `[UPDATED 2026-07-15]` Approve/Reject no longer exist as steps in this journey — see §4.4 and `sprint-change-proposal-2026-07-15.md`.
  - **Persona + context:** Maria, a QA Director at a mid-size insurer, has just had V1 finish its first discovery run against the claims-processing staging environment. Scenario and Playwright generation has already started for every discovered Journey — she isn't gating that, she's curating it.
  - **Entry state:** Authenticated in the platform, viewing the Discover Journeys screen for the first time for this application.
  - **Path:** She sees a list of candidate Journeys — "Claims Approval," "Policy Issuance," a few oddly-split duplicates. She renames one the AI labeled generically, and deletes two low-value duplicates (excluding them, and whatever was already generated for them, from downstream compilation). She leaves the rest as-is — there's nothing to individually approve; at this application's scale, requiring a decision on every one of dozens or hundreds of candidates isn't realistic.
  - **Climax:** She moves on to Review Scenarios, where generated test scenarios for every Journey she didn't delete are already waiting.
  - **Resolution:** `[UPDATED 2026-07-15]` She continues to Generate Suite, where the curated set of Journeys' generated tests are compiled into a named suite she can show her Engineering Leader — there is no Capability Map to open (removed, no supporting screen in current UX).
  - *(Edge case removed 2026-07-15: "discovery hits its time budget mid-application" no longer applies — FR-5 is removed, and FR-7's only stop condition is now exhaustive traversal.)*

*(UJ-2 "Devon checks release readiness before a Friday deploy" removed in full 2026-07-15 — it depended entirely on the multi-application executive dashboard, which has no supporting screen in the current UX and is removed from scope. See `sprint-change-proposal-2026-07-15.md` for the original history.)*

## 3. Glossary
*"Capability" and "Journey" are used as shorthand for "Business Capability" and "Business Journey" throughout the rest of this document.*

- **Application** — A single running web application onboarded for discovery. A customer may onboard multiple Applications from V1 launch.
- **Discovery Run** — One execution of the Runtime Discovery engine against an Application. `[UPDATED 2026-07-15]` Always covers the full Application, with no configurable scope or time-budget cap (both removed) — bounded only by exhaustive traversal.
- **Business Capability** — A named, business-language grouping of related functionality the AI infers from discovery signals (e.g., "Claims Processing").
- **Business Journey** — A named, business-language sequence of pages/actions/API calls representing an end-to-end user workflow (e.g., "Claims Approval"), nested under a Capability.
- **Trusted Knowledge Model** — `[REDEFINED 2026-07-15]` The set of Capabilities and Journeys that have been discovered and not deleted by a human reviewer; these feed Scenario Generation and Analytics automatically upon discovery. No longer "human-approved" — see §4.4 and `sprint-change-proposal-2026-07-15.md`.
- **Scenario** — A generated integration test scenario (happy-path or negative/edge-case) derived from a discovered Journey.
- **Test Asset** — An executable Playwright test generated from a Scenario.
- **Dedicated Test Account** — Customer-provisioned credentials used solely for discovery, distinct from a real end-user identity.
- **Non-Production Environment** — A staging/UAT/test instance of the Application, as distinct from the live production system. V1 must never run discovery against a production-facing environment.

## 4. Features

### 4.1 Application Onboarding & Connection

**Description:** The entry point to the platform — a customer connects an Application by supplying its URL, environment designation, access credentials, and discovery configuration. This is the entirety of V1 setup: no repository access, no agents to install.

**Functional Requirements:**

#### FR-1: Application onboarding
User can onboard an Application by providing its URL, environment designation, and access credentials.

**Consequences (testable):**
- An Application record is created and available for Discovery Run configuration once these three fields are supplied.

#### FR-2: Dedicated credentials only
Access credentials must correspond to a Dedicated Test Account provisioned by the customer, not a real end-user identity.

#### FR-3: Authentication via storage-state reuse
Platform establishes a session prior to discovery either by (a) performing a standard/manual username-password login flow itself, or (b) reusing a pre-authenticated session (storage state: cookies, localStorage, sessionStorage) supplied by the customer for SSO/MFA-protected Applications. In case (b), the customer authenticates once through their own SSO/MFA flow — ideally using a Dedicated Test Account with MFA exempted/disabled at the identity-provider level — and hands the platform the resulting session state to reuse across Discovery Runs.

**Consequences (testable):**
- Platform never implements a SAML/OAuth/OIDC handshake or MFA-code retrieval itself in V1.
- A Discovery Run that finds its session has expired (redirected to login) fails gracefully and surfaces a re-authentication prompt rather than silently producing an empty/partial map.

*(FR-4 "Configurable discovery scope" and FR-5 "Discovery time budget" removed in full 2026-07-15 — no supporting fields exist anywhere in the current Connect App form, and product confirmed this isn't a UI gap but a removed concept entirely: Discovery Runs always cover the full Application, with no configurable time-budget safety cap. See §9 for the accepted-risk tradeoff this creates.)*

**Notes:** Onboarding does not technically verify that the target is a Non-Production Environment — see §11 Constraints and Guardrails.

### 4.2 Runtime Discovery

**Description:** The exploration engine — navigates the Application the way a thorough tester would, capturing everything it encounters as raw signal for the intelligence layer.

**Functional Requirements:**

#### FR-6: Autonomous exploration
Platform autonomously navigates pages, exercises UI actions and forms, and invokes APIs across the entire Application, capturing pages, navigation paths, actions, forms, API calls, and state transitions. `[UPDATED 2026-07-15]` No configurable scope restriction exists (FR-4 removed) — always the full Application.

#### FR-7: Discovery stop conditions
`[UPDATED 2026-07-15]` A Discovery Run terminates when no new pages, actions, or state transitions are found (exhaustive traversal). There is no time-budget stop condition (FR-5 removed) — a Discovery Run has no safety cap against unbounded exploration (e.g., infinite pagination or calendar "next" links); see §12 Risk Register for this accepted tradeoff.

### 4.3 Journey & Capability Intelligence

**Description:** The AI layer that turns raw discovery signal into business understanding — the core of what makes this a "map," not a crawl log.

**Functional Requirements:**

#### FR-8: AI journey/capability inference
Platform uses AI to transform captured discovery signals into candidate Business Capabilities and Journeys expressed in business language, not raw technical labels (e.g., page/route names).

**Consequences (testable):**
- Every candidate Journey presented in the Review queue (FR-9) has a business-language name, not a raw route/page identifier.
- Every candidate Journey is associated with the specific pages, actions, and API calls (captured per FR-6) that produced it, so a reviewer can trace the inference back to raw evidence.

**Notes:** No AI-generated confidence or risk score is attached to candidates in V1 — see §5 Non-Goals and §9 for the reasoning behind this cut.

### 4.4 Human Curation `[RENAMED 2026-07-15, was "Human Review & Approval"]`

**Description:** `[REWRITTEN 2026-07-15]` AI-inferred Journeys are compiled into generated test coverage immediately, with no approval gate — at the scale a single Application's discovery run can produce (dozens to hundreds of candidates), requiring a human decision on every one before anything downstream can happen isn't realistic. Instead, a human reviewer curates the result: renaming what's mislabeled and deleting what doesn't belong. Deletion is retroactive — it excludes a Journey, and anything already generated for it, from downstream compilation, rather than gating that generation from happening in the first place. See §9 and `sprint-change-proposal-2026-07-15.md` for the full rationale and the tradeoff this accepts (§12 Risk item 2).

**Functional Requirements:**

#### FR-9: Discover Journeys screen
Discovered Journeys and Capabilities are presented to a human reviewer for curation (rename, delete). Presentation is not a gate — a Journey is already part of the Trusted Knowledge Model and feeding Scenario Generation (FR-14) before a reviewer ever looks at it.

#### FR-10: Approve `[CUT 2026-07-15]`
Previously: reviewer can approve a discovered Journey/Capability, adding it to the Trusted Knowledge Model. Cut because there is no gate to approve past — every discovered Journey is in the Trusted Knowledge Model immediately (FR-14). Retained here, per this document's convention, as a record of intent rather than silently deleted.

#### FR-11: Reject `[CUT 2026-07-15]`
Previously: reviewer can reject a discovered Journey/Capability, excluding it from the Trusted Knowledge Model. Cut as redundant with Delete (FR-13), which is now the sole exclusion mechanism. Retained here as a record of intent.

#### FR-12: Rename
Reviewer can rename a discovered Journey/Capability.

#### FR-13: Delete
Reviewer can delete a discovered Journey/Capability. `[UPDATED 2026-07-15]` This is now the only way a Journey/Capability is excluded from the Trusted Knowledge Model — deleting one also excludes any Scenarios/Test Assets already generated for it from Generate Suite compilation and Analytics (§4.5, §4.7), though it does not retroactively cancel a `GenerationWorkflow` already running/completed (consistent with how regeneration, FR-18, is the only way to redo generation for a kept Journey).

**Out of Scope:** `[NON-GOAL for MVP]` Merging two discovered Journeys, splitting one into two, or editing a discovered Journey are not supported in V1. The brief's Solution narrative describes a reviewer who "merges duplicates" — that specific capability is cut for V1 to keep the review workflow free of composition-combining actions; a reviewer facing duplicate Journeys must instead delete the redundant one(s) rather than merge or edit them.

#### FR-28: Edit a discovered Journey `[CUT 2026-07-15]`
Briefly added 2026-07-15 per the UX ripple proposal (reviewer edits a Journey via a per-row action menu), then cut the same day once it became clear the exact edit surface (name/description vs. constituent steps) was never confirmed in the UX review and product decided not to build it. Retained here, per this document's convention, as a record of intent rather than silently deleted.

#### FR-14: Discovery gates downstream use `[REWRITTEN 2026-07-15, was "Approval gates downstream use"]`
Every discovered, non-deleted Journey/Capability automatically enters the Trusted Knowledge Model and feeds Scenario Generation and Analytics (§4.5, §4.7) immediately upon discovery — deletion (FR-13) is the only exclusion mechanism. There is no separate approval step.

#### FR-15: New-journey flagging on re-discovery
Re-running discovery on a previously discovered Application flags only newly-discovered Journeys/Capabilities (not seen in a prior run) for human review; already-known Journeys are not automatically re-surfaced. This is a simple **existence check** (does this Journey's identity already exist in the Trusted Knowledge Model?) — a materially smaller capability than detecting *what changed* inside an existing Journey.

**Out of Scope:** V1 cannot detect that a previously-discovered Journey's underlying runtime behavior has changed — only that a Journey it has never seen before now exists. See §5 Non-Goals.

### 4.5 Scenario & Test Generation

**Description:** Converts a discovered Journey into executable regression coverage immediately upon discovery — the day-one deliverable that makes the map actionable, not just informative.

**Functional Requirements:**

#### FR-16: Scenario generation
Platform generates integration test Scenarios for each discovered Journey, covering both happy-path and negative/edge-case scenarios. `[UPDATED 2026-07-15]` Generation starts immediately upon discovery (FR-14), not gated on human approval.

#### FR-17: Playwright generation
Platform converts generated Scenarios into executable Playwright Test Assets.

#### FR-18: Full regeneration on request
When a customer triggers regeneration of Test Assets for a Journey, platform regenerates Scenarios and Test Assets from scratch. `[UPDATED 2026-07-15]` Since generation is no longer gated on approval (§4.4), regeneration is the only way to redo generation for a Journey the reviewer has kept; individual Scenarios can additionally be edited/removed pre-generation as of 2026-07-15 — see FR-29.

**Out of Scope:** V1 has no capability to detect *what* changed in a Journey and regenerate incrementally — regeneration is always full, not a diff/patch. See §5 Non-Goals.

#### FR-29: Edit or remove an individual Scenario `[ADDED 2026-07-15]`
Reviewer can rename, edit, or remove a generated Scenario before Playwright generation, via a per-row action menu on the scenario review screen.

**Notes:** `[GAP]` Whether an edited Scenario's test data/steps actually feed Playwright generation, or the edit is display-only, is unconfirmed against the current reference prototype. Needs a follow-up UX/engineering pass before implementation.

*(§4.6 "CI/CD Delivery" [FR-19–21] and §4.8 "Deployment" [FR-26/27] removed in full 2026-07-15 — no supporting screen exists in the current reference prototype's IA for either, and on-prem deployment is confirmed parked for a later release. See `sprint-change-proposal-2026-07-15.md` for the original history.)*

### 4.7 Analytics `[TRIMMED 2026-07-15, was "Analytics & Dashboards"]`

**Description:** The view that makes a discovered Journey's evidence legible to a reviewer. `[REMOVED 2026-07-15]` Capability Map (FR-22), coverage analytics (FR-24), and the multi-application executive dashboard (FR-25) are removed in full — no screen in the current reference prototype's IA serves any of them, and UJ-2 (§2.3, the journey they served) is removed alongside.

**Functional Requirements:**

#### FR-23: Journey Explorer `[RETAINED, RELOCATED]`
Platform provides Journey-explorer detail — a view of a Journey's screens, actions, and API calls. As of 2026-07-15 this is satisfied inline: selecting a candidate on the discovery-review screen loads its step-by-step detail (route, method, stage) in a detail panel, rather than via a standalone explorer screen.

**Consequences (testable):**
- Selecting any candidate Journey shows the specific pages, actions, and API calls captured for it during discovery (FR-6).

## 5. Non-Goals (Explicit)

- **No merging, splitting, or editing of Journeys** — the brief named merging duplicates as a V1 outcome; V1 doesn't support combining two Journeys into one, splitting one into two, or editing one (FR-28, added then cut same day 2026-07-15 — see §4.4). A reviewer facing duplicates deletes the redundant one(s).
- **No source code or repository read access** for discovery, and nothing that depends on it (route/component/permission/feature-flag structure, dependency mapping, code-to-journey traceability). That's V2.
- **No change intelligence** — predicting which Journeys/tests a specific *code* change affects. That's V3.
- **No AI confidence or risk scoring of any kind** — neither a per-Journey discovery confidence score nor a risk/confidence scorecard. Cut during PRD discovery: meaningful usage/error-rate signals require a real telemetry feed V1 doesn't have, and the unresolved questions weren't worth V1's complexity budget. `[NOTE FOR PM: the approved brief named risk/confidence scoring as a V1 outcome — this is a deliberate scope deviation, see §9 and memlog.]`
- **No runtime drift/change detection** on previously-discovered Journeys — V1 cannot tell what changed inside a Journey, only regenerate it from scratch on request.
- **No CI/CD delivery of any kind** — `[UPDATED 2026-07-15]` V1 originally planned manual/template-based pipeline wiring as a compromise on "automated"; as of 2026-07-15 CI/CD delivery (automated or manual) is removed in full, not merely simplified — no supporting screen exists in the current UX. See §9.
- **No native SSO/SAML/OAuth/OIDC protocol implementation or automated MFA-code retrieval** — V1 handles SSO/MFA-protected apps only via customer-supplied reusable session state (FR-3), not by performing the identity-provider handshake itself.
- **No claim of superior discovery technology** in product messaging — V1's differentiation is the business-journey framing and fast time-to-coverage with retroactive curation, not a proprietary discovery algorithm (per brief). `[UPDATED 2026-07-15]` No longer "human-in-the-loop trust model" — see §1 Vision and §12 Risk item 2 for the repositioning.
- **No non-web applications** — mobile/native apps are not addressed by V1.
- **No test frameworks other than Playwright.**
- **No numeric coverage or time-saved targets** — deliberately undefined until real pilot data exists (per brief).
- **No system-enforced non-production safeguard** — determining and declaring a Non-Production target is entirely the customer's responsibility in V1; the platform does not technically verify or block discovery against production.
- **No reviewer prioritization/importance-marking** — the brief's Solution narrative describes a reviewer who "marks what matters most to the business" when reviewing discovered Journeys. V1's curation toolset (FR-12–FR-13) has no way to flag business importance; every discovered Journey is treated equally. `[NOTE FOR PM: this gap is also why §12 Risk item 3 (no reviewer triage aid) exists — the two are the same underlying capability the brief implied but V1 doesn't build.]`

## 6. MVP Scope

*Revised 2026-07-15 — see `sprint-change-proposal-2026-07-15.md` for the full rationale behind this narrowing.*

### 6.1 In Scope
- Application onboarding via a single connect form: URL + Dedicated Test Account credentials, environment, authentication method (FR-1–FR-3). `[UPDATED 2026-07-15]` FR-4/FR-5 (discovery scope, time budget) confirmed removed, not a UI gap — no fields for either exist or are planned.
- Runtime discovery, always full-Application, exhaustive-traversal only — no configurable scope, no time-budget safety cap (FR-6–FR-7, updated 2026-07-15).
- AI-driven Journey/Capability inference (FR-8), with per-candidate step/evidence detail shown inline (FR-23).
- Human curation: rename/delete workflow (FR-9, FR-12, FR-13, FR-15). `[UPDATED 2026-07-15]` FR-10/FR-11 (approve/reject) and FR-28 (edit) cut — generation is no longer gated on review; deletion is the sole exclusion mechanism.
- Scenario generation (happy-path + negative), with per-scenario rename/**edit**/remove (FR-16, FR-18, FR-29), and Playwright test generation (FR-17) surfaced via a named Test Suite generation step. Generation starts immediately per discovered Journey, not on approval.

### 6.2 Removed From Scope (2026-07-15)
`[UPDATED 2026-07-15]` These moved from "moved out of MVP, deferred" to "removed in full" the same day, once it was confirmed none has any path back without a fresh product/UX decision:
- CI/CD delivery via PR or direct commit, provider support, and manual pipeline-wiring instructions (previously FR-19–21) — no supporting screen in current UX.
- Capability Map, coverage analytics, multi-application executive dashboard (previously FR-22/24/25) — no supporting screen in current UX. (Journey Explorer, previously FR-23's Epic 6 sibling, is unaffected — retained and relocated, see §4.7.)
- UJ-2 (Devon's release-readiness journey, §2.3) — depended entirely on the removed executive dashboard.
- Two deployment models / on-prem data locality (previously FR-26/27) — Settings, the only UI entry point, is cut; **this one is a deliberate parked-for-later-release product decision**, not merely an orphaned/unsupported item like the rest of this list — worth revisiting on its own timeline rather than treating as dead.

### 6.3 Out of Scope for MVP
See §5 Non-Goals — all items there apply to MVP scope directly, in addition to §6.2's deferrals above.

## 7. Success Metrics

Per the approved brief, V1 business success is **not** a customer-count or revenue target — it's proving the core thesis (runtime discovery → journey mapping → generated tests) holds up in real pilots well enough to justify building V2. No numeric coverage or time-saved target is set for V1 by design; inventing one now would be a fabricated claim rather than a real criterion.

**Directional signals (qualitative, tracked per pilot):**
- **SM-1**: An Engineering Leader or QA Director who, having tried V1, keeps using it into a second and third release cycle without being asked to. Validates FR-9, FR-12–FR-18, FR-23 (the full curation-to-generation loop delivering ongoing value). `[UPDATED 2026-07-15]` No longer "review-to-dashboard" — the dashboard is removed.
- **SM-2**: Discovered Journeys need light correction rather than heavy rework during human review — a proxy for discovery accuracy. Validates FR-8, FR-9, FR-12, FR-13.
- **SM-3**: Generated Test Assets a QA team trusts enough to fold into their real regression process, not treat as a novelty. Validates FR-16–FR-18. `[UPDATED 2026-07-15]` No longer references FR-19–21 (CI/CD delivery, removed) — "fold into their real regression process" now means the customer does that manually, entirely outside V1.

**Counter-metrics (do not optimize)**
- **SM-C1**: `[UPDATED 2026-07-15]` Journey retention rate (candidates not deleted) should not be optimized by inflating Journey granularity or over-splitting Capabilities to look more thorough — that would game SM-2 without reflecting real discovery quality.

## 8. Open Questions

1. **Time-to-first-map validation.** "Hours, not days or weeks" is the internal target — not yet validated against real-world application complexity. Confirm before this appears in any external-facing claim. *(from brief)*
2. **V2 greenlight threshold.** What counts as V1 having "proven the thesis enough" to justify building V2 — number of design partners, retention through a full release cycle, something else? *(from brief)*
3. Should V1 add a technical safeguard against accidentally running discovery against a production environment, beyond customer responsibility — given how severe that failure mode is (live side effects on a production system)?
4. What are the hosted SaaS data residency/retention specifics?
5. Is cutting all confidence/risk scoring the right long-term call, or should a lightweight, discovery-signal-only version (no external feed required) be reconsidered before V1 ships? *(Reaffirmed as fully cut during Finalize review, after confirming 2 of the brief's 4 scorecard inputs — complexity, coverage-gap — don't strictly need a telemetry feed. Kept simple by explicit decision; see `addendum.md` for how to reintroduce cheaply later.)*
6. `[MOOT 2026-07-15]` Previously: what happens when a direct-commit regeneration overwrites a customer's manually-edited test file? Moot — direct-commit export (previously FR-19) is removed; there is no delivery mechanism to overwrite anything with. Would need to be re-asked if CI/CD delivery is ever redesigned.
7. What page/action volume must V1 handle for a "typical" enterprise pilot application — is there a performance/scale ceiling to design against?
8. For SSO/MFA-protected apps (FR-3), how does the customer actually capture and hand off the reusable session state — a manual export process, a small helper tool the platform provides, or something else? Mechanism isn't yet specified; deliberately deferred to engineering during technical design rather than resolved in this PRD. **Deferred with a condition, not ignored:** this must be resolved before UX/architecture work on the Application Onboarding flow (§4.1) proceeds — the onboarding screen design and any helper-tool UX depend directly on the answer.

## 9. Assumptions Index

- **§4.1 Notes / §11**: The non-production-only rule is enforced entirely by customer responsibility, not by the platform, in V1. (Confirmed decision, not an open assumption — flagged here because it's a real residual risk; see §12 item 1.)
- **§5 [NOTE FOR PM]**: Removing all confidence/risk scoring is a deliberate deviation from the approved brief's stated V1 outcomes — flagged for explicit sign-off, not a quiet scope cut.
- **§4.4 FR-13 [NON-GOAL for MVP]**: The brief's "merges duplicates" reviewer action is cut for V1 — reviewers delete redundant Journeys instead of merging them.
- **§5 [NOTE FOR PM]**: The brief's "marks what matters most to the business" reviewer capability has no V1 equivalent — every discovered Journey is treated with equal weight.
- **[NOTE FOR PM]**: The brief commits to tests running "automatically as part of standard regression" once delivered. V1's original plan (manual pipeline-wiring, previously §4.6/FR-21) was already a deviation from that; as of 2026-07-15 CI/CD delivery is removed in full, a larger deviation still — the customer must integrate generated tests into their regression process entirely outside the platform.

*(SSO/MFA handling and Scenario-editing granularity were open assumptions in an earlier draft; both are now resolved decisions — see FR-3 and FR-18.)*

- **2026-07-15 [Sprint Change Proposal]**: A new reference prototype triggered a confirmed, user-directed MVP narrowing — full detail in `sprint-change-proposal-2026-07-15.md`. Summary: FR-19–FR-22, FR-24–FR-27 moved to deferred post-V1; UJ-2 deferred alongside FR-25; FR-13's Out-of-Scope note narrowed (editing now allowed) and FR-28/FR-29 added for Journey/Scenario edit; FR-23 retained but relocated from a standalone Journey Explorer screen into the discovery-review flow. `DESIGN.md`/`EXPERIENCE.md` (both updated 2026-07-15) are the source of truth for the new IA this revision aligns to.
- **2026-07-15 [Follow-up]**: FR-26/27 (on-prem deployment) confirmed parked for a later release — not a compliance-NFR item awaiting separate sign-off. §4.8 and §6.2 updated to remove the "confirm before final" flag accordingly.
- **2026-07-15 [Follow-up]**: FR-28 (Edit a Journey, added earlier the same day) cut — its exact editable surface was never confirmed in the UX review, and product decided not to build it. §4.4, §5, §6.1 updated.
- **2026-07-15 [Follow-up]**: FR-10 (Approve) and FR-11 (Reject) cut, and FR-14 rewritten — every discovered, non-deleted Journey/Capability now enters the Trusted Knowledge Model and starts generation immediately, with no human approval gate. Rationale: per-item approval doesn't scale to a real discovery run's candidate volume (dozens to hundreds per Application); a reviewer's only lever is now retroactive deletion (FR-13). This matches `EXPERIENCE.md`'s own Flow-1 walkthrough, which already showed the reviewer renaming/removing candidates and continuing to Review Scenarios without ever depicting an approve/reject click — the PRD text had simply never caught up to that flow. Accepted tradeoff: §12 Risk item 2's mitigation is weaker as a result (see that entry). §1 Vision, §3 Glossary, §4.4, §4.5 FR-16/18, §5, §6.1, UJ-1 all updated; Architecture AD-1/AD-7/AD-9 and Epic 2/3/4 updated to match.
- **2026-07-15 [Final follow-up]**: FR-19–22 and FR-24–27 removed in full (not merely deferred) — confirmed none has any supporting screen in the current UX, and on-prem deployment (FR-26/27) is additionally a deliberate parked-for-later-release decision. §4.6 and §4.8 deleted; §4.7 trimmed to FR-23 only; UJ-2 removed; §5, §6.2, §8 (Open Question 6), §10, §12 (Risk item 4), §13 updated to match. Epics 5, 6 (partially), and 7 removed from `epics.md`; Stories 3.2, 3.3, 5.1-5.3, 6.1 files deleted; Architecture Module Map/Deferred section updated to match.
- **2026-07-15 [Cleanup follow-up]**: FR-4 (discovery scope) and FR-5 (time budget) removed in full — the earlier `[GAP]` note treating their missing UI as unconfirmed was resolved: the whole concept is gone, not just the config fields. FR-6 always covers the full Application; FR-7's only stop condition is exhaustive traversal, with no time-budget branch. This is an accepted-risk tradeoff (§12 Risk item 7, new) — Discovery Runs have no safety cap against unbounded exploration. §1 UJ-1, §3 Glossary, §6.1, §10 updated to match; Story 1.5 removed in full; Story 2.3 ("Discovery Stop Conditions & Completeness Status") simplified to drop the `incomplete` status entirely; Architecture AD-10/AD-11 updated to match.

## 10. Cross-Cutting NFRs

- **Security**: Standard enterprise-grade secret handling for stored discovery credentials (encryption at rest and in transit, least-privilege service accounts). No bespoke certification requirement specified for V1.
- **Reliability**: `[UPDATED 2026-07-15]` A Discovery Run must complete (exhaustive traversal) or fail gracefully (e.g., session expiry) — there is no time-budget timeout state, since no time budget exists (FR-5 removed).
- *(NFR-3 "Data locality (on-prem)" removed 2026-07-15 — tied to FR-27, removed alongside on-prem deployment being parked for a later release. See §6.2.)*

## 11. Constraints and Guardrails

**Safety**
- V1 must never be run against a customer's production-facing environment. In V1, this is a **customer responsibility**, not a platform-enforced constraint. See §12 Risk Register item 1 for exposure and mitigation status.

**Privacy**
- Discovery credentials must be a Dedicated Test Account, never a real end-user identity (FR-2). Standard enterprise-grade secret handling applies (§10).

## 12. Risk and Mitigations

1. **Risk**: Discovery engine triggers real side effects (payments, emails, data changes) if accidentally pointed at a production environment. **Mitigation**: Customer contractually/operationally designates a Non-Production target; prominently documented at onboarding. **Unresolved**: whether V1 needs a technical safeguard (Open Question 3).
2. **Risk**: AI misclassifies or over-fragments Business Journeys, eroding trust in the map. `[UPDATED 2026-07-15]` **Mitigation**: Weakened as of this revision — there is no longer a mandatory approval gate before a Journey enters the Trusted Knowledge Model and generates coverage (FR-9–FR-14); a reviewer's only lever is retroactive deletion. This means a misclassified or over-fragmented Journey may already have consumed AI-generation cost, and produced a Scenario/Test Asset, before a human ever sees it — the risk isn't eliminated, it's shifted from "bad output never gets generated" to "bad output gets deleted after the fact." Accepted tradeoff, made explicitly because per-item approval doesn't scale to a discovery run's realistic candidate volume (dozens to hundreds per Application) — see §1 Vision and `sprint-change-proposal-2026-07-15.md`.
3. **Risk**: Without any AI confidence signal, reviewers triaging a large discovery output have no prioritization aid, which could slow review at scale. **Mitigation**: None built into V1 — flagged for revisit if pilot feedback shows this is a real bottleneck (Open Question 5).
4. `[MOOT 2026-07-15]` Previously: full-regeneration-on-request combined with direct-commit export could silently overwrite a customer's manually-edited test file. Moot — direct-commit export (previously FR-19) is removed; there is no delivery mechanism to carry this risk. Would need to be re-assessed if CI/CD delivery is ever redesigned.
5. **Risk**: V1 has no differentiated technical moat (per brief); pilots may be won or lost on roadmap credibility rather than delivered capability. **Mitigation**: Sales motion leans on an honest, credible V2/V3 roadmap story — see `addendum.md`.
6. **Risk**: `FR-6`'s autonomous form/API exercising has no destructive-action guardrail — even in a Non-Production environment, the discovery engine could trigger irreversible side effects (real emails sent, shared test data deleted, fraud-detection tripwires) if that environment isn't fully isolated from real-world systems. **Mitigation**: **Accepted risk** — V1 relies entirely on the customer providing a properly isolated Non-Production environment (§11); no platform-side guardrail is built in V1, by explicit decision.
7. **`[NEW 2026-07-15]` Risk**: A Discovery Run has no time-budget safety cap (FR-5 removed) — an Application with infinite pagination, calendar "next" links, or another unbounded-traversal pattern could cause a Discovery Run to run indefinitely, consuming AI-generation cost and compute with no automatic stop other than genuine exhaustion. **Mitigation**: **Accepted risk**, by explicit product decision — no time-budget cap or other platform-side runaway-discovery guardrail is built in V1.

## 13. Integration and Dependencies

- *(CI/CD providers integration removed 2026-07-15 — CI/CD delivery is out of scope; see §6.2.)*
- **AI/LLM provider**: Hosted SaaS mode uses vendor-hosted AI processing. `[UPDATED 2026-07-15]` On-prem mode (previously FR-27) is removed — parked for a later release, see §6.2.
