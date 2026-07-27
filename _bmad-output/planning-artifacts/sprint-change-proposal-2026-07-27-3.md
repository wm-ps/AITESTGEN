# Sprint Change Proposal — UX v3 Redirect Reconciliation

**Date:** 2026-07-27
**Trigger:** New UX prototype (`prototype-v3.html`) reconciled into `DESIGN.md`/`EXPERIENCE.md` (2026-07-27), superseding the 2026-07-15/2026-07-21 UX baseline.
**Mode:** Batch

## 1. Issue Summary

A new UX prototype (`prototype-v3.html`) was reconciled into the locked UX spine on 2026-07-27 via `bmad-ux` (full detail in `_bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/reconcile-prototype-v3.md` and `.memlog.md`, entries 38-53). Net effect on the product:

- **Adopted:** a full visual-identity redirect (teal→blue accent, native-font-stack→Inter webfont, flat→soft-shadow elevation, no-gradients→two permitted gradient surfaces); dropped the "full dark-mode parity" commitment (light-mode only); a Suite Generated post-generation screen (resolves a prior `[GAP]`); a Review Scenarios Ready/Needs-Data readiness filter; a corrected Landing-persistence rule (an Application record never disappears from Home once onboarded, regardless of Journey count); the concrete three-option Connect App authentication method set.
- **Rejected as prototype drift, not adopted:** a reintroduced Journey-level Edit action; a raw scrolling discovery live-feed; a single-file TypeScript suite download; a "Discovery Attention" approve/skip gate; a "Workspace" multi-tab home screen with live pass/fail test-execution results.

This is a course-correction pass because several of these items conflict with **already-implemented, already-`review`-status stories** (Epic 1: 1.2, 1.4; Epic 4: 4.1, 4.2), not just unbuilt backlog items.

## 2. Impact Analysis

### Epic Impact

| Epic | Status | Impact |
|---|---|---|
| Epic 1 (Onboarding) | in-progress | Stories 1.2, 1.4 need AC amendments + rework (see below). 1.3, 1.6 unaffected in substance. |
| Epic 2 (Discovery) | in-progress | No AC changes — 2.2/2.7's business-language-only discovery display is reconfirmed, not altered. |
| Epic 3 (Curation) | in-progress | No AC changes — Rename+Delete-only reconfirmed, not altered. |
| Epic 4 (Generation) | in-progress | Stories 4.1, 4.2 need AC amendments (see below). 4.3 unaffected, benefits from 4.2's resolved gap. |

No epic added, removed, or resequenced. No new epic needed — every adopted change fits inside existing FRs (FR-16, FR-17, FR-29); every rejected item was already unbacked by any FR or directly contradicted one (FR-13/FR-14).

### Artifact Conflicts

- **PRD:** No conflict. Dark-mode parity was never a PRD/FR requirement (confirmed via search — it only ever existed as a Story 1.2 AC / `DESIGN.md` commitment), so dropping it doesn't touch MVP scope. No PRD section needs updating.
- **Architecture:** No conflict. `ARCHITECTURE-SPINE.md` has no dark-mode/theming decision — theming lives entirely in the frontend token layer (`apps/web/src/tokens.css`, `theme.ts`), which is a Story 1.2 implementation detail, not an architecture decision. No architecture changes needed.
- **UX Design:** Already reconciled (`DESIGN.md`/`EXPERIENCE.md`, this session) — the source of this change, not a downstream conflict.
- **Other artifacts:** Frontend component tests referencing old visual assumptions (e.g. `GenerateSuite.test.tsx`, `TestSuiteResults.test.tsx`, `ReviewScenarios.test.tsx`) will need updates alongside their story's rework — noted per-story below, not a separate epic.

### Key finding: dark-mode code already exists

`apps/web/src/tokens.css` and `theme.ts` already implement `@media (prefers-color-scheme: dark)` and `data-theme="dark"` overrides (Story 1.2 is `review` status — this was actually built). Dropping the parity **requirement** is not free: leaving that code in place un-updated would show a broken, half-migrated theme (old teal-based dark values against new blue-based light values) to any user with OS dark mode enabled. This must be an explicit removal, not a silent gap — folded into Story 1.2's rework below.

## 3. Recommended Approach

**Option 1 — Direct Adjustment.** Amend 4 story ACs (1.2, 1.4, 4.1, 4.2) and update `apps/web/src/tokens.css`/`theme.ts` (shared, global) for the new palette/typography/elevation tokens. Because the frontend already uses a token-based design system, the color/font/shadow redirect is a **global token-file change**, not per-story rework — every screen consuming those tokens restyles automatically. Only stories with genuine new/changed *behavior* need to go back through dev-story.

- **Option 2 (Rollback):** Not viable/not applicable — nothing here needs reverting; we're moving forward to a new confirmed design, not undoing a mistake.
- **Option 3 (MVP Review):** Not viable/not applicable — no FR or MVP goal is touched; every adopted item fits existing FRs, every rejected item was already out of scope or unbacked.

**Effort:** Low–Medium (4 story reworks + 1 global token update, no epic restructuring, no architecture change).
**Risk:** Low (every decision already made and logged in `.memlog.md`/`reconcile-prototype-v3.md`; no open product ambiguity left in this change set).

## 4. Detailed Change Proposals

### Story 1.2 — Sign In & Organization-Scoped Workspace

**(a) Home screen layout**

OLD:
> they land on Home, showing three action cards (Start a New Project, Managed Applications, Watch a Product Demo) beneath a top bar (brand mark + product name, left; user-initials avatar, right)

NEW:
> they land on Home. With zero Applications onboarded, Home shows an onboarding empty state (icon badge, "No projects yet" heading, one line of body copy, a primary "+ Create New Project" button). With at least one existing Application, Home instead shows that Application as a persistent card (name, journey/scenario counts, status) beside a "Watch Demo" action — clicking the card **resumes the guided pipeline** at that Application's Discover Journeys step, never resetting to Connect App. An Application's card remains on Home regardless of its Journey count, including zero after all Journeys are deleted — Home only reverts to the zero-Applications empty state when no Application has ever been onboarded. All of this sits beneath the existing top bar (brand mark + product name, left — click returns to Home from anywhere; user-initials avatar, right).

**Rationale:** `prototype-v3.html` replaces the three static cards with a conditional empty/persistent-card layout; also resolves an ambiguity (does an Application disappear from Home if all its Journeys are deleted? — no, confirmed 2026-07-27).

**(b) Dark-mode parity**

OLD:
> the design-token system is applied with full light/dark parity (`:root` light defaults, `@media (prefers-color-scheme: dark)` override, explicit `data-theme` override) — no component hardcodes a color

NEW:
> the design-token system is applied per `DESIGN.md`'s current light-mode-only token set — no component hardcodes a color. `[DECISION, 2026-07-27]` Full dark-mode parity is dropped as a requirement (the reference UX no longer specifies dark values, and this was never a PRD/FR commitment). The existing `@media (prefers-color-scheme: dark)`/`data-theme="dark"` overrides in `tokens.css`/`theme.ts` must be **removed**, not left in place with stale pre-redirect colors — a stale dark theme would look more broken than no dark theme for OS-dark-mode users. Reinstating dark mode later requires a fresh product decision and new `DESIGN.md` token values, not a revival of the old teal-based dark palette.

**Rationale:** Story 1.2 is already built (`review` status) with live dark-mode tokens; the UX redirect drops the requirement, so the code must be explicitly updated, not silently left inconsistent.

### Story 1.4 — Configure Application Authentication Method

ADD (after the existing "Username & Password" AC clause):

> **`[ADDED 2026-07-27]` Given** a user filling out the Connect App form, **when** they open the Authentication method dropdown, **then** it offers exactly three options — **Username & Password**, **API Key**, **OAuth Client Credentials** — each revealing its own credential field(s) on selection (username+password fields; a single API Key field). `[GAP]` OAuth Client Credentials' own field set is unconfirmed — the reference UX reveals nothing further for it; needs explicit confirmation before implementation, not an invented Client ID/Secret pair.

**Unchanged:** the SSO/MFA provisional branch AC and PRD Open Question 8 — v3 does not address SSO, so this stays exactly as flagged.

**Rationale:** confirms the concrete three-option set from `prototype-v3.html`; previously the story only described the "Username & Password" happy path plus a still-open SSO/MFA branch, with no confirmed full option list.

### Story 4.1 — Generate Scenarios for a Discovered Journey

ADD:

> **`[ADDED 2026-07-27]` Given** a generated Scenario, **when** the platform evaluates its required Test Data fields, **then** it computes a readiness status — **Ready** if every required field has a value, otherwise **Needs Data** — shown as a status pill on the Scenario's list row and in its detail panel, recomputed live (no separate save step) the instant a required field is filled or cleared. **And** the Review Scenarios screen offers a 3-way filter (All / Ready / Needs Data) above the list, filtering which Scenarios are shown without altering which exist.

**Rationale:** adopted from `prototype-v3.html` as an additive detail — doesn't conflict with any locked decision, and makes the existing "fill in Test Data" workflow navigable at scale.

### Story 4.2 — Generate Playwright Test Assets via a Named Test Suite

OLD:
> The screen the user sees immediately after clicking "Generate Test Suite" (i.e., whether the prior code-viewer + `<details>` disclosure pattern survives) was not reachable during UX review — `[GAP]`, retained as last-confirmed spec pending re-verification.

NEW:
> **`[RESOLVED 2026-07-27]`** The screen shown immediately after clicking "Generate Test Suite" is confirmed: a **Suite Generated** screen showing a hero card (suite name, "Generated {N} test cases across {N} journeys · Est. runtime {X}"), three stat tiles (test cases / journeys covered / est. runtime), and a collapsible **Generated Tests** list grouped by generated file, each group expandable to a per-scenario row (type badge, name, a secondary "Code" button). This screen also hosts the "Download Test Suite" action (Story 4.3) and a "Go to Dashboard" button, which returns to Home — there is no separate Dashboard screen.

**Rationale:** `prototype-v3.html`'s Suite Generated screen resolves this story's previously-flagged `[GAP]` with a confirmed, concrete spec.

### Story 4.3 — Download a Generated Test Suite

No AC change. Cross-reference only: its "Test Suites Generated screen" is now fully specified by Story 4.2's resolved gap above.

## 5. Implementation Handoff

**Scope classification: Moderate** — backlog reorganization (story status + AC changes) and PO/DEV coordination, no PRD/architecture replan.

**`[CORRECTED 2026-07-27, same day]`** The original version of this section under-scoped the visual-identity redirect's impact — it correctly identified the 4 stories with genuine AC changes, but treated the color/font/shadow redirect as a purely implicit, untracked side effect of the shared token file. Per explicit user direction, every already-built UI-bearing story is now formally reopened, split into two tiers:

**Tier 1 — behavioral AC changes (full dev-story rework):**

| Story | Current status | New status | Owner |
|---|---|---|---|
| 1-2-sign-in-organization-scoped-workspace | done | **in-progress** | Developer agent (dev-story) |
| 1-4-configure-application-authentication-method | review | **in-progress** | Developer agent (dev-story) |
| 4-1-generate-scenarios-for-an-approved-journey | review | **in-progress** | Developer agent (dev-story) |
| 4-2-generate-playwright-test-assets-from-scenarios | ready-for-dev | **in-progress** | Developer agent (dev-story) |

**Tier 2 — visual restyle only, no AC change (verify against new `DESIGN.md` tokens):**

| Story | Current status | New status | What's visually stale |
|---|---|---|---|
| 1-3-onboard-an-application-basic-details | review | **in-progress** | Connect App form — accent/font/shadow |
| 1-6-dynamic-browser-tab-branding | review | **in-progress** | Top-bar brand-mark/wordmark restyle |
| 2-1-start-a-discovery-run | review | **in-progress** | Discovery Progress spinner/card |
| 2-4-session-expiry-handling | review | **in-progress** | Re-authentication prompt |
| 2-7-business-oriented-import-progress-display | review | **in-progress** | Discovery Progress display |
| 3-1-review-queue-candidate-list-evidence-panel | review | **in-progress** | List rows, detail panel, badge/kebab-menu/icon-button now formally specified; new (non-committal) reference-screenshot placeholder column |
| 3-4-rename-delete-a-journey-capability | review | **in-progress** | Kebab-menu now formally specified |

**Unaffected:** `4-3-download-a-generated-test-suite` (not yet built — will be built directly against the current spec, nothing stale to restyle) and backend/infra-only stories with no UI surface (1-1, 2-2, 2-3, 2-5, 2-6, 2-8).

**Global, one-time task (still applies, underlies both tiers):** update `apps/web/src/tokens.css`/`theme.ts` to `DESIGN.md`'s new token values (colors, typography, rounded, spacing, shadows) and remove the dark-mode override blocks. This cascades visually to every screen, but each Tier 2 story still needs its own dev-story pass to verify the now-formally-specified components (badge, kebab-menu, icon-button, top-bar, status-pill) actually match spec, not just inherit colors correctly.

**Success criteria:** Tier 1's 4 stories re-pass dev-story + code-review against their new ACs. Tier 2's 7 stories re-pass a visual-parity dev-story pass (no AC diff, but explicit sign-off that the screen matches current `DESIGN.md`/`EXPERIENCE.md`). `4-3` implements fresh against 4.2's now-confirmed Suite Generated screen home.
