---
name: Application Intelligence Platform
status: final
updated: 2026-07-13
sources:
  - "../../prds/prd-AITestGen-2026-07-13/prd.md"
  - "../../briefs/brief-AITestGen-2026-07-12/brief.md"
  - "../../research/market-application-intelligence-platform-research-2026-07-12.md"
---

# Application Intelligence Platform — Experience Spine

> `DESIGN.md` is the visual identity reference; this spine is the experience — information architecture, behavior, states, and flows. Where this file describes a visual property, `DESIGN.md` wins on conflict. Composition reference: `mockups/prototype-v1.html` (approved v6, 11-screen prototype).

## Foundation

Desktop web app only — no mobile or tablet form factor in V1. This was an explicit Discovery decision, not an oversight: the product's primary jobs (reviewing a discovered Journey against its evidence trail, reading a dense coverage table) assume a real monitor and a keyboard, and building responsive parity for a V1 whose review workflows are inherently data-dense would spend effort the product doesn't need yet.

**WCAG is the explicit accessibility bar.** Not SOC2-style compliance signaling, not a governance-product visual language — the brief and PRD are clear that the product's positioning runs *away* from that register (see `{DESIGN.md#Brand & Style}`). Accessibility here means real behavioral commitments (focus visibility, keyboard operability, contrast), not a compliance badge.

The product's core entity model — Application → Discovery Run → Capability/Journey → Scenario → Test Asset — is defined in full in PRD §3 (Glossary) and is not restated here. Two structural facts shape everything below: **only human-approved Journeys and Capabilities enter the Trusted Knowledge Model** (PRD FR-14), and every candidate Journey the platform ever shows a reviewer is traceable back to the specific pages, actions, and API calls discovery actually captured (PRD FR-8 consequence). This traceability requirement is why Review Journeys is built as a two-pane list-plus-evidence pattern rather than a flat approve/reject list — see Review & Trust Model.

## Information Architecture

Visual reference: `mockups/prototype-v1.html` (approved v6, 11-screen interactive prototype — click through it, it's the fastest way to feel the flows below).

Eleven screens, one pre-authentication (Login) and ten inside a persistent app shell (nav rail + top bar). The rail groups links under five section labels that mirror the product's narrative arc — Application Intelligence → Journey Intelligence → Test Intelligence:

| Section | Screen | Reached from |
|---|---|---|
| — (pre-shell) | Login | App open, unauthenticated |
| Workspace | Applications | Sign-in; nav rail (default landing) |
| Onboard | Add Application | "+ Add Application" (Applications) or nav rail |
| Onboard | Discovery Progress | Wizard completion, or a running/completed Application row |
| Understand | App Overview | Nav rail, once an Application has approved Capabilities |
| Understand | Review Journeys | Nav rail (carries a live pending-count badge) |
| Automate | Generated Scenarios | Nav rail |
| Automate | Generated Tests | Nav rail |
| Automate | Connect to CI/CD | Nav rail |
| Prove | Dashboard | Nav rail |
| (rail foot) | Settings | Rail foot, below a divider |
| (rail foot) | Sign out | Rail foot |

**Primary flow:** Applications → Add Application → Discovery Progress → App Overview → Review Journeys → Generated Scenarios → Generated Tests → Connect to CI/CD → Dashboard. This is a guided linear workflow, not a set of disconnected dashboards — each screen is a checkpoint in "onboard an app, understand it, get it under test," and the rail's section labels exist to make that arc legible even when a user jumps in mid-sequence.

**Naming rule — function-first labels.** Every screen name states what a user *does* there, not the internal mechanism or artifact type behind it. This rule, not just its outputs, is the thing to carry forward when naming future screens: a name that describes the underlying data structure or system component ("Journey Explorer," "Capability Map," "Scenario Explorer," "Analytics Dashboard," "Application Setup Wizard") reads as an engineer's mental model; a name that describes the user's task ("Review Journeys," "App Overview," "Generated Scenarios," "Dashboard," "Add Application") reads as the user's mental model. This is why those exact renames happened during Discovery, and why "Discovery Run" became **Discovery Progress** — the screen's job is watching a live status change, not configuring a run (that's the wizard's job).

**Breadcrumb / app-name context rule.** The top-bar crumb shows the current Application's name (`<b>Claims Processing App</b> /`) only on screens genuinely scoped to one Application: Discovery Progress, App Overview, Review Journeys, Generated Scenarios, Generated Tests, Connect to CI/CD, Settings. It is suppressed on Applications, Add Application, and Dashboard — the three screens that are inherently cross-Application or pre-Application. This was a specific declutter fix during Discovery: showing an app-context breadcrumb on a screen that lists *all* Applications, or on the wizard before an Application exists, was noise, not orientation.

## Review & Trust Model

This is the product's central mechanic, and it is intentionally narrow. Two PRD conflicts surfaced during Discovery and were explicitly resolved — both are hard constraints for every future screen and story, not soft suggestions:

**1. Journey review has exactly four actions: Approve, Rename, Reject, Delete.** No merge, no split, no inline edit of what pages/actions/API calls compose a Journey. When discovery produces overlapping or duplicate candidates (e.g., a Journey the AI split awkwardly into two), the correct reviewer action is to **reject the redundant one(s)** — never to merge them. The UI signals this directly: a duplicate candidate carries a `dupe` badge (e.g., "Overlaps Claims Approval") precisely so a reviewer recognizes it should be rejected, not combined. Any future feature work proposing a merge/split/composition-edit affordance on a Journey contradicts a deliberate, PRD-level V1 cut (PRD §4.4 Out of Scope) — resolve it as a product decision before it becomes a design decision.

**2. Generated Scenarios are view-only.** There is no per-scenario selection, checkbox, or approval gate. The approval gate lives at the Journey level only (PRD FR-18): once a Journey is approved in Review Journeys, all of its Scenarios auto-proceed to Playwright generation. Generated Scenarios exists purely for traceability and visibility — a reviewer or exec can see *what got generated and why* — not as a second review queue. Visually, scenario rows resemble other action-bearing rows in the system (list row + badges), but they must never grow action affordances; that resemblance is a trap for future screens to avoid, not a pattern to extend.

**Evidence traceability is the mechanism that makes review trustworthy**, not a nice-to-have: every candidate Journey a reviewer sees is backed by the literal pages, actions, and API calls discovery captured for it (PRD FR-8 consequence), surfaced in the evidence panel described in Component Patterns. A reviewer should never have to take an inferred Journey's business-language name on faith — the raw evidence is one click away, in monospace, unparaphrased (`{DESIGN.md#Typography}`).

By product decision (PRD §5 Non-Goals), there is **no AI confidence or risk score anywhere in this workflow**, and **no reviewer prioritization or importance-marking** — every approved Journey is treated with equal weight, and reviewers triage a potentially large candidate list with no built-in ranking aid (PRD Risk #3, accepted for V1). Design and copy must not imply otherwise — no "high confidence" language, no subtle visual weighting that reads as a priority signal.

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
| Nav rail link | Global | Click navigates; the active link highlights per `{DESIGN.md#components.nav-rail-link-active}`. Review Journeys' link additionally shows a live pending-review count that updates as items are triaged. |
| Review row | Review Journeys | Click/select loads that Journey's evidence trail into the sticky side panel (replacing the previous selection, not stacking). Undecided rows show all four actions (approve/rename/reject/delete); a decided row (approved or rejected) drops its action buttons entirely and its title dims — the row becomes a record, not a control. |
| Evidence panel | Review Journeys | Sticky on scroll — stays in view while the row list scrolls beneath it, since its job is to stay attached to whatever row is currently selected. Content (pages / actions / API calls) is grouped and always rendered in monospace per `{DESIGN.md#Typography}`. |
| Capability card | App Overview | Static display — read-only rollup. Each nested Journey row shows a test-asset count; clicking a Journey name is not a defined interaction in V1 (App Overview is a presentation surface for showing an Engineering Leader, not a second review entry point). |
| KPI tile / hero stat | Dashboard, Applications | Static display. The progress bar beneath a KPI (e.g., tests-generated-of-approved) is non-interactive — a visual ratio, not a control. |
| Stepper | Add Application | Only the active step renders its full form body; completed steps collapse to a one-line summary, pending steps show only their title. Back/Continue moves the active step; a completed step is not directly clickable to jump back to in this version. |
| Option card / provider card | Add Application (auth method), Connect to CI/CD (export mode, provider) | Click anywhere on the card selects it (the real `<input type="radio">` underneath makes this keyboard-operable natively). Exactly one selection per group; selecting a new option deselects the previous one. |
| Code disclosure (`<details>`) | Generated Tests, Connect to CI/CD | Closed by default for every code block except the first/most-relevant one on a screen (e.g., the first Test Asset's code starts open on Generated Tests, the rest start closed). Opening one disclosure does not close others — multiple can be open at once. This is the direct fix for the clutter Discovery flagged on Add Application and Connect to CI/CD: dense technical content is opt-in, not ambient. |
| Toggle switch | Settings | Immediate on/off, no confirmation step. Used only for genuine binary settings (AI provider mode, notification preferences) — never repurposed as a selection control (that's option/provider cards). |
| Status pill | Discovery Progress, Applications table | Reflects live run state; see State Patterns for the Running → Incomplete transition. |

`[NOTE FOR PM/ENG — placeholder, not a confirmed decision]` The Add Application wizard's "Authenticate" step shows a specific SSO/MFA session-handoff mechanism (paste session-state JSON, or reference a `storageState.json` file) purely as an illustrative placeholder. PRD Open Question 8 explicitly marks this mechanism as unresolved and states it must be decided *before* onboarding UX proceeds — that decision has not yet been made. Treat the wizard's Step 2 content as a stand-in for "whatever the real handoff mechanism turns out to be," not as the resolved design. Revisit this step once PRD Open Question 8 is answered; it may not change the step's shape (a second auth-method option alongside standard login) but could change its exact fields.

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| Discovery running | Discovery Progress, Applications row | Status pill reads "Running" with a pulsing dot; live-feed list shows the most recently discovered pages/actions/API calls, newest first, appended as discovery proceeds. |
| Discovery hits time budget (PRD FR-7) | Discovery Progress, Applications row | Status pill automatically transitions from "Running" to **"Incomplete"** the moment the configured time budget is reached, even if traversal wasn't exhaustive. This is a real product state transition, not a prototype detail — the run's captured Journeys remain usable and enter the review queue normally, but the run itself must never present as a finished/complete map once it has timed out (PRD FR-7 consequence, realizes PRD UJ-1's edge case). |
| Review queue in progress | Review Journeys | Undecided rows show badges (`New`, or `Overlaps {other Journey}` for a flagged duplicate) and all four actions. |
| Review queue item resolved | Review Journeys | Row switches to a muted/reduced-opacity treatment, badge switches to `Approved` or `Rejected`, and the four action buttons are removed (not disabled — removed, since there's nothing left to do with a resolved row). |
| Review queue cleared | Review Journeys | Empty-state panel replaces the "once queue is clear" section: a confirmation line plus an Approved/Rejected count pair, so the reviewer sees the outcome of the session at a glance rather than just an absence of rows. |
| CI/CD provider connected | Connect to CI/CD | Selected provider card shows a "Connected" status label beneath its name; unconnected providers show none. |
| Coverage gap | Dashboard | An application row with at least one approved Journey lacking a generated Test Asset shows an inline warning flag ("N pending test") next to its coverage figures — this is the specific catch that lets an Engineering Leader spot a gap before sign-off (PRD UJ-2 climax). |

## Interaction Primitives

- **Click to navigate.** Every nav-rail link, and every clickable table row (Applications, Dashboard), is a single click to its destination. There is no double-click, no drag, no multi-select anywhere in V1.
- **`<details>` progressive disclosure** for dense technical content — generated code, pipeline snippets — per Component Patterns above. This is a real, intended interaction primitive for this product, not just a prototype convenience.
- **Sticky evidence panel on scroll** — the Review Journeys evidence panel stays pinned in the viewport as the row list scrolls, so evaluating evidence never requires losing your place in the list.
- **Row hover** highlights the row background and, on clickable table rows (Applications, Dashboard), switches the cursor to a pointer as an affordance cue. On Review Journeys, the four row actions are **always visible** on any undecided row rather than hidden behind hover — they gate a required decision, so hiding them behind a hover state would work against discoverability and against keyboard/touch users who don't hover at all.
- **One important non-primitive to flag explicitly:** the approved prototype uses a no-JavaScript, radio-input-driven CSS technique to switch between its eleven "pages" inside one static HTML file. That is a **prototyping technique only**, built so the file could be reviewed and clicked through without a server or build step — it is not a real product interaction pattern and must not be read as a spec for how page navigation, tabs, or steppers should actually be implemented (e.g., "use hidden radio inputs for real app routing" or "use `:checked` CSS selectors for real tab state"). The real primitives are ordinary click-driven navigation and the native, keyboard-operable radio/`<details>` elements described above, wired to real application state rather than a single-file CSS trick.

## Accessibility Floor

Behavioral commitments; visual contrast lives in `{DESIGN.md#Colors}`.

- **WCAG 2.1/2.2 AA is the floor** across the entire desktop surface — not a stretch goal, and not SOC2/governance-style compliance signaling (see Foundation).
- **Focus-visible on every interactive element** — buttons, nav-rail links, inputs, selects, textareas, and `<summary>` disclosure triggers all get a visible focus ring. This is a behavioral requirement this file states; the ring's exact color and offset are DESIGN.md's to specify.
- **Keyboard operability for radio-driven selection patterns.** Option cards, provider cards, and the wizard's auth-method choice are real `<input type="radio">` controls under a styled card — this must stay true in implementation (not become a `<div onclick>` fake), specifically so these patterns remain fully keyboard-operable (arrow-key group navigation, Space/Enter to select) without any extra work.
- **Tab order matches visual order** on every screen — top bar, then rail, then main content, top to bottom, left to right within the two-pane Review Journeys layout (list before evidence panel).
- **Label/caption contrast is a standing requirement, not a one-time fix.** DESIGN.md documents the specific token-level fix (routing all real label/caption text through `{DESIGN.md#colors.ink-muted}`, ~5:1, and reserving the faint tier for decorative-only use) after a real AA-contrast failure was caught during Discovery. This file's requirement is the "why it matters": any new screen or component that introduces new label/caption text must use the AA-passing muted tier, full stop — this is not negotiable per-component judgment.

## Inspiration & Anti-patterns

- **Lifted from Linear, Datadog, GitHub, Harness, Grafana Cloud (the explicit reference cluster):** clean, light, airy chrome; minimal decoration; hairline borders over shadows; dense-but-legible data tables; a single restrained accent color used sparingly and consistently for "this is active/primary" rather than scattered across the UI.
- **Rejected — traditional ALM tools, legacy QA management suites, compliance-heavy governance products:** these were named explicitly as the *away-from* direction. Their visual signature — bureaucratic form density, heavy chrome, "enterprise gray," governance-badge iconography — actively undercuts this product's positioning, which sells trust through transparency and inspectability, not through looking like a compliance artifact.
- **Rejected — the first comparison-sketch pass** (`{DESIGN.md#Brand & Style}` has the full story): the lesson carried forward isn't about any one visual element — it's that this product needed one committed, finished-looking direction presented with conviction, not a menu of rough alternatives.
- **Rejected — merge/split Journey actions:** the approved brief's narrative described a reviewer who "merges duplicates," but this was cut from the PRD for V1 (§4.4) to keep the review workflow to four simple, unambiguous actions. Don't reintroduce this as a "quick UX win" without a product-level decision first — see Review & Trust Model.
- **Rejected — reviewer prioritization/importance-marking:** the approved brief also described a reviewer who "marks what matters most to the business." V1 has no such affordance; every approved Journey is equal-weighted, by explicit PRD decision (§5 Non-Goals). No priority flag, star, or ranking control anywhere near a Journey or Capability.
- **Rejected — any AI confidence/risk score UI:** named explicitly in PRD §5 as a deliberate cut from the approved brief's stated V1 outcomes. This is a recurring temptation for "helpful" UI (e.g., a subtle confidence bar on a candidate Journey) that must be resisted at the product-decision level, not just the visual level.

## Key Flows

### Flow 1 — Maria reviews her Application's first discovered map (PRD UJ-1)

Maria Colón, QA Director at a mid-size insurer, has just had her first Discovery Run finish against the Claims Processing App staging environment.

1. Maria is signed in, and opens **Review Journeys** from the nav rail — its link shows a pending count (6) pulling her attention.
2. She sees six candidate Journeys: "Claims Approval," "Policy Issuance," "Claims Intake," a few named plainly, and one — `Page_Flow_7` — carrying a `dupe` badge reading "Overlaps Claims Approval."
3. She selects a row to load its evidence trail in the side panel, confirming the AI's inference against the actual pages/actions/API calls discovery captured, before deciding.
4. She **renames** a generically-labeled candidate to a real business name, **rejects** the duplicate (`Page_Flow_7`) rather than trying to merge it into "Claims Approval," and **approves** the rest one by one — each approved row loses its action buttons and mutes, dropping out of her remaining attention.
5. **Climax:** as she approves the last undecided Journey, the queue empties and the empty-state panel confirms: "Review queue cleared. All candidates from the Jul 12 run have been triaged. Scenario and test generation has started for approved Journeys." — with an Approved/Rejected count pair (5 approved, 1 rejected) as visible proof of the session's outcome.
6. **Resolution:** she navigates to **App Overview**, where her approved Journeys now render grouped under business-language Capabilities (Claims Processing, Policy Administration, Billing & Payments) — the artifact she can put in front of her Engineering Leader.
7. **Edge case:** if the Discovery Run had hit its time budget before finishing, the Discovery Progress screen (and any Applications-table row referencing that run) would show the status pill as **Incomplete**, not "Running" or a bare completion state — Maria would see a partial map clearly marked as partial, never presented as finished.

### Flow 2 — Devon checks release readiness before sign-off (PRD UJ-2)

Devon, an Engineering Leader, is deciding whether to approve a release.

1. Devon signs in and opens **Dashboard** — the cross-Application executive rollup, reached directly from the nav rail's "Prove" section (no single-Application context needed, matching the breadcrumb-suppression rule).
2. He scans the KPI row (27 approved Journeys, 24/27 Test Assets generated, 6 awaiting review, 3 Applications onboarded) and then the by-Application table, which shows generated-vs-not coverage per Application — deliberately not live pass/fail from CI, since V1 has no read-back channel from the customer's pipeline (PRD FR-24 consequence).
3. **Climax:** on the Claims Processing App row, he spots an inline warning flag — "1 pending test" — showing that a recently-approved Journey still has no generated Test Asset (still mid-pipeline). He would have missed this by eyeballing the coverage bar alone; the flag exists specifically to catch it.
4. **Resolution:** he factors that gap into his release decision — approving with a documented, specific view of what's covered and what isn't, rather than a gut call.

