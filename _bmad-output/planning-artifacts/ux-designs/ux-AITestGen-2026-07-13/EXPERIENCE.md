---
name: Application Intelligence Platform
status: final
updated: 2026-07-15
sources:
  - "../../prds/prd-AITestGen-2026-07-13/prd.md"
  - "../../briefs/brief-AITestGen-2026-07-12/brief.md"
  - "../../research/market-application-intelligence-platform-research-2026-07-12.md"
---

# Application Intelligence Platform — Experience Spine

> `DESIGN.md` is the visual identity reference; this spine is the experience — information architecture, behavior, states, and flows. Where this file describes a visual property, `DESIGN.md` wins on conflict. Composition reference: `mockups/prototype-v2-standalone.html` (current, 2026-07-15 — a single-application guided pipeline; supersedes `mockups/prototype-v1.html`'s 11-screen nav-rail shell, kept in the mockups folder for history only).

> **`[NOTE FOR PM/ENG — 2026-07-15]`** This revision reflects a confirmed, intentional narrowing of V1 scope: the multi-application nav-rail shell (Applications list, App Overview/Capability Map, Dashboard, Settings, Connect to CI/CD) is cut. The product is now a single-application guided pipeline. This is a UX-and-product-level decision made together with the user; the PRD, architecture, and epics/stories are being updated to match via a separate `bmad-correct-course` pass — treat this file as the source of truth for the *new* IA, and treat any remaining PRD/architecture text describing the old shell as stale until that pass lands.

## Foundation

Desktop web app only — no mobile or tablet form factor in V1. This was an explicit Discovery decision, not an oversight: the product's primary jobs (reviewing a discovered Journey against its evidence trail, reading a dense coverage table) assume a real monitor and a keyboard, and building responsive parity for a V1 whose review workflows are inherently data-dense would spend effort the product doesn't need yet.

**WCAG is the explicit accessibility bar.** Not SOC2-style compliance signaling, not a governance-product visual language — the brief and PRD are clear that the product's positioning runs *away* from that register (see `{DESIGN.md#Brand & Style}`). Accessibility here means real behavioral commitments (focus visibility, keyboard operability, contrast), not a compliance badge.

The product's core entity model — Application → Discovery Run → Capability/Journey → Scenario → Test Asset — is defined in full in PRD §3 (Glossary) and is not restated here. Two structural facts shape everything below: **only human-approved Journeys and Capabilities enter the Trusted Knowledge Model** (PRD FR-14), and every candidate Journey the platform ever shows a reviewer is traceable back to the specific pages, actions, and API calls discovery actually captured (PRD FR-8 consequence). This traceability requirement is why Review Journeys is built as a two-pane list-plus-evidence pattern rather than a flat approve/reject list — see Review & Trust Model.

## Information Architecture

Visual reference: `mockups/prototype-v2-standalone.html` (current, 2026-07-15 — click through it: sign in, then either card on Home).

**Six screens** (2026-07-15, confirmed cut from the earlier 11-screen shell): one pre-authentication (Sign In), one cross-application landing (Home), and a 4-step guided pipeline scoped to a single Application. There is no persistent nav rail — top-level navigation *is* the pipeline stepper described in `{DESIGN.md#Components}`.

| Screen | Reached from | Status |
|---|---|---|
| Sign In | App open, unauthenticated | Confirmed |
| Home | Sign-in (default landing) | Confirmed — 3 action cards: "Start a New Project," "Managed Applications," "Watch a Product Demo" |
| Connect App (pipeline step 1) | Home ("Start a New Project" or "Managed Applications") | Confirmed |
| Discover Journeys (pipeline step 2) | Connect App submission | Confirmed |
| Review Scenarios (pipeline step 3) | Discover Journeys → "Continue to Scenarios" | Confirmed |
| Generate Suite (pipeline step 4) | Review Scenarios → "Continue to Generate Suite" | Confirmed up to the generation form; the resulting/post-generation screen was not reachable during UX review — `[GAP]` |

**Cut entirely, confirmed intentional (2026-07-15):** the multi-application Applications list (with hero-stat strip), App Overview / Capability Map, Generated Tests' standalone code-review screen, Connect to CI/CD, the cross-application Dashboard, and Settings. No replacement screen exists for any of these in the current reference prototype. See the note at the top of this file — PRD/architecture/epics-stories are being updated to match in a separate pass.

**Primary flow:** Home → Connect App → Discover Journeys → Review Scenarios → Generate Suite. Still a guided linear workflow, now collapsed from nine onboarding-through-proof screens into four, with the multi-application "portfolio" layer (list all Applications, roll up coverage across them) removed rather than deferred to a later screen.

**Naming rule — function-first labels — still holds.** Every screen name states what a user *does* there: "Connect App," "Discover Journeys," "Review Scenarios," "Generate Suite." This is a continuation of the same discipline that produced "Discovery Progress" over "Discovery Run" in the prior revision, not a new rule.

**Breadcrumb / app-name context rule — narrowed.** The top bar shows the current Application's name plus an environment badge (e.g. "Staging") on all four pipeline-step screens, since every one of them is now inherently scoped to a single Application. It is suppressed on Sign In and Home, the only two screens that are pre-Application or cross-Application.

## Review & Trust Model

This is the product's central mechanic. Its shape changed on 2026-07-15 — the two-action-set restriction below is **retired**, confirmed as an intentional scope expansion (prototype wins over the prior PRD-level cut; PRD/architecture/epics-stories are being updated to match in a separate `bmad-correct-course` pass):

**1. Journey review now supports rename, edit, and remove via a per-row `⋯` menu** (Discover Journeys screen: "Rename, edit, or remove any journey before generating scenarios"). This supersedes the earlier four-action-only rule (Approve/Rename/Reject/Delete, no composition edit). `[GAP]` the exact edit affordance — what "editing" a Journey's composition actually lets a reviewer change — was not reachable during UX review (the `⋯` menu wasn't opened); needs confirmation before implementation. **Merging two Journeys into one remains out of scope** — nothing in the new prototype suggests combining duplicates, only acting on them individually; a duplicate candidate should still be edited or removed on its own, not merged with another.

**2. Generated Scenarios now support the same rename/edit/remove pattern** (Review Scenarios screen: "Rename, edit, or remove scenarios before generating your suite"), superseding the earlier view-only rule. Selecting a scenario shows its full detail — test steps, a Test data table (field/value pairs), and an Expected result — a materially richer per-scenario view than the prior mono-typed evidence-only panel. `[GAP]` whether an edited scenario's Test data/steps are actually used for Playwright generation, or the edit is cosmetic (e.g., renaming/annotation only), was not confirmed.

**Evidence traceability remains the mechanism that makes review trustworthy.** Every candidate Journey a reviewer sees is backed by the literal pages, actions, and API calls discovery captured for it (PRD FR-8 consequence). In the current prototype this is surfaced as a numbered step list (route, method, and a stage badge like "Login" or "MFA Verification" per step) rather than the prior flat mono-typed evidence panel — a more structured, less raw presentation, but the same underlying commitment: a reviewer should never have to take an inferred Journey's business-language name on faith.

By product decision (PRD §5 Non-Goals, **not** revisited by this change), there is still **no AI confidence or risk score anywhere in this workflow**, and **no reviewer prioritization or importance-marking** — every approved Journey is treated with equal weight. Nothing in the new prototype contradicts this; design and copy must continue to avoid "high confidence" language or subtle visual weighting that reads as a priority signal.

## Voice and Tone

Plain, function-first, factual. No exclamation points, no emoji, no celebratory language ("Success!", "Great job!") anywhere in the product — the product's whole premise is that a human is exercising judgment over AI output, and cheerful copy undercuts that seriousness. Business nouns from the PRD glossary (§3) — **Application**, **Capability**, **Journey**, **Scenario**, **Test Asset**, **Trusted Knowledge Model** — are capitalized as proper product nouns everywhere in the UI, consistently with how the PRD itself treats them.

Errors, hints, and constraints state facts plainly and explain the *why*, not just the *what* — the approved prototype already does this correctly in several places, and these are the calibration examples for any new copy:

| Do | Don't |
|---|---|
| "Review queue cleared. All candidates from the Jul 12 run have been triaged." — empty state as a factual status report | "You're all caught up! 🎉" |
| "Session state expires per your identity provider's policy — re-upload when a discovery run reports an authentication failure." — fact + consequence, no apology | "Oops, your session expired!" |
| "This run will automatically be marked **Incomplete**." — names the mechanism, not just the outcome | "Uh-oh, we ran out of time!" |
| "Discovery only targets non-production environments — production URLs are blocked at setup." — constraint and reason in one breath | "Don't worry, we'll handle it for you!" |
| "Regenerates from scratch — not a diff/patch." — names the mechanism plainly, no reassurance needed | State a constraint with no explanation, or an apology with no fact |
| Capitalize Journey / Capability / Application / Scenario / Test Asset as proper nouns | Lowercase business nouns inconsistently, or invent synonyms mid-product ("flow," "test case") |
| Reviewer-facing copy assumes technical fluency (routes, API calls, status codes) | Copy talks down, over-explains basic web concepts, or adds encouragement/hype |

## Component Patterns

Behavioral only — visual specs live in `{DESIGN.md#Components}`.

| Component | Use | Behavioral rules |
|---|---|---|
| Pipeline stepper | Global (all 4 pipeline screens) | Click navigates between completed steps; the active step is highlighted per `{DESIGN.md#Components}`. Replaces the retired nav-rail link pattern as primary navigation. `[GAP]` whether a completed step is clickable to jump back was not confirmed. |
| List row + `⋯` menu | Discover Journeys, Review Scenarios | Click/select loads that item's detail into the right-hand panel (replacing the previous selection, not stacking). Every row — not just "undecided" ones — carries a `⋯` menu for rename/edit/remove; see `{#Review & Trust Model}` for the 2026-07-15 scope change this reflects. `[GAP]` post-decision row treatment (e.g., does an edited/removed row visually mute like the old "decided row" pattern?) was not confirmed. |
| Detail panel | Discover Journeys, Review Scenarios | Not sticky-confirmed in the new layout (unlike the prior evidence panel) — `[GAP]`, re-verify scroll behavior. Discover Journeys' panel shows a numbered step list (route/method + stage badge per step); Review Scenarios' panel shows Test steps, a Test data table, and Expected result. Content is prose-and-table, not exclusively monospace evidence — narrower than `{DESIGN.md#Typography}`'s original mono-only evidence rule; `{typography.mono-inline}` still applies to any raw route/API text within these panels. |
| Connect App form | Connect App | A single-page form (no internal wizard/stepper) — Application name, Base URL, Environment select, Authentication method select, credential fields, one submit CTA ("Connect Application"). Authentication method is a plain `<select>`, not the prior option-card/radio pattern. `[GAP]` no SSO/MFA session-handoff step is present — unconfirmed whether PRD Open Question 8 was resolved to "not needed" or is simply absent from this export. |
| Generate Suite panel | Generate Suite | Form (Suite name, Target environment, Execution radio group) beside a static "Suite summary" card that mirrors the form's current values plus a generate CTA. Execution is a real radio selection (`Run immediately` default-selected) but — per `{DESIGN.md#Components}`'s Generate Suite panel note — its downstream behavior is a placeholder, not a confirmed spec. |
| Status pill | — | `[GAP]` not reachable in the current reference prototype; retained from the prior revision pending re-verification. See State Patterns. |

`[NOTE FOR PM/ENG — 2026-07-15, superseded]` The prior revision's Add Application wizard "Authenticate" step (paste session-state JSON, or reference a `storageState.json` file) no longer exists — Connect App is now a single-page form with a plain Authentication method `<select>` and no visible SSO/MFA session-handoff step at all. PRD Open Question 8 (the SSO/MFA session-handoff mechanism) is **still unresolved**, and it's now unclear whether the new prototype intends "not needed for V1" or simply omitted this step from the exported flow. This must be confirmed explicitly — do not read the absence of the step as an answer to Open Question 8.

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| Discovery running / hits time budget (PRD FR-7) | `[GAP]` no discovery-in-progress screen was reachable in the current reference prototype — the Connect App → Discover Journeys transition happened instantly against pre-seeded demo data. The prior "Running" → "Incomplete" status-pill transition is retained here as the last-confirmed spec (PRD FR-7 is unchanged), but needs re-verification against a real in-progress state once one exists in the prototype or implementation. |
| Journey/Scenario row before action | Discover Journeys, Review Scenarios | Rows show their name, a step/scenario count or type badge (`Happy Path`/`Negative Path`/`Edge Case` on Review Scenarios), and a `⋯` menu. `[GAP]` post-edit/remove row treatment not confirmed — see Component Patterns. |
| Discover Journeys / Review Scenarios list cleared | Discover Journeys, Review Scenarios | `[GAP]` not reachable during UX review (both screens were seen mid-list, never at zero remaining items). The prior empty-state pattern (confirmation line + Approved/Rejected count pair) is retained as last-confirmed spec pending re-verification. |

## Interaction Primitives

- **Click to navigate.** Every nav-rail link, and every clickable table row (Applications, Dashboard), is a single click to its destination. There is no double-click, no drag, no multi-select anywhere in V1.
- **`<details>` progressive disclosure** for dense technical content — generated code, pipeline snippets — per Component Patterns above. This is a real, intended interaction primitive for this product, not just a prototype convenience.
- **Sticky evidence panel on scroll** — the Review Journeys evidence panel stays pinned in the viewport as the row list scrolls, so evaluating evidence never requires losing your place in the list.
- **Row hover** highlights the row background and, on clickable table rows (Applications, Dashboard), switches the cursor to a pointer as an affordance cue. On Review Journeys, the four row actions are **always visible** on any undecided row rather than hidden behind hover — they gate a required decision, so hiding them behind a hover state would work against discoverability and against keyboard/touch users who don't hover at all.
- **Prototype fidelity note (2026-07-15):** the current reference prototype (`prototype-v2-standalone.html`) is a real bundled React SPA with client-side state, unlike the prior revision's no-JavaScript radio/CSS trick — its click-driven navigation and form controls are much closer to how the real product would behave, though it runs against pre-seeded demo data with no live backend (submitting Connect App, for instance, always yields the same fixed 15 Journeys). Treat its interaction behavior as a stronger signal than the prior prototype's, but its "Sign in" and "Connect Application" submissions are not proof of real request/response handling.

## Accessibility Floor

Behavioral commitments; visual contrast lives in `{DESIGN.md#Colors}`.

- **WCAG 2.1/2.2 AA is the floor** across the entire desktop surface — not a stretch goal, and not SOC2/governance-style compliance signaling (see Foundation).
- **Focus-visible on every interactive element** — buttons, nav-rail links, inputs, selects, textareas, and `<summary>` disclosure triggers all get a visible focus ring. This is a behavioral requirement this file states; the ring's exact color and offset are DESIGN.md's to specify.
- **Keyboard operability for selection controls.** Connect App's Environment and Authentication method are native `<select>` elements (natively keyboard-operable). Generate Suite's Execution choice is a real `<input type="radio">` group. Neither should become a `<div onclick>` fake in implementation. `[GAP]` the prior revision's option-card/provider-card visual pattern (bordered card + radio) is not confirmed to still exist anywhere in the new IA — CI/CD provider selection was one of its two uses and that screen is cut; re-verify if it survives anywhere.
- **Tab order matches visual order** on every screen — top bar, then pipeline stepper, then main content, top to bottom, left to right within the two-pane Discover Journeys / Review Scenarios layouts (list before detail panel).
- **Label/caption contrast is a standing requirement, not a one-time fix.** DESIGN.md documents the specific token-level fix (routing all real label/caption text through `{DESIGN.md#colors.ink-muted}`, ~5:1, and reserving the faint tier for decorative-only use) after a real AA-contrast failure was caught during Discovery. This file's requirement is the "why it matters": any new screen or component that introduces new label/caption text must use the AA-passing muted tier, full stop — this is not negotiable per-component judgment.

## Inspiration & Anti-patterns

- **Lifted from Linear, Datadog, GitHub, Harness, Grafana Cloud (the explicit reference cluster):** clean, light, airy chrome; minimal decoration; hairline borders over shadows; dense-but-legible data tables; a single restrained accent color used sparingly and consistently for "this is active/primary" rather than scattered across the UI.
- **Rejected — traditional ALM tools, legacy QA management suites, compliance-heavy governance products:** these were named explicitly as the *away-from* direction. Their visual signature — bureaucratic form density, heavy chrome, "enterprise gray," governance-badge iconography — actively undercuts this product's positioning, which sells trust through transparency and inspectability, not through looking like a compliance artifact.
- **Rejected — the first comparison-sketch pass** (`{DESIGN.md#Brand & Style}` has the full story): the lesson carried forward isn't about any one visual element — it's that this product needed one committed, finished-looking direction presented with conviction, not a menu of rough alternatives.
- **Rejected — merge/split Journey actions:** the approved brief's narrative described a reviewer who "merges duplicates," but this was cut from the PRD for V1 (§4.4) to keep the review workflow to four simple, unambiguous actions. Don't reintroduce this as a "quick UX win" without a product-level decision first — see Review & Trust Model.
- **Rejected — reviewer prioritization/importance-marking:** the approved brief also described a reviewer who "marks what matters most to the business." V1 has no such affordance; every approved Journey is equal-weighted, by explicit PRD decision (§5 Non-Goals). No priority flag, star, or ranking control anywhere near a Journey or Capability.
- **Rejected — any AI confidence/risk score UI:** named explicitly in PRD §5 as a deliberate cut from the approved brief's stated V1 outcomes. This is a recurring temptation for "helpful" UI (e.g., a subtle confidence bar on a candidate Journey) that must be resisted at the product-decision level, not just the visual level.

## Key Flows

### Flow 1 — Maria reviews her Application's discovered journeys (PRD UJ-1, updated 2026-07-15)

Maria Colón, QA Director at a mid-size insurer, is connecting the Claims Processing App for the first time.

1. Maria signs in, lands on **Home**, and clicks "Start a New Project."
2. On **Connect App**, she fills in the Application name, Base URL, environment, and credentials, then submits.
3. On **Discover Journeys**, she sees the discovered candidates (the reference prototype shows 15 for a demo banking app) in a list, each with a step count. Selecting one loads its discovered step-by-step flow (route, method, stage badge) in the detail panel, so she can confirm the AI's inference before deciding.
4. She uses each row's `⋯` menu to **rename** a generically-labeled candidate and **remove** ones she doesn't want carried forward — see `{#Review & Trust Model}` for the current (2026-07-15) action set, which is broader than the prior four-action-only rule.
5. She continues to **Review Scenarios**, where generated test scenarios appear grouped by their source Journey, each tagged `Happy Path`/`Negative Path`/`Edge Case`; selecting one shows its test steps, test data, and expected result. She can rename/edit/remove scenarios here too before proceeding.
6. **Climax:** she continues to **Generate Suite**, names the suite, confirms the target environment, and generates it against the suite summary (journey/scenario counts, estimated runtime).
7. **Resolution:** `[GAP]` what she sees immediately after clicking "Generate Test Suite" was not reachable during UX review — needs confirmation before this step can be called complete.
8. **Edge case — no longer confirmed:** the prior revision's "Discovery Run hits its time budget, map marked Incomplete" edge case (PRD FR-7) has no confirmed screen to attach to now that there's no observed in-progress discovery state — see State Patterns.

### Flow 2 — Devon checks release readiness before sign-off (PRD UJ-2) — `[NOTE FOR PM/ENG — 2026-07-15, BLOCKED]`

**This flow currently has no UI to attach to.** The cross-Application executive Dashboard it depends on — KPI rollups, by-Application coverage table, the "N pending test" gap flag that was this flow's entire climax — is one of the screens confirmed cut from V1 scope on 2026-07-15. PRD UJ-2 (Devon, Engineering Leader, deciding release readiness from a coverage view) is a **named journey in the PRD itself**, not just a nice-to-have screen; cutting its only supporting surface means either (a) this user journey is also being cut from V1 — which the PRD does not yet say — or (b) it needs a new home somewhere in the 4-step pipeline that hasn't been designed yet. This needs explicit product-level resolution via the PRD update, not a UX-only call; the flow's steps below are preserved from the prior revision as a record of the *intent*, not as a current spec:

1. ~~Devon signs in and opens Dashboard...~~
2. ~~He scans the KPI row and by-Application coverage table...~~
3. ~~He spots an inline warning flag ("1 pending test")...~~
4. ~~He factors that gap into his release decision...~~

