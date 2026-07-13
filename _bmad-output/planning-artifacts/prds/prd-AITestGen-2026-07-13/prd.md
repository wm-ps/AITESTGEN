---
title: "Application Intelligence Platform — V1 PRD"
status: final
created: 2026-07-13
updated: 2026-07-13
---

# PRD: Application Intelligence Platform (V1)
*Working title — confirm.*

## 0. Document Purpose

This PRD scopes **V1** of the Application Intelligence Platform for engineering, design, and QA stakeholders building and validating the first release. It builds on the approved [Product Brief](../../briefs/brief-AITestGen-2026-07-12/brief.md) — this PRD does not restate the market/competitive rationale in full; deeper competitive positioning, the V2/V3 vision arc, and rejected-alternative reasoning live in `addendum.md` alongside this document. Functional Requirements are grouped by feature and numbered globally (FR-1 … FR-N) for stable downstream reference. Inline `[ASSUMPTION]` tags mark inferences made during drafting that need explicit confirmation; §9 indexes any that remain open, plus `[NOTE FOR PM]` callouts flagging deliberate deviations from the approved brief. As of this draft, all inline assumptions raised during discovery have been resolved into explicit decisions — §9 currently holds disclosure notes, not open assumptions.

**This PRD deliberately deviates from the approved brief in four places** — all flagged inline with `[NOTE FOR PM]` and indexed in §9: cutting all AI confidence/risk scoring (§5), cutting the reviewer's "merge duplicates" action (§4.4 FR-13), cutting reviewer prioritization/importance-marking (§5), and replacing automatic CI pipeline wiring with a manual process (§4.6 FR-21). None are silent — each needs explicit sign-off from whoever owns the brief before this PRD is treated as final.

## 1. Vision

The Application Intelligence Platform turns a running web application into a business-language map of what it actually does — discovered automatically, confirmed by a human, and converted into running regression coverage. Where existing test-automation tools execute journeys someone already told them about, V1 answers the prior question: *what are all the business journeys this application supports, right now, as built?*

Given only a URL and dedicated test credentials — no source code or repository access — V1 explores a non-production instance of a customer's application the way a thorough tester would, infers candidate business capabilities and journeys from what it observes, and hands them to a human reviewer (typically a QA Director or Engineering Leader) to approve, rename, reject, or delete — V1's review toolset is deliberately simple (§4.4); it doesn't yet support merging, splitting, or editing what makes up a Journey. Approved journeys become the trusted basis for generated integration test scenarios and executable Playwright tests, delivered into the customer's own repository and CI/CD pipeline. Above that sits a set of views — Capability Map, Journey Explorer, coverage analytics, and a multi-application executive dashboard — that let engineering and QA leadership see what's understood, what's tested, and what isn't, without anyone having had to remember to document it.

V1 does not claim technical discovery superiority (see brief's *What Makes This Different*); it wins pilots on the strength of the business-journey framing, the human-in-the-loop trust mechanism, and a credible roadmap. The deeper technical moat — source-code correlation and change-impact prediction — arrives in V2 and V3.

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

- **UJ-1. Maria reviews her application's first discovered map.**
  - **Persona + context:** Maria, a QA Director at a mid-size insurer, has just had V1 finish its first discovery run against the claims-processing staging environment.
  - **Entry state:** Authenticated in the platform, viewing the Review queue for the first time for this application.
  - **Path:** She opens the queue and sees a list of candidate Journeys — "Claims Approval," "Policy Issuance," a few oddly-split duplicates. She renames one the AI labeled generically, deletes two low-value duplicates, and approves the rest one by one.
  - **Climax:** As she approves the last Journey, the platform confirms scenario and Playwright test generation has started for all approved Journeys.
  - **Resolution:** She leaves the review queue empty (all triaged) and opens the Capability Map to see the approved Journeys rendered as a business-language view she can show her Engineering Leader.
  - **Edge case:** If discovery hit its time budget before finishing (per FR-5/FR-7) mid-application, Maria sees a partial map clearly marked as incomplete, not presented as a finished result.

- **UJ-2. Devon checks release readiness before a Friday deploy.**
  - **Persona + context:** Devon, an Engineering Leader, is deciding whether to approve a release.
  - **Entry state:** Authenticated, opens the executive dashboard for the application in question.
  - **Path:** Reviews coverage analytics — which approved Journeys have a generated test and which don't (V1 shows generated-vs-not, not live pass/fail status from CI) — across the two Applications his org has onboarded.
  - **Climax:** Sees that one recently-approved Journey has no generated test yet (still mid-pipeline), and flags it before sign-off.
  - **Resolution:** Approves the release with a documented view of what's covered, rather than a gut call.

## 3. Glossary
*"Capability" and "Journey" are used as shorthand for "Business Capability" and "Business Journey" throughout the rest of this document.*

- **Application** — A single running web application onboarded for discovery. A customer may onboard multiple Applications from V1 launch.
- **Discovery Run** — One execution of the Runtime Discovery engine against an Application, bounded by a configured scope and time budget.
- **Discovery Scope** — The subset of an Application (e.g., specific sections/paths) a Discovery Run is configured to explore; defaults to the full Application if unscoped.
- **Business Capability** — A named, business-language grouping of related functionality the AI infers from discovery signals (e.g., "Claims Processing").
- **Business Journey** — A named, business-language sequence of pages/actions/API calls representing an end-to-end user workflow (e.g., "Claims Approval"), nested under a Capability.
- **Trusted Knowledge Model** — The set of Capabilities and Journeys that have been human-approved; only these feed Scenario Generation and Analytics.
- **Scenario** — A generated integration test scenario (happy-path or negative/edge-case) derived from an approved Journey.
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

#### FR-4: Configurable discovery scope
User can define a Discovery Scope (e.g., limit to specific sections/paths) rather than defaulting to full-Application discovery.

#### FR-5: Discovery time budget
User can configure a maximum time budget for a Discovery Run, as a safety cap against unbounded exploration (e.g., infinite pagination or calendar "next" links).

**Notes:** Onboarding does not technically verify that the target is a Non-Production Environment — see §11 Constraints and Guardrails.

### 4.2 Runtime Discovery

**Description:** The exploration engine — navigates the Application the way a thorough tester would, capturing everything it encounters as raw signal for the intelligence layer.

**Functional Requirements:**

#### FR-6: Autonomous exploration
Platform autonomously navigates pages, exercises UI actions and forms, and invokes APIs within the configured Discovery Scope, capturing pages, navigation paths, actions, forms, API calls, and state transitions.

#### FR-7: Discovery stop conditions
A Discovery Run for a given scope terminates when either (a) no new pages, actions, or state transitions are found (exhaustive traversal), or (b) the configured maximum time budget (FR-5) is reached.

**Consequences (testable):**
- A Discovery Run that hits its time budget produces a partial result set, clearly marked incomplete rather than presented as a finished map (realizes UJ-1 edge case).

### 4.3 Journey & Capability Intelligence

**Description:** The AI layer that turns raw discovery signal into business understanding — the core of what makes this a "map," not a crawl log.

**Functional Requirements:**

#### FR-8: AI journey/capability inference
Platform uses AI to transform captured discovery signals into candidate Business Capabilities and Journeys expressed in business language, not raw technical labels (e.g., page/route names).

**Consequences (testable):**
- Every candidate Journey presented in the Review queue (FR-9) has a business-language name, not a raw route/page identifier.
- Every candidate Journey is associated with the specific pages, actions, and API calls (captured per FR-6) that produced it, so a reviewer can trace the inference back to raw evidence.

**Notes:** No AI-generated confidence or risk score is attached to candidates in V1 — see §5 Non-Goals and §9 for the reasoning behind this cut.

### 4.4 Human Review & Approval

**Description:** The trust mechanism at the center of the product. AI-inferred journeys are drafts until a human confirms them; this review step is what turns an inference into an organization's accepted source of truth (realizes UJ-1).

**Functional Requirements:**

#### FR-9: Review queue
Discovered Journeys and Capabilities are presented to a human reviewer before being treated as part of the Trusted Knowledge Model.

#### FR-10: Approve
Reviewer can approve a discovered Journey/Capability, adding it to the Trusted Knowledge Model.

#### FR-11: Reject
Reviewer can reject a discovered Journey/Capability, excluding it from the Trusted Knowledge Model.

#### FR-12: Rename
Reviewer can rename a discovered Journey/Capability.

#### FR-13: Delete
Reviewer can delete a discovered Journey/Capability.

**Out of Scope:** `[NON-GOAL for MVP]` Merging two discovered Journeys, splitting one into two, or editing which pages/actions belong to a Journey are not supported in V1. The brief's Solution narrative describes a reviewer who "merges duplicates" — that specific capability is cut for V1 to keep the review workflow to four simple actions; a reviewer facing duplicate Journeys must instead reject the redundant one(s) rather than merge them.

#### FR-14: Approval gates downstream use
Only approved Journeys/Capabilities enter the Trusted Knowledge Model and feed Scenario Generation and Analytics (§4.5, §4.7).

#### FR-15: New-journey flagging on re-discovery
Re-running discovery on a previously discovered Application flags only newly-discovered Journeys/Capabilities (not seen in a prior run) for human review; already-approved Journeys are not automatically re-surfaced. This is a simple **existence check** (does this Journey's identity already exist in the Trusted Knowledge Model?) — a materially smaller capability than detecting *what changed* inside an existing Journey.

**Out of Scope:** V1 cannot detect that a previously-approved Journey's underlying runtime behavior has changed — only that a Journey it has never seen before now exists. See §5 Non-Goals.

### 4.5 Scenario & Test Generation

**Description:** Converts an approved Journey into executable regression coverage — the day-one deliverable that makes the map actionable, not just informative.

**Functional Requirements:**

#### FR-16: Scenario generation
Platform generates integration test Scenarios for each approved Journey, covering both happy-path and negative/edge-case scenarios.

#### FR-17: Playwright generation
Platform converts generated Scenarios into executable Playwright Test Assets.

#### FR-18: Full regeneration on request
When a customer triggers regeneration of Test Assets for a Journey, platform regenerates Scenarios and Test Assets from scratch. Individual Scenarios are not manually editable prior to Playwright generation in V1 — the approval gate is at the Journey level (§4.4) only.

**Out of Scope:** V1 has no capability to detect *what* changed in a Journey and regenerate incrementally — regeneration is always full, not a diff/patch. See §5 Non-Goals.

### 4.6 CI/CD Delivery

**Description:** Gets generated tests out of the platform and into the customer's real regression process — without that step, the map is interesting but the tests are shelfware.

**Functional Requirements:**

#### FR-19: Export mode choice
Platform can export generated Playwright Test Assets to the customer's source repository via either (a) creating a pull/merge request, or (b) direct commit to a branch — customer configures which mode per Application.

**Consequences (testable):**
- An Application configured for PR mode never receives a direct commit, and vice versa — the two modes are mutually exclusive per Application, not chosen per export.

#### FR-20: CI/CD provider support
Platform supports repository/pipeline targets for GitHub Actions, GitLab CI, Jenkins, and Azure DevOps.

#### FR-21: Manual pipeline wiring
Platform provides instructions/a template for the customer to manually wire generated tests into their CI pipeline's test-run step.

**Consequences (testable):**
- The provided instructions/template are specific to the Application's configured CI/CD provider (FR-20) — a GitHub Actions customer does not receive Jenkins-specific instructions.

**Notes:** `[NON-GOAL for MVP]` Automated pipeline wiring (platform directly modifies the customer's CI config) is deferred — candidate fast-follow, not V1-blocking, per explicit product decision to keep V1 simple here. `[NOTE FOR PM: the brief's Scope section commits to tests running "automatically as part of standard regression" once integrated — V1's manual-wiring-only approach means that automation is customer-executed, not platform-delivered, until the pipeline step is wired in by hand. This is a real deviation from the brief's phrasing, not just an implementation detail — flagging for the same explicit sign-off the confidence-scoring cut (§5) got.]`

### 4.7 Analytics & Dashboards

**Description:** The views that make the Trusted Knowledge Model and generated coverage legible to each audience — realizes UJ-2.

**Functional Requirements:**

#### FR-22: Capability Map
Platform provides a Capability Map view — a business-language map of approved Capabilities.

**Consequences (testable):**
- Every approved Capability (FR-14) appears in the Capability Map; rejected or deleted candidates do not.

#### FR-23: Journey Explorer
Platform provides a Journey Explorer — a detail view of a Journey's screens, actions, and API calls.

**Consequences (testable):**
- Selecting any approved Journey in the Journey Explorer shows the specific pages, actions, and API calls captured for it during discovery (FR-6).

#### FR-24: Coverage analytics
Platform provides coverage analytics showing which approved Journeys have a generated Test Asset, and which do not.

**Consequences (testable):**
- Coverage analytics reflect whether a Test Asset exists for a Journey (FR-17), not whether it is currently passing in the customer's CI/CD pipeline — V1 has no read-back channel from the customer's CI (per FR-21's manual wiring), so pass/fail status post-delivery is outside what the platform can see or report.

#### FR-25: Multi-application executive dashboard
Platform provides an executive dashboard rolling up Capability, coverage, and Journey views across multiple Applications, supporting multi-application onboarding from V1 launch — even where a given customer initially onboards only one Application.

**Out of Scope:** No risk/confidence scorecard in V1 — see §5 Non-Goals.

### 4.8 Deployment

**Description:** V1 ships two deployment models to fit enterprise data-residency requirements from day one.

**Functional Requirements:**

#### FR-26: Two deployment models
Platform supports hosted SaaS and on-premises/VPN-based deployment.

#### FR-27: On-prem data locality
In on-premises deployment, the entire platform — including AI/LLM processing — runs inside the customer's network, using AI provider API keys/endpoints supplied by the customer.

**Feature-specific NFRs:**
- On-prem mode must not require any customer data or AI processing to leave the customer's network.

## 5. Non-Goals (Explicit)

- **No source code or repository read access** for discovery, and nothing that depends on it (route/component/permission/feature-flag structure, dependency mapping, code-to-journey traceability). That's V2.
- **No change intelligence** — predicting which Journeys/tests a specific *code* change affects. That's V3.
- **No AI confidence or risk scoring of any kind** — neither a per-Journey discovery confidence score nor a risk/confidence scorecard. Cut during PRD discovery: meaningful usage/error-rate signals require a real telemetry feed V1 doesn't have, and the unresolved questions weren't worth V1's complexity budget. `[NOTE FOR PM: the approved brief named risk/confidence scoring as a V1 outcome — this is a deliberate scope deviation, see §9 and memlog.]`
- **No runtime drift/change detection** on previously-approved Journeys — V1 cannot tell what changed inside a Journey, only regenerate it from scratch on request.
- **No automated CI pipeline wiring** — manual/template-based only in V1.
- **No native SSO/SAML/OAuth/OIDC protocol implementation or automated MFA-code retrieval** — V1 handles SSO/MFA-protected apps only via customer-supplied reusable session state (FR-3), not by performing the identity-provider handshake itself.
- **No claim of superior discovery technology** in product messaging — V1's differentiation is the business-journey framing and human-in-the-loop trust model, not a proprietary discovery algorithm (per brief).
- **No non-web applications** — mobile/native apps are not addressed by V1.
- **No test frameworks other than Playwright.**
- **No numeric coverage or time-saved targets** — deliberately undefined until real pilot data exists (per brief).
- **No system-enforced non-production safeguard** — determining and declaring a Non-Production target is entirely the customer's responsibility in V1; the platform does not technically verify or block discovery against production.
- **No reviewer prioritization/importance-marking** — the brief's Solution narrative describes a reviewer who "marks what matters most to the business" when reviewing discovered Journeys. V1's review toolset (FR-10–FR-13) has no way to flag business importance; every approved Journey is treated equally. `[NOTE FOR PM: this gap is also why §12 Risk item 3 (no reviewer triage aid) exists — the two are the same underlying capability the brief implied but V1 doesn't build.]`

## 6. MVP Scope

### 6.1 In Scope
- Application onboarding via URL + Dedicated Test Account credentials, standard login only (FR-1–FR-5).
- Runtime discovery with configurable scope and time-budget safety cap (FR-6–FR-7).
- AI-driven Journey/Capability inference (FR-8).
- Human review, approve/reject/rename/delete workflow (FR-9–FR-15).
- Scenario generation (happy-path + negative) and Playwright test generation (FR-16–FR-18).
- CI/CD delivery via PR or direct commit, across GitHub Actions/GitLab CI/Jenkins/Azure DevOps, with manual pipeline-wiring instructions (FR-19–FR-21).
- Capability Map, Journey Explorer, coverage analytics, multi-application executive dashboard (FR-22–FR-25).
- Hosted SaaS and on-prem/VPN deployment, with full in-network AI processing for on-prem (FR-26–FR-27).

### 6.2 Out of Scope for MVP
See §5 Non-Goals — all items there apply to MVP scope directly.

## 7. Success Metrics

Per the approved brief, V1 business success is **not** a customer-count or revenue target — it's proving the core thesis (runtime discovery → journey mapping → generated tests) holds up in real pilots well enough to justify building V2. No numeric coverage or time-saved target is set for V1 by design; inventing one now would be a fabricated claim rather than a real criterion.

**Directional signals (qualitative, tracked per pilot):**
- **SM-1**: An Engineering Leader or QA Director who, having tried V1, keeps using it into a second and third release cycle without being asked to. Validates FR-9–FR-25 (the full review-to-dashboard loop delivering ongoing value).
- **SM-2**: Discovered Journeys need light correction rather than heavy rework during human review — a proxy for discovery accuracy. Validates FR-8–FR-13.
- **SM-3**: Generated Test Assets a QA team trusts enough to fold into their real regression process, not treat as a novelty. Validates FR-16–FR-21.

**Counter-metrics (do not optimize)**
- **SM-C1**: Review-queue approval rate should not be optimized by inflating Journey granularity or over-splitting Capabilities to look more thorough — that would game SM-2 without reflecting real discovery quality.

## 8. Open Questions

1. **Time-to-first-map validation.** "Hours, not days or weeks" is the internal target — not yet validated against real-world application complexity. Confirm before this appears in any external-facing claim. *(from brief)*
2. **V2 greenlight threshold.** What counts as V1 having "proven the thesis enough" to justify building V2 — number of design partners, retention through a full release cycle, something else? *(from brief)*
3. Should V1 add a technical safeguard against accidentally running discovery against a production environment, beyond customer responsibility — given how severe that failure mode is (live side effects on a production system)?
4. What are the hosted SaaS data residency/retention specifics?
5. Is cutting all confidence/risk scoring the right long-term call, or should a lightweight, discovery-signal-only version (no external feed required) be reconsidered before V1 ships? *(Reaffirmed as fully cut during Finalize review, after confirming 2 of the brief's 4 scorecard inputs — complexity, coverage-gap — don't strictly need a telemetry feed. Kept simple by explicit decision; see `addendum.md` for how to reintroduce cheaply later.)*
6. What happens when a direct-commit regeneration (FR-18/FR-19) overwrites a customer's manually-edited test file? No conflict handling is currently specified.
7. What page/action volume must V1 handle for a "typical" enterprise pilot application — is there a performance/scale ceiling to design against?
8. For SSO/MFA-protected apps (FR-3), how does the customer actually capture and hand off the reusable session state — a manual export process, a small helper tool the platform provides, or something else? Mechanism isn't yet specified; deliberately deferred to engineering during technical design rather than resolved in this PRD. **Deferred with a condition, not ignored:** this must be resolved before UX/architecture work on the Application Onboarding flow (§4.1) proceeds — the onboarding screen design and any helper-tool UX depend directly on the answer.

## 9. Assumptions Index

- **§4.1 Notes / §11**: The non-production-only rule is enforced entirely by customer responsibility, not by the platform, in V1. (Confirmed decision, not an open assumption — flagged here because it's a real residual risk; see §12 item 1.)
- **§5 [NOTE FOR PM]**: Removing all confidence/risk scoring is a deliberate deviation from the approved brief's stated V1 outcomes — flagged for explicit sign-off, not a quiet scope cut.
- **§4.4 FR-13 [NON-GOAL for MVP]**: The brief's "merges duplicates" reviewer action is cut for V1 — reviewers reject redundant Journeys instead of merging them.
- **§5 [NOTE FOR PM]**: The brief's "marks what matters most to the business" reviewer capability has no V1 equivalent — every approved Journey is treated with equal weight.
- **§4.6 FR-21 [NOTE FOR PM]**: The brief commits to tests running "automatically as part of standard regression" once delivered; V1's manual-pipeline-wiring approach means that automation step is customer-executed, not platform-delivered, until wired in by hand — a deviation from the brief's phrasing.

*(SSO/MFA handling and Scenario-editing granularity were open assumptions in an earlier draft; both are now resolved decisions — see FR-3 and FR-18.)*

## 10. Cross-Cutting NFRs

- **Security**: Standard enterprise-grade secret handling for stored discovery credentials (encryption at rest and in transit, least-privilege service accounts). No bespoke certification requirement specified for V1.
- **Reliability**: A Discovery Run must complete or fail gracefully within its configured time budget; partial results are retained and clearly marked incomplete on timeout (realizes UJ-1 edge case).
- **Data locality (on-prem)**: On-prem deployment must keep all data and AI processing inside the customer's network (FR-27).

## 11. Constraints and Guardrails

**Safety**
- V1 must never be run against a customer's production-facing environment. In V1, this is a **customer responsibility**, not a platform-enforced constraint. See §12 Risk Register item 1 for exposure and mitigation status.

**Privacy**
- Discovery credentials must be a Dedicated Test Account, never a real end-user identity (FR-2). Standard enterprise-grade secret handling applies (§10).

## 12. Risk and Mitigations

1. **Risk**: Discovery engine triggers real side effects (payments, emails, data changes) if accidentally pointed at a production environment. **Mitigation**: Customer contractually/operationally designates a Non-Production target; prominently documented at onboarding. **Unresolved**: whether V1 needs a technical safeguard (Open Question 3).
2. **Risk**: AI misclassifies or over-fragments Business Journeys, eroding trust in the map. **Mitigation**: Mandatory human review/approval gate before anything enters the Trusted Knowledge Model (FR-9–FR-14).
3. **Risk**: Without any AI confidence signal, reviewers triaging a large discovery output have no prioritization aid, which could slow review at scale. **Mitigation**: None built into V1 — flagged for revisit if pilot feedback shows this is a real bottleneck (Open Question 5).
4. **Risk**: Full-regeneration-on-request (FR-18) combined with direct-commit export (FR-19) could silently overwrite a customer's manually-edited test file. **Mitigation**: Customer controls export mode and can choose PR-based review instead; direct-commit mode carries this risk by design (Open Question 6).
5. **Risk**: V1 has no differentiated technical moat (per brief); pilots may be won or lost on roadmap credibility rather than delivered capability. **Mitigation**: Sales motion leans on an honest, credible V2/V3 roadmap story — see `addendum.md`.
6. **Risk**: `FR-6`'s autonomous form/API exercising has no destructive-action guardrail — even in a Non-Production environment, the discovery engine could trigger irreversible side effects (real emails sent, shared test data deleted, fraud-detection tripwires) if that environment isn't fully isolated from real-world systems. **Mitigation**: **Accepted risk** — V1 relies entirely on the customer providing a properly isolated Non-Production environment (§11); no platform-side guardrail is built in V1, by explicit decision.

## 13. Integration and Dependencies

- **CI/CD providers**: GitHub Actions, GitLab CI, Jenkins, Azure DevOps (repository export; manual pipeline-wiring instructions per FR-21).
- **AI/LLM provider**: Hosted SaaS mode uses vendor-hosted AI processing. On-prem mode requires the customer to supply their own AI provider API keys/endpoint (FR-27).
