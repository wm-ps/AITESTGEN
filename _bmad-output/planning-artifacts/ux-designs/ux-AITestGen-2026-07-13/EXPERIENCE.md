---
name: Application Intelligence Platform
status: final
updated: 2026-07-27
sources:
  - "../../prds/prd-AITestGen-2026-07-13/prd.md"
  - "../../briefs/brief-AITestGen-2026-07-12/brief.md"
  - "../../research/market-application-intelligence-platform-research-2026-07-12.md"
---

# Application Intelligence Platform — Experience Spine

> `DESIGN.md` is the visual identity reference; this spine is the experience — information architecture, behavior, states, and flows. Where this file describes a visual property, `DESIGN.md` wins on conflict. Composition reference: `mockups/prototype-v3.html` (current, 2026-07-27 — a bundled SPA export using a custom template DSL over `this.state`; supersedes `mockups/prototype-v2-standalone.html`, kept in the mockups folder for history only alongside `prototype-v1.html`).

> **`[NOTE FOR PM/ENG — 2026-07-27]`** This revision reconciles the locked (2026-07-21) spine against `prototype-v3.html`. Full reconciliation detail, including what was rejected and why, lives in `reconcile-prototype-v3.md`. Three kinds of change happened in this pass: (1) **adopted** — the visual identity redirect (see `DESIGN.md`), the Review Scenarios ready/needs-data filter, the Suite Generated screen (resolving a prior `[GAP]`), and a clarified Landing/existing-Application rule; (2) **rejected as prototype drift** — a reintroduced Journey-level Edit action, a raw scrolling discovery live-feed, a single-TypeScript-file suite download, a "Discovery Attention" approve/skip gate, and a "Workspace" multi-tab home screen with live pass/fail results; (3) **carried forward unchanged** — everything from the 2026-07-15/2026-07-21 revisions not named above, including the four-step pipeline shape, the Review & Trust Model's rename/delete-only Journey action set, and Sign In. **Corrected this pass (2026-07-27):** Key Flow 3 (formerly framed as UJ-2's "unresolved Dashboard gap") was miscast as a still-open item awaiting product resolution — the current PRD (updated 2026-07-21) already disposed of UJ-2 as removed in full on 2026-07-15. See Key Flows below for the correction.

## Foundation

Desktop web app only — no mobile or tablet form factor. Unchanged.

**WCAG is the explicit accessibility bar.** Unchanged — see Accessibility Floor.

The product's core entity model — Application → Discovery Run → Capability/Journey → Scenario → Test Asset — is defined in full in PRD §3 (Glossary) and is not restated here. Every discovered, non-deleted Journey and Capability enters the Trusted Knowledge Model automatically (PRD FR-14 — there is no human approval gate; deletion, FR-13, is the only exclusion mechanism), and every candidate Journey the platform shows a reviewer is traceable back to the specific pages, actions, and API calls discovery actually captured (PRD FR-8 consequence).

**Sign In is unchanged.** It is not in scope of this revision beyond the visual restyle documented in `DESIGN.md` (the login canvas, the two-column layout with a product intro on the left and the sign-in card on the right). Its field set, "Continue with Single Sign-On" link, and validation are unaffected.

## Information Architecture

**Six screens**, unchanged in count and shape from the 2026-07-15/2026-07-21 revisions: one pre-authentication (Sign In), one cross-application landing (Landing), and a 4-step guided pipeline scoped to a single Application. There is no persistent nav rail — top-level navigation *is* the pipeline stepper.

| Screen | Reached from | Status |
|---|---|---|
| Sign In | App open, unauthenticated | Confirmed, unchanged |
| Landing | Sign-in (default landing) | Confirmed — see State Patterns for the two distinct empty/non-empty treatments |
| Connect App (pipeline step 1) | Landing ("+ Create New Project" or an existing Application card) | Confirmed |
| Discover Journeys (pipeline step 2) | Connect App submission, or resuming an existing Application | Confirmed |
| Review Scenarios (pipeline step 3) | Discover Journeys → "Continue to Scenarios" | Confirmed |
| Generate Suite (pipeline step 4) | Review Scenarios → "Generate Test Suite" | Confirmed, now including the post-generation **Suite Generated** screen — resolves the prior `[GAP]` for what appears after generation completes |

**Confirmed still cut, not reintroduced (2026-07-27):** `prototype-v3.html` adds two new screens beyond these six — a "Discovery Attention" approve/skip gate for uncertain or missing-field discoveries, and a "Workspace" screen (Overview / Test Suite / Runs / Application tabs, including a live Passed/Failed test-execution view). Both are rejected in full; see the note at the top of this file and `reconcile-prototype-v3.md`. No replacement screen exists for either.

**Primary flow:** Landing → Connect App → Discover Journeys → Review Scenarios → Generate Suite → Suite Generated. Unchanged in shape from the prior revision, now with its terminal screen filled in.

**Naming rule — function-first labels — still holds,** unchanged.

**Breadcrumb / app-name context rule** — unchanged: the top bar shows the current Application's name plus an environment pill on all four pipeline-step screens; suppressed on Sign In and Landing.

**Browser tab branding rule** (FR-32, Story 1.6) — unchanged, same suppression logic as the breadcrumb rule.

## Review & Trust Model

This remains the product's central mechanic, and its final action sets are **unchanged and reconfirmed** against `prototype-v3.html`:

**1. Journey review supports rename and delete only, via a per-row `⋯` menu** (Discover Journeys screen). `prototype-v3.html`'s underlying JS retains a vestigial `startEditJourney` function (a description-edit mode, wired to nothing visible in the rendered menu — only Rename and Delete are actually bound to on-screen buttons), which the 2026-07-27 reconciliation explicitly rejects as prototype drift rather than a reintroduced product decision — see `reconcile-prototype-v3.md`. There is still no approve/reject step; every discovered, non-deleted Journey is already in the Trusted Knowledge Model from the moment it's created. **Merging two Journeys into one, or editing a Journey's composition, remains out of scope** (PRD §4.4 Non-Goal).

**2. Generated Scenarios support rename, edit, and remove** (PRD FR-29), unchanged. `prototype-v3.html`'s Review Scenarios row menu itself renders only Rename/Delete, same as Journeys — but the richer "edit" surface for a Scenario is its detail panel's inline **Test Data** field-editing (see Component Patterns), which the prototype does render fully. `[GAP]` whether an edited Scenario's Test Data/steps are actually used for Playwright generation, or the edit is cosmetic, was not confirmed by this reconciliation pass either — carried forward from the prior revision.

**New this revision — a Scenario readiness signal, additive, not previously in this file:** each Scenario now carries a **Ready** vs **Test Data Required** status, computed from whether every required Test Data field has a value. Review Scenarios adds a 3-way filter (All / Ready / Needs Data) above the list, and a Scenario missing required data shows an inline warning banner in its detail panel ("Test data required — fill in the highlighted fields below to mark this scenario Ready"), plus a per-field "Required to generate this test" note under any still-empty required input. This does not conflict with any locked decision — it's an additive detail on the existing Story 4.1 review screen, adopted per the 2026-07-27 reconciliation.

**Evidence traceability remains the mechanism that makes review trustworthy,** unchanged — surfaced as a numbered step list (route, method, and a stage tag per step) on Discover Journeys, now paired with a sticky reference-screenshot placeholder column (see Component Patterns) that wasn't previously specified.

By product decision (PRD §5 Non-Goals), there is still **no AI confidence or risk score anywhere in this workflow**, and **no reviewer prioritization or importance-marking**.

## Voice and Tone

Unchanged from the prior revision. Plain, function-first, factual. No exclamation points, no emoji, no celebratory language. Business nouns from the PRD glossary (§3) — **Application**, **Capability**, **Journey**, **Scenario**, **Test Asset**, **Trusted Knowledge Model** — capitalized as proper product nouns.

One addition worth naming explicitly given the new Suite Generated screen: its copy ("Generated {N} test cases across {N} journeys · Est. runtime {X}") stays in the same factual, count-forward register as the rest of the product — a status report, not a celebration, even though `DESIGN.md`'s gradient hero card gives it more visual weight than a typical screen. Visual emphasis and celebratory copy are independent; the copy discipline does not loosen just because the card got a gradient.

| Do | Don't |
|---|---|
| "Review queue cleared. All candidates from the Jul 12 run have been triaged." — empty state as a factual status report | "You're all caught up! 🎉" |
| "Generated 47 test cases across 12 journeys · Est. runtime 6m 40s." — count-forward, factual | "Woohoo! Your tests are ready!" |
| "All journeys have been removed." — bare factual state, no apology, no CTA invented | "Looks like there's nothing here — want to start over?" |
| Capitalize Journey / Capability / Application / Scenario / Test Asset as proper nouns | Lowercase business nouns inconsistently, or invent synonyms mid-product |
| Reviewer-facing copy assumes technical fluency (routes, API calls, status codes) | Copy talks down, over-explains basic web concepts, or adds encouragement/hype |

## Component Patterns

Behavioral only — visual specs live in `{DESIGN.md#Components}`.

| Component | Use | Behavioral rules |
|---|---|---|
| Top bar | Global — every authenticated screen | **New row, not previously documented here (visual spec only lived in `{DESIGN.md#Components}`).** Brand mark + wordmark sit at the left on every authenticated screen; clicking either returns to Landing from anywhere, including mid-pipeline. Once inside an Application's pipeline (the 4 pipeline-step screens only), a divider, the Application's name, and an environment pill additionally render beside the brand mark — suppressed on Sign In and Landing, per the breadcrumb rule in Information Architecture. A circular user-initials avatar sits at the far right on every authenticated screen (including Landing); clicking it opens a menu with the user's name, email, and a Log out action. The browser tab mirrors the same suppression logic (FR-32, Story 1.6): pipeline screens show the connected Application's name and favicon (or the platform default if none was fetched), Sign In and Landing show the platform default. |
| Pipeline stepper | Global (all 4 pipeline screens) | Unchanged. Click navigates between completed steps; the active step is highlighted. `[GAP]` whether a completed step is clickable to jump back was not confirmed in this pass either — carried forward. |
| List row + `⋯` menu | Discover Journeys, Review Scenarios | Click/select loads that item's detail into the right-hand panel, replacing the previous selection. Every row's `⋯` menu is **always visible**, not hover-gated. Both screens' row menus render **Rename** and **Delete** only — see Review & Trust Model above for why Scenarios' fuller edit/remove capability (FR-29) lives in the detail panel instead of a third menu item. |
| Kebab menu (`⋯` trigger) | Discover Journeys, Review Scenarios list rows | **New row — dedicated behavioral coverage; visual spec in `{DESIGN.md#components.kebab-menu}`.** Click opens a two-item dropdown (Rename, Delete) anchored below the trigger; the trigger itself carries a visible focus outline per Accessibility Floor. The dropdown closes on selecting an item, clicking outside it, or pressing Escape. Always visible, never hover-gated (see Interaction Primitives). The Delete item renders and hovers in `{DESIGN.md#colors.danger}` / `{DESIGN.md#colors.danger-wash}` to read as the destructive action. |
| Icon button (generic) | Global — kebab-menu trigger, Generated Tests disclosure expand/collapse chevron, back/close affordances | **New row — dedicated behavioral coverage; visual spec in `{DESIGN.md#components.icon-button}`.** Transparent at rest, fills `{DESIGN.md#colors.border}` on hover, focus-visible outline per Accessibility Floor. Click triggers its one bound action only (open a menu, toggle a disclosure, navigate back) — there is no distinct press/active visual state beyond hover and focus. |
| Badge (Scenario type) | Review Scenarios list rows, Review Scenarios detail panel, Suite Generated per-scenario rows | **New row — dedicated behavioral coverage; visual spec in `{DESIGN.md#components.badge}`.** Purely a non-interactive display label — no click, hover, or focus state of its own. Set automatically at scenario-generation time (FR-16) from the Scenario's type (Happy Path / Negative Path / Edge Case); never user-editable, never triggers a state change on its own. |
| Status pill | Review Scenarios list rows, Review Scenarios detail panel | **New row — dedicated behavioral coverage; visual spec in `{DESIGN.md#components.status-pill}`.** Non-interactive display label computed live from Test Data completeness (see Review & Trust Model) — flips between **Ready** and **Needs Data** the instant a required field is filled or cleared in the detail panel, with no separate save step. Not itself clickable, but drives which Scenarios the Scenario status filter surfaces. |
| Detail panel — Discover Journeys | Discover Journeys | Shows the Journey's name, description, and a numbered step list (route/action + a stage tag per step). New this revision: a sticky **reference-screenshot placeholder** column alongside the step list, labeled "journey screenshot" — a visual stand-in for a real evidence screenshot, not yet backed by a real captured image per this reconciliation; treat as a placeholder pattern to fill with real evidence, not as confirmation that screenshot capture is in scope. |
| Detail panel — Review Scenarios | Review Scenarios | Shows a type badge + a Ready/Needs Data status pill, the Scenario name, a numbered Test Steps list, a **Test Data** callout (labeled field rows, required fields marked, inline warnings for empty required fields), and an **Expected Result** block. |
| Scenario status filter | Review Scenarios | New this revision. A 3-way segmented control (All / Ready / Needs Data) filters the Scenario list by Test Data completeness; does not affect which Scenarios exist, only which are shown. |
| Connect App form | Connect App | A single-page form — Application name, Base URL, Environment select, Authentication method select, then method-specific credential field(s), one submit CTA ("Connect Application"). Authentication method's confirmed option set: **Username & Password, API Key, OAuth Client Credentials** (adopted from `prototype-v3.html` as the concrete Story 1.4 option set). **On submit (PRD FR-31, added 2026-07-21, not previously represented here):** the platform validates the Base URL is reachable (2xx/3xx) before creating the Application record or starting discovery. A network/DNS error or 4xx/5xx response blocks submission — the form stays on Connect App and shows a specific, factual inline error; nothing is created and Discovery Progress never starts. A reachable URL proceeds exactly as onboarding did before this FR existed. See State Patterns below for the failure-state row. `[GAP]` the prototype shows no distinct credential fields for OAuth Client Credentials specifically — needs explicit confirmation of what that method's fields should be, not an invented Client ID/Secret pair. `[GAP]` PRD Open Question 8 (SSO/MFA session-handoff) remains unaddressed by this option set, unchanged from the prior revision — none of the three options is an SSO flow. |
| Generate Suite panel | Generate Suite | Unchanged in shape: a form (Suite name, Target environment, journey/scenario counts) beside a static summary card (an "included Journeys" list and a checklist). Its downstream execution behavior remains a placeholder per the prior revision — not a confirmed spec. |
| Suite Generated | Generate Suite → "Generate Test Suite" | **New this revision — resolves the prior `[GAP]` for what appears after generation.** A hero card (suite name, generated-count summary, "Download Test Suite" button, "Go to Dashboard" button) followed by three stat tiles (test cases / journeys covered / estimated runtime) and a collapsible list of generated tests grouped by file. "Go to Dashboard" is read as **"return to Landing"** — there is no separate Dashboard screen; see Information Architecture. "Download Test Suite" triggers a download of the locked Python (pytest/pytest-playwright) suite-folder project (Story 4.3/FR-34) — the prototype's own literal single-TypeScript-file download behavior is not the real behavior; see `reconcile-prototype-v3.md`. |
| Empty state | Discover Journeys, Review Scenarios, Landing | Two distinct patterns — see State Patterns below for which applies where. |

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| Discovery running / completing (PRD FR-7, FR-33) | Discover Journeys (pre-list) | **Unchanged mechanism**, reconfirmed against `prototype-v3.html`: a centered card (spinner, "Discovering journeys in {Application name}," the current business-language stage label, and a progress bar). It shows exactly one of four business-language stage labels — Initialization, Authentication, Discovery, Analysis — mapped from `DiscoveryRun.stage`, with the paired percentage representing the *previous* stage's completion (0/10/25/75), per the 2026-07-21 correction. `prototype-v3.html` additionally renders a rotating single-line "Currently exploring: {business area}" caption (cycling through area names like "Claims → File a Claim") beneath the stage label — this reconciliation does **not** adopt that rotating caption as a confirmed behavior: it reads as exactly the kind of "raw scrolling technical live-feed of discovered areas" the 2026-07-27 decision explicitly rejects, even though its individual items are business-language phrases rather than raw routes. Discovery Progress therefore stays scoped to the four canonical stage labels only. A restyled 4-up metric-tile row (counts like "Unique routes discovered," "Interactions explored") appears in the prototype alongside the spinner; this is a plausible compatible detail (aggregate counts, not a feed) but is not asserted here as a confirmed product behavior — flagged as an open item, not adopted or rejected outright. |
| Discover Journeys list cleared | Discover Journeys | **Adopted 2026-07-27:** when an Application's Journeys are all deleted, Discover Journeys shows bare centered text — **"All journeys have been removed."** — no title, no icon, no illustration, no CTA. Open item, not yet resolved: whether a recovery CTA (e.g., "Re-run discovery") should exist here is a UX call not made by this reconciliation; the prototype has none, and none is invented. |
| Review Scenarios list cleared | Review Scenarios | New empty-state string observed in the prototype, consistent in style with the above: "No scenarios remain — add journeys back to generate scenarios." Same bare-text pattern, no CTA. |
| Landing, zero Applications onboarded | Landing | Richer empty state: icon badge, "No projects yet" heading, one line of explanatory body copy, and a primary "+ Create New Project" button. This is distinct from the row below and must not be conflated with it. |
| Landing, an Application exists whose Journeys are all deleted | Landing | **Adopted 2026-07-27, correcting a prototype-demo artifact:** the Application's card still appears on Landing exactly as it would with Journeys present (name, journey/scenario counts reading zero, a status label) — clicking it **resumes the guided pipeline**, landing on that Application's Discover Journeys screen, which then shows its own "All journeys have been removed" empty state (the row above). `prototype-v3.html`'s actual behavior — Landing reverting entirely to the zero-Applications "No projects yet" state the moment the one hardcoded demo Application's journey count hits zero — is rejected as a shared-boolean prototype-demo artifact, not a real product rule. A real Application record persists on Landing regardless of its Journey count. |
| Journey/Scenario row before action | Discover Journeys, Review Scenarios | Unchanged: rows show their name, a step/scenario count or type badge, and an always-visible `⋯` menu. `[GAP]` post-edit/remove row treatment not confirmed, carried forward. |
| Connect App reachability check fails (PRD FR-31, added 2026-07-21) | Connect App | **New, not previously represented in this document.** Submitting a Base URL that returns a network/DNS error or a 4xx/5xx response blocks Application creation and the DiscoveryWorkflow start: the form stays on Connect App (no navigation to Discovery Progress), the submit action is treated as blocked/failed, and a specific, factual inline error message is shown (e.g. "Could not reach this URL — check it's correct and reachable"), not a generic failure banner. Reuses the same 2xx/3xx reachability tolerance FR-6(f) already established for a live discovery-time destination — no new concept, just applied one step earlier. |

## Interaction Primitives

- **Click to navigate/act.** Every stepper step, list row, and button is a single click. No double-click, drag, or multi-select.
- **Always-visible row menus,** unchanged — the `⋯` trigger on Journey/Scenario rows is never hover-gated, favoring discoverability and non-hover input methods.
- **Sticky reference column** — new this revision: Discover Journeys' reference-screenshot placeholder column stays pinned in the viewport as the step list scrolls, mirroring the sticky-evidence-panel discipline the product has used since the 2026-07-15 revision's Journey/Scenario detail panels.
- **Inline field editing for Test Data,** new this revision: a Scenario's required Test Data fields are edited directly in the detail panel (not behind a separate "edit mode" toggle) — filling a required field updates that field's missing-warning and can move the Scenario from Needs Data to Ready.
- **Prototype fidelity note (2026-07-27):** `prototype-v3.html` is a larger, more elaborate bundled SPA export than `prototype-v2-standalone.html`, still running against pre-seeded demo data with no live backend. Two of its screens ("Discovery Attention," "Workspace") are rejected wholesale as unauthorized scope expansion rather than treated as a stronger signal — see `reconcile-prototype-v3.md`. Treat the six adopted screens' interaction behavior as the current best signal; treat the two rejected screens' code as informative for *what was considered and declined*, not as a spec.

## Accessibility Floor

Behavioral commitments; visual contrast lives in `{DESIGN.md#Colors}`.

- **WCAG 2.1/2.2 AA is the floor**, unchanged.
- **Focus-visible on every interactive element**, unchanged.
- **Keyboard operability for selection controls**, unchanged — Connect App's Environment and Authentication method are native `<select>` elements.
- **Tab order matches visual order**, unchanged.
- **Label/caption contrast is a standing requirement, not a one-time fix — reconfirmed and re-flagged this revision.** `DESIGN.md` documents that `prototype-v3.html` reintroduces the exact contrast failure pattern fixed once already in the 2026-07-15 revision: several genuinely informational captions (Landing's journey/scenario counts, list pagination labels, "No matches." text) render in the decorative-only faint gray tier rather than the AA-passing muted tier. This is called out explicitly so it is caught before implementation rather than silently re-introduced a second time: any string a user needs to actually read must route through `{DESIGN.md#colors.ink-muted}`, full stop, regardless of what color the reference prototype uses for it.

## Inspiration & Anti-patterns

- **Rejected — Journey-level Edit (2026-07-27):** `prototype-v3.html`'s underlying code retains an unused `startEditJourney` function that would open a description-edit mode from the Journey row menu, but no visible button in the rendered template actually triggers it — only Rename and Delete are wired to on-screen controls. Treated as prototype drift (dead code from an earlier build), not a reintroduced product decision. Do not wire it up as a "quick win" without a product-level decision first.
- **Rejected — "Discovery Attention" (2026-07-27):** a new screen in `prototype-v3.html` presenting an approve/skip gate for "uncertain" discovered items and a manual-entry form for "missing" fields, shown between Discovery Progress and Discover Journeys. Dropped entirely — it reintroduces exactly the reviewer-gate/manual-entry pattern the product's Trusted-Knowledge-Model-by-default design (FR-14) was built to avoid, and no story authorizes it. The underlying *idea* — surfacing discovery's own uncertainty about specific fields or candidates — is not without merit and could be reconsidered deliberately later; see `reconcile-prototype-v3.md` for that discussion. It is not built now.
- **Rejected — "Workspace" (2026-07-27):** a new tabbed screen (Overview / Test Suite / Runs / Application) in `prototype-v3.html`, reachable from the top-bar brand mark, including an Overview tab with a health rollup and a "Run Suite" action, and a Runs tab showing live Passed/Failed/Not Run test-execution counts. Dropped entirely, including its non-Runs tabs. The Runs tab specifically implies live test execution plus a CI read-back channel, which the current architecture does not support — coverage stays generated-vs-not only, per the locked stance below. No return-to-existing-Application "home" screen exists right now; Landing plus the pipeline is the whole IA. The health/coverage-rollup *concept* is a reasonable future direction and is discussed further in `reconcile-prototype-v3.md`, but nothing is built from it now.
- **Rejected — raw discovery live-feed (2026-07-27):** see State Patterns above — Discovery Progress stays scoped to four business-language stage labels.
- **Rejected — single-file TypeScript suite download (2026-07-27):** see Component Patterns above — the download stays the locked Python suite-folder project.
- **Carried forward, unchanged from 2026-07-15:** merge/split/edit Journey actions remain out of scope; reviewer prioritization/importance-marking remains out of scope; AI confidence/risk score UI remains out of scope. See PRD §4.4 and §5.

## Key Flows

### Flow 1 — Maria reviews her Application's discovered journeys (PRD UJ-1, updated 2026-07-27)

Maria Colón, QA Director at a mid-size insurer, is connecting the Claims Processing App for the first time.

1. Maria signs in, lands on **Landing**. She has no Applications onboarded yet, so Landing shows the "No projects yet" onboarding empty state; she clicks "+ Create New Project."
2. On **Connect App**, she fills in the Application name, Base URL, environment, and chooses **Username & Password** as her authentication method, then submits — the platform validates the Base URL is reachable (PRD FR-31) before creating the Application or starting discovery; a failed check would keep her on Connect App with a specific inline error, but her URL is reachable, so submission proceeds.
3. **Discovery Progress** shows the four business-language stages in turn (Initialization → Authentication → Discovery → Analysis) with a progress bar — no raw technical feed, no per-page live scroll.
4. On **Discover Journeys**, she sees the discovered candidates in a list, each with a step count. Selecting one loads its discovered step-by-step flow (route, action, stage tag) in the detail panel, alongside a reference-screenshot placeholder, so she can confirm the AI's inference before deciding.
5. She uses each row's `⋯` menu to **rename** a generically-labeled candidate and **delete** ones she doesn't want carried forward — rename and delete only; there is no approve/reject step, every candidate is already in the Trusted Knowledge Model.
6. She continues to **Review Scenarios**, where generated scenarios appear grouped by their source Journey, tagged `Happy Path`/`Negative Path`/`Edge Case`. She filters to **Needs Data** to find the three scenarios still missing required Test Data, fills in the highlighted fields for each until they flip to **Ready**.
7. **Climax:** she continues to **Generate Suite**, names the suite, confirms the target environment, and generates it against the suite summary.
8. **Resolution:** she lands on **Suite Generated** — a hero card confirms "Generated 47 test cases across 12 journeys · Est. runtime 6m 40s," she expands the Generated Tests list to spot-check a couple of files, then clicks **Download Test Suite** to get the Python suite-folder project. This closes the prior revision's `[GAP]` — the post-generation screen is now fully specified.

### Flow 2 — Maria returns to an app she's already connected (new, 2026-07-27, illustrating the Landing persistence rule)

1. A week later, Maria signs in and lands on **Landing**. Her Claims Processing App card is still there, showing its current journey/scenario counts — even though she deleted several duplicate Journeys in the session above, the Application itself never disappeared from Landing.
2. She clicks the card. This **resumes the guided pipeline** — she lands directly on **Discover Journeys** for that Application (not Connect App again, and not a reset Landing).
3. **Edge case:** if she had gone on to delete *every* Journey for this Application in a later session, this same click would land her on Discover Journeys' own "All journeys have been removed" empty state — Landing itself still shows her the card, it just resumes into an empty pipeline step rather than pretending the Application was never connected.

### Flow 3 — Devon checks release readiness before sign-off (PRD UJ-2) — `[REMOVED 2026-07-15, corrected 2026-07-27 — PRD-level cut, not a standing UX gap]`

**Corrected this pass:** the prior (2026-07-21) revision of this file framed this flow as `[BLOCKED, carried forward unchanged]`, stating it "still needs explicit product-level resolution via the PRD." That framing was stale — the PRD already resolved it, in the other direction. The current PRD (`prd.md`, updated 2026-07-21) confirms UJ-2 was **removed in full on 2026-07-15**, not deferred or left open: "*UJ-2 'Devon checks release readiness before a Friday deploy' removed in full 2026-07-15 — it depended entirely on the multi-application executive dashboard, which has no supporting screen in the current UX and is removed from scope*" (PRD §2.3, line 51), reconfirmed at §6.2 line 265 ("UJ-2 ... depended entirely on the removed executive dashboard") and §9 line 308 ("UJ-2 removed"). The dependent FRs — Capability Map (FR-22), coverage analytics (FR-24), and the multi-application executive dashboard (FR-25) — were removed alongside it; no screen in the current six-screen IA serves any of them, and none should be invented here to retroactively satisfy a cut requirement.

This correction documents the cut rather than silently deleting the flow's history, matching this project's established pattern for retired scope (see `epics.md`'s Epic 5/6/7 removal entries and the Story 3.2/3.3 deletion note in `.memlog.md`). The flow's steps are preserved below only as a record of what was once scoped and is no longer — not a current spec, and not an open item:

1. ~~Devon signs in and opens Dashboard...~~
2. ~~He scans the KPI row and by-Application coverage table...~~
3. ~~He spots an inline warning flag ("1 pending test")...~~
4. ~~He factors that gap into his release decision...~~

Reviving any part of this journey (a multi-application rollup, coverage analytics, or a release-readiness view) would require a fresh, explicit product decision reinstating the relevant FR(s) — it is not something this spine can restore unilaterally, and not something a downstream consumer should treat as pending.
