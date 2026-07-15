---
title: "Sprint Change Proposal — UX Redesign Ripple (2026-07-15)"
status: approved
created: 2026-07-15
approved: 2026-07-15
---

## 0. Approval Record

Approved by Harsha, 2026-07-15, with one deviation from this proposal's recommendation: **both flagged judgment calls (§4.A) were resolved as full cuts, not "retained but deferred."** Specifically:

- **FR-26/27 (on-prem data locality, Epic 7)** — treated the same as every other screen-driven cut, not specially preserved as a retained compliance requirement.
- **PRD UJ-2 (Devon/Dashboard)** — treated the same as its supporting screen (deferred alongside FR-25), not called out for separate product sign-off.

This is recorded here because it's a deliberate deviation from this document's own recommendation (§3, §4.A) — a future reader should know the more conservative path was considered and explicitly declined, not overlooked.

# Sprint Change Proposal — UX Redesign Ripple

## 1. Issue Summary

A new interactive prototype (`ux-designs/ux-AITestGen-2026-07-13/mockups/prototype-v2-standalone.html`) was shared on 2026-07-15, superseding the approved v1 prototype the PRD, architecture, and all 22 V1 stories were written against. UX review of the new prototype (documented in `DESIGN.md`/`EXPERIENCE.md`, both updated to `2026-07-15`) found it is not a visual refresh — it is a different product shape:

- **IA collapsed** from an 11-screen, persistent-nav-rail, multi-application shell to a 6-screen single-application guided pipeline (Sign In → Home → Connect App → Discover Journeys → Review Scenarios → Generate Suite).
- **Review scope expanded**: Journey and Scenario rows now support rename/edit/remove via a per-row menu, superseding the PRD's explicit four-action-only (Journey) and view-only (Scenario) non-goals.
- **Six screens have no surviving home**: Applications list (multi-app landing + hero stats), App Overview/Capability Map, Coverage Analytics, multi-app Dashboard, Connect to CI/CD, and Settings.

User confirmed (this session): every screen UX review flagged as missing is **intentionally cut**, not just absent from this particular export — explicit go-ahead to update PRD, architecture, and epics/stories to match. User also confirmed Generate Suite's "Run immediately / Schedule for later / Save without running" execution options are **UI placeholders only** — the real test-execution/delivery mechanism is deliberately undecided and must not be locked into architecture as a commitment.

No code exists yet (repository has no `apps/`/`packages/` — Story 1.1 hasn't started). All 22 stories are `ready-for-dev`, none `in-progress` or beyond. **This is a pre-implementation replan, not a mid-sprint correction** — there is nothing to roll back.

## 2. Impact Analysis

### Epic Impact

| Epic | Impact |
|---|---|
| Epic 1 (Onboarding) | Story 1.2 loses its nav-rail/switcher-specific ACs (new top-bar + Home landing IA); Stories 1.4/1.5 need rewriting against a single-page Connect App form, not a 3-step wizard — and two fields (Discovery Scope, Time Budget) weren't visible in the new prototype's form at all (`[GAP]`, not confirmed cut). |
| Epic 2 (Discovery) | No screen-level impact confirmed; Discovery Progress screen wasn't reachable in the new prototype (`[GAP]`) — FRs/ACs unchanged, flagged for re-verification only. |
| Epic 3 (Review) | **Scope change, not cut.** FR-12/13's action set expands to include edit; new FRs needed for Journey-edit and Scenario-edit/remove. |
| Epic 4 (Generation) | Story 4.2's "Generated Tests" code-viewer screen folds into "Generate Suite," which adds a new named-suite/execution-mode concept not previously in the PRD (`[GAP]` on real semantics, confirmed placeholder-only for now). |
| Epic 5 (CI/CD Delivery) | **Confirmed cut from V1 UI.** No Connect to CI/CD screen exists; Generate Suite's Execution radio is an unspecified placeholder standing in for whatever this becomes. Recommend: defer Epic 5 post-V1 pending a real design once "the integration is tagged." |
| Epic 6 (Analytics) | **Mostly cut.** 6-1 (Capability Map), 6-3 (Coverage Analytics), 6-4 (Executive Dashboard): no surviving screen, confirmed cut, recommend defer post-V1. 6-2 (Journey Explorer): substantially satisfied by Discover Journeys' detail panel — recommend rewrite, not cut. |
| Epic 7 (AI Provider / Deployment) | Settings screen (Story 7.1's only UI) is cut. **Judgment call, flagged for explicit confirmation**: FR-26/27 are compliance-grade NFRs (on-prem data locality), not merely a UI convenience — recommend treating this as "UI home deferred, capability retained," not a silent NFR cut. |

### Story Impact

~15 of 22 existing stories need rewriting or rescoping; 0 need rollback (none started). See §4 for the full per-story diff.

### Artifact Conflicts

- **PRD**: §1 Vision (Capability Map/dashboard framing), §2.3 UJ-2 (Devon/Dashboard — no surviving screen), §4.4 FR-13 + Out-of-Scope note, §4.5 FR-18, §4.6 (CI/CD, FR-19-21), §4.7 (FR-22-25), §4.8 (FR-26/27 — flagged, not cut), §5 Non-Goals, §6 MVP Scope, §9 Assumptions Index all need updates.
- **Architecture**: Module Map rows for CI Delivery, CI Instructions, and Analytics need a "deferred" annotation; Deferred section gains the execution/delivery-mechanism placeholder; no AD currently asserts anything that contradicts the new IA (AD-7, AD-8, AD-12, etc. are all still structurally valid — they're about data ownership, not screens), so the core invariants survive unchanged. This is a scope-shrink, not a re-architecture.
- **UX**: Already updated (`DESIGN.md`, `EXPERIENCE.md`, both `2026-07-15`) — this proposal exists to bring PRD/architecture/epics into line with that update, not the reverse.

### Technical Impact

None — no code exists. This changes what gets built, not anything already built.

## 3. Recommended Approach

**Hybrid: Direct Adjustment (Epics 1-4) + MVP Scope Review (Epics 5-7).**

- **Epics 1-4**: Direct Adjustment. Rewrite affected story ACs in place to match the new IA and expanded review scope. Low risk, low effort — no story has started, and the underlying FRs (onboarding, discovery, review, generation) are intact, just reshaped.
- **Epics 5-7**: MVP Scope Review. Epic 5 (CI/CD) and most of Epic 6 (Analytics/Dashboard) lose their only UI and are recommended for deferral to post-V1 rather than force-built against an undesigned placeholder. Epic 7 needs an explicit product decision (see flagged item below) before its scope can be finalized.
- **Rollback**: Not viable/not applicable — nothing has been built.

This keeps the MVP buildable against a real, confirmed spec instead of stories written against screens that no longer exist, while being honest that three epics' scope has genuinely shrunk rather than papering over it with placeholder ACs.

## 4. Detailed Change Proposals

### 4.A PRD (`prd.md`)

| Section | Change | Rationale |
|---|---|---|
| §1 Vision | Reword "Above that sits a set of views — Capability Map, Journey Explorer, coverage analytics, and a multi-application executive dashboard" → "A Journey Explorer view (folded into the review pipeline) lets engineering and QA leadership inspect discovered evidence; the Capability Map, coverage analytics, and multi-application executive dashboard described in earlier planning are deferred post-V1 (see §6, §9)." | Confirmed cut — Vision shouldn't promise screens no longer in V1 scope. |
| §2.3 UJ-2 | Add `[NOTE FOR PM]`: Devon's journey has no supporting V1 screen as of 2026-07-15; recommend marking UJ-2 deferred post-V1 alongside FR-25, or requiring a new design before it can ship in V1. Do not delete UJ-2 — a named user journey being cut is a product decision, not a doc-cleanup. | This is the single highest-stakes item in this proposal — a primary persona's entire use case losing its screen deserves visibility, not silent removal. |
| §4.4 FR-13 Out-of-Scope note | Narrow from "Merging two discovered Journeys, splitting one into two, or editing which pages/actions belong to a Journey are not supported in V1" → "Merging two discovered Journeys or splitting one into two are not supported in V1." (drop "or editing") | Edit capability confirmed added; merge/split remain unconfirmed/unsupported per new prototype. |
| §4.4 (new) | Add **FR-28: Edit a discovered Journey.** "Reviewer can edit a discovered Journey via a per-row action menu, in addition to approve/reject/rename/delete. `[GAP]` exact edit surface (what composition fields are editable) not yet confirmed — needs a follow-up UX pass once the `⋯` menu's edit affordance is reachable in a future prototype export." | Confirmed scope expansion, but the *extent* of "edit" is genuinely unknown — don't fabricate a spec. |
| §4.5 FR-18 | Strike "Individual Scenarios are not manually editable prior to Playwright generation in V1 — the approval gate is at the Journey level (§4.4) only." Replace with a pointer to new FR-29. | Directly contradicted by the new prototype. |
| §4.5 (new) | Add **FR-29: Edit or remove an individual Scenario.** "Reviewer can rename, edit, or remove a generated Scenario before Playwright generation, via a per-row action menu on Review Scenarios. `[GAP]` whether an edited Scenario's test data/steps actually feed Playwright generation, or the edit is display-only, is unconfirmed." | Same rationale as FR-28. |
| §4.6 (CI/CD Delivery) | Add `[NOTE FOR PM]` at the top of §4.6: "As of 2026-07-15, FR-19–21 are recommended for deferral to post-V1 — the Connect to CI/CD screen this feature depended on is cut, and Generate Suite's replacement Execution control (`Run immediately`/`Schedule for later`/`Save without running`) is an explicit UI placeholder with no confirmed underlying mechanism. Do not build FR-19–21 against the current spec; revisit once 'the integration is tagged' (user's phrasing)." | Confirmed cut + explicit deferral of the mechanism itself. |
| §4.7 (Analytics) | FR-22 (Capability Map): mark deferred post-V1. FR-23 (Journey Explorer): reword — "satisfied by the per-Journey step detail shown when a candidate is selected on Discover Journeys, rather than a standalone explorer screen." FR-24 (Coverage Analytics): mark deferred post-V1. FR-25 (Executive Dashboard): mark deferred post-V1, cross-reference the UJ-2 note. | Matches confirmed screen cuts; FR-23 survives in modified form rather than being cut, since Discover Journeys' detail panel demonstrably does what it describes. |
| §4.8 (Deployment) | Add `[NOTE FOR PM — flagged, not auto-resolved]`: "Settings, the only V1 screen carrying the AI-provider-mode toggle (Story 7.1), is cut from the new prototype's IA. FR-26/27 are compliance-grade NFRs (on-prem data locality), not UI-only conveniences — this proposal treats them as **UI-home-deferred, requirement-retained** rather than cut, since the prototype export not including a Settings screen is weaker evidence for cutting a compliance NFR than it is for cutting a dashboard. Needs explicit confirmation from {user_name} either way before Epic 7 stories are finalized." | The one place this proposal deliberately does *not* extend "whatever's missing is cut" at face value — the stakes (data-residency compliance) are high enough to ask rather than assume. |
| §5 Non-Goals | Update the "merges duplicates" bullet to reflect FR-28's edit capability; leave all other Non-Goals (confidence scoring, prioritization, automated CI wiring, drift detection, etc.) unchanged — nothing in the new prototype touches them. | Keep the diff minimal — only touch what's actually contradicted. |
| §6 MVP Scope | Rewrite the In Scope bullet list to match: single-page Connect App onboarding; discovery; AI inference; review with expanded (approve/reject/rename/**edit**/delete) actions; Scenario generation with the same expanded actions; Generate Suite (naming + placeholder execution config); Journey Explorer folded into Discover Journeys. Move Capability Map, Coverage Analytics, Executive Dashboard, and CI/CD Delivery (FR-19-25, minus FR-23) to a new "Deferred Post-V1" subsection with a pointer to this proposal. | Matches confirmed scope; makes the MVP boundary honest rather than aspirational. |
| §9 Assumptions Index | Add an entry recording this whole change, dated 2026-07-15, pointing at this proposal and at `EXPERIENCE.md`'s 2026-07-15 note. | Keeps the PRD's own change record intact — future readers shouldn't have to reconstruct this from git history. |

### 4.B Architecture (`ARCHITECTURE-SPINE.md`)

| Section | Change | Rationale |
|---|---|---|
| Module Map — CI Delivery, CI Instructions rows | Add a note: "Deferred post-V1 as of 2026-07-15 (Sprint Change Proposal) — do not build against FR-19–21 until the execution/delivery mechanism is redesigned." Module contracts (`DeliveryAdapter`, `CIInstructionsGenerator`) stay defined (no harm in keeping the port shape ready) but are marked not-yet-scheduled. | Ports already exist as clean interfaces (AD-4) — no architectural rework needed, just a scheduling note. |
| Module Map — Analytics row | Add a note: "Capability Map / Coverage Analytics / Executive Dashboard reads deferred post-V1; Journey Explorer read is retained, now served from the Discover Journeys detail endpoint rather than a standalone Analytics view." | Matches PRD FR-22/24/25 deferral and FR-23's retained-but-relocated status. |
| Deferred section | Add: "**Test-suite execution mechanism** (Generate Suite's `Run immediately`/`Schedule for later`/`Save without running`): explicitly a UI placeholder as of 2026-07-15 (user-confirmed) — no architecture decision is made here about whether the platform executes tests itself. **Do not** interpret 'Run immediately' as authorizing a live-test-execution capability; that would contradict the existing 'no CI read-back channel' stance (FR-24 consequence) without a real decision having been made. Revisit when the mechanism is actually specified." | This is the one place a wrong inference here would be expensive — locking in "platform runs tests" as an architectural fact would ripple into infra, security, and scope no one has actually decided on yet. |
| binds / updated frontmatter | `updated: 2026-07-15`; no changes to `binds` (FR list) since no FR numbers are removed, only annotated as deferred, and FR-28/29 are additive. | Keeps the spine's FR-binding honest without a disruptive renumbering. |

### 4.C Epics & Stories (`epics.md` + `_bmad-output/implementation-artifacts/*.md`)

| Story | Change |
|---|---|
| 1.2 Sign In & Organization-Scoped Workspace | Drop nav-rail-specific ACs (236px rail, Workspace/Onboard/Understand/Automate/Prove groups, rail-foot Settings/sign-out). Replace with: land on Home (3 action cards); top bar shows brand mark + avatar menu (name/email/Log out). **Keep** the Organization-scoping AC (AD-12) unchanged — that's a data/security requirement, not a nav-rail artifact. |
| 1.4 Configure Application Authentication Method | Rewrite from "wizard step, option-card auth choice" to "Connect App form field, plain `<select>` for Authentication method." Flag `[GAP]`: SSO/MFA session-handoff mechanism (PRD Open Question 8) not visible in the new form at all — story should treat this as still-unresolved, not resolved-to-"not needed." |
| 1.5 Configure Discovery Scope & Time Budget | Flag `[GAP]`: fields not visible in the new Connect App screenshot. Recommend keeping this story as-is (scope/time-budget are FR-4/FR-5, not confirmed cut) but adding a note that the field placement needs re-verification against a fuller prototype export before dev-story starts. |
| 3.2/3.3/3.4 (Approve/Reject/Rename/Delete) | Add new AC for the `⋯` menu's Edit action (FR-28) alongside existing four actions; update UX-DR5/UX-DR22 references. |
| 4.1 Generate Scenarios | Update AC: Scenario rows are no longer strictly view-only — add rename/edit/remove per FR-29; drop the "no checkbox/action button" language tied to the old UX-DR23. |
| 4.2 Generate Playwright Test Assets | Rename/reframe around "Generate Suite" (named suite, target environment, execution-mode placeholder) rather than a standalone "Generated Tests" code-review screen; keep the underlying `TestAsset`/code-generation AC unchanged (AD-8 still applies) — only the screen framing changes. |
| 5.1/5.2/5.3 (CI/CD) | Recommend moving to `backlog`/deferred status (not deleted) pending the real execution/delivery mechanism design. |
| 6.1 Capability Map | Recommend deferred/backlog status. |
| 6.2 Journey Explorer | Rewrite: "the Journey's evidence detail is shown inline in Discover Journeys' detail panel when a candidate is selected" rather than a standalone Journey Explorer screen; AC updated to match `EXPERIENCE.md`'s Component Patterns. |
| 6.3 Coverage Analytics | Recommend deferred/backlog status. |
| 6.4 Multi-Application Executive Dashboard | Recommend deferred/backlog status; cross-reference PRD UJ-2 flag. |
| 7.1 Configure AI Provider Mode | Flag `[NOTE FOR PM]`: no confirmed UI home (Settings cut). Recommend holding this story at `backlog` pending explicit resolution of the §4.8 PRD flag above — do not silently redesign its UI without that decision. |
| 7.2 Enforce In-Network AI Processing | Unaffected functionally (no UI dependency) — keep as-is; only Story 7.1's UI entry point is in question. |

Stories not listed (1.1, 1.3, 2.1-2.5, 3.1, 3.5) have no confirmed change — flagged only where a `[GAP]` (e.g. Discovery Progress screen not reached) warrants a re-verification note, not a rewrite.

## 5. Implementation Handoff

**Scope classification: Major.** This changes MVP boundaries (three epics' worth of scope moving to deferred), not just story wording — routes to Product Manager / Solution Architect, per this workflow's own classification rule, even though the mechanical edits themselves are Direct-Adjustment-simple.

- **Product Manager (John)** — owns: confirming the Epic 7 / FR-26-27 flag (§4.A, §4.8 row) since it's a compliance-NFR judgment call I'm not making unilaterally; confirming PRD UJ-2's disposition (deferred vs. redesigned); signing off on §6 MVP Scope's rewritten In/Out boundary.
- **Solution Architect (Winston)** — owns: reviewing the architecture Deferred-section addition (execution-mechanism placeholder) to make sure nothing already-decided (AD-4, AD-8, AD-9) is quietly contradicted by a future CI/CD or test-execution design.
- **Developer agent** — once PM/Architect sign off: mechanical application of the story-level edits in §4.C, and updating `sprint-status.yaml` to move Epic 5 stories and Stories 6.1/6.3/6.4/7.1 to `backlog` (deferred) status.

**Success criteria:** PRD, architecture, and epics/stories all describe the *same* product as `DESIGN.md`/`EXPERIENCE.md` (2026-07-15) — no story references a cut screen as if it still exists, no FR is silently dropped without a `[NOTE FOR PM]` trail, and the two flagged judgment calls (Epic 7/NFR-27, PRD UJ-2) have explicit answers before Epic 5-7 stories are treated as buildable.
