---
name: Vantage (AITestGen)
description: Visual design language of the shipped Vantage product. Light mode only, Instrument Sans with IBM Plex Mono, one teal accent, soft-shadow cards on a light grey page, a left sidebar shell.
status: final
updated: 2026-10-27
colors:
  page: '#EDEEF0'
  panel: '#FFFFFF'
  panel-subtle: '#F5F6F7'
  row-hover: '#F7F8F9'
  chip: '#EFF0F2'
  line: '#E5E6E9'
  border-soft: '#DADCE0'
  border: '#C8CACF'
  border-strong: '#ABAEB5'
  ink: '#16161A'
  ink-secondary: '#3E3E46'
  ink-muted: '#5C5C66'
  ink-faint: '#6C6C76'
  code-surface: '#15161A'
  accent: '#0F766E'
  accent-strong: '#115E59'
  accent-hover: '#0D6B64'
  accent-high: '#0C5E58'
  accent-deep: '#083F3B'
  accent-wash: '#0F766E21'
  ok: '#0D8A64'
  bad: '#C93049'
  warn: '#D97706'
  good-wash: '#F0FDF4'
  good-text: '#15803D'
  danger-wash: '#FEF2F2'
  danger-text: '#B91C1C'
  warn-wash: '#FFFBEB'
  warn-text: '#B45309'
  flaky: '#7C3AED'
  flaky-text: '#6D28D9'
  flaky-wash: '#F5F3FF'
typography:
  ui: "Instrument Sans (weights 400, 500, 600, 700), system sans-serif fallback"
  mono: "IBM Plex Mono (weights 400, 500, 600), system monospace fallback"
  body: 14px / 1.5
rounded:
  small: 6px
  control: 8px
  card: 12px-14px
  large: 16px
  pill: 9999px
layout:
  content-max: about 1560px
  shell: left sidebar + top bar + content area
---

# Vantage — Design Language

This document describes the visual design of Vantage as it ships today. `EXPERIENCE.md` covers screens, behaviour and copy; this file wins on any visual question.

## Brand & Style

- **Name.** The product is **Vantage**. AITestGen is the internal project name and does not appear in the interface.
- **Mark.** A double-chevron mark with the "Vantage" wordmark, always shown in the teal accent colour. It sits at the top of the sidebar and appears in the sign-in screen's marketing image.
- **Parent brand.** The sign-in screen carries the line **"An initiative of Omnewave"** with the Omnewave logo in its own red. That red belongs to Omnewave and is used nowhere else.
- **Browser tab.** The tab title is "Vantage".
- **Posture.** A calm, data-dense working tool for QA teams. The tone is trustworthy and factual: no exclamation points, no emoji, no gamified touches and no AI confidence scores.
- **Theme.** **Light mode only.** Dark mode was considered and deliberately dropped.

## Colors

**Neutrals.**
- The page sits on a light grey (#EDEEF0). Cards, panels, dialogs and the sidebar are white (#FFFFFF). Insets, disabled fields and table headers use a faint grey (#F5F6F7).
- Hairlines run from very soft (#E5E6E9 for row dividers) through #DADCE0 (card outlines) to #C8CACF and #ABAEB5 (input and button borders, hover).
- Text is near-black (#16161A) for headings and values, with a ladder of greys for secondary text (#3E3E46), captions and placeholders (#5C5C66) and decorative marks (#6C6C76). Any text a user actually needs to read uses the caption grey or darker.
- Code is shown on a dark surface (#15161A) in the "View code" dialog.

**Accent.**
- **Teal #0F766E** is the one accent. It is used for primary buttons, links, the selected sidebar item, focus rings, checkboxes and the brand mark.
- Supporting shades: #115E59 (strong), #0D6B64 (hover), #0C5E58 (high) and #083F3B (deep). A 13% teal wash (#0F766E21) backs selected rows and in-progress pills, and also forms the 3px focus ring around fields.
- A very soft teal glow appears in page-wash backgrounds. It is atmosphere only and never fills a control.

**Semantic colours.** These are separate from the accent and never swapped with it:
- **Pass / healthy:** green #0D8A64 in charts and numbers. Pills use a pale green wash (#F0FDF4) with dark green text (#15803D).
- **Fail / critical / destructive:** red #C93049 in charts and numbers. Pills and destructive menu items use a pale red wash (#FEF2F2) with dark red text (#B91C1C).
- **Attention / paused:** amber #D97706. Pills use #FFFBEB with #B45309 text. Self-healed is amber in charts, but its chip on a test run row is green.
- **Flaky:** purple #7C3AED / #6D28D9 on a pale violet wash (#F5F3FF). Purple is reserved for the flaky flag and appears nowhere else.
- **Neutral states** (Cancelled, Not run, No test cases yet): grey text on a light grey wash. A cancelled run is not a failure and is never shown in red.

## Typography

- **Instrument Sans** is used for all interface text: headings, labels, buttons, tables and body copy. It loads in weights 400, 500, 600 and 700.
- **IBM Plex Mono** is used for code, file names in the project structure, test case numbers where shown as identifiers, raw error text and the cron field.
- Base body text is 14px with 1.5 line height. Page titles are around 20px bold, card titles 15–16px semibold, labels and table text 12.5–13.5px, and small uppercase section eyebrows 11px with slight letter-spacing.
- Weights: 400 for reading, 500–600 for labels and buttons, 700 for headings and headline numbers.

## Layout & Spacing

- **Shell.** A fixed **left sidebar** carries the brand mark and navigation. A slim **top bar** above the content shows a breadcrumb, an "Add application" button (viewers see a "View only" badge in its place) and the account menu. Content sits on the grey page in white cards.
- **Width.** Content is capped at about 1560px and centred on wide screens.
- **Spacing.** A dense, control-panel rhythm on a 4px base (4, 6, 8, 10, 12, 14, 16, 20, 24, 32px). Cards use 16–24px inner padding.
- **Dashboards.** The Overview pages lay out a row of headline number tiles, then charts in a two- or three-column grid, then lists.
- **Tables.** Applications, Test cases, Test runs, Schedules, Team members and Activity are full-width tables inside a card. They have a header row on the faint grey, soft row dividers and a light row-hover tint.
- **Sign-in.** A split screen: a marketing image panel on the left and the sign-in card on the right.

## Elevation & Depth

- Cards and panels have a soft outline plus a gentle, layered shadow. The shadow is barely visible; it lifts white cards off the grey page without looking heavy.
- Menus, popovers and dialogs sit higher, with a more diffuse shadow. Dialogs dim the page behind them.
- Primary buttons carry a faint teal glow beneath them.
- There are no decorative gradients on controls. The only gradients are the soft radial page washes.

## Shapes

- 6px corners: pills, chips, small icon buttons and menu items.
- 8px corners: buttons, inputs and selects.
- 12–14px corners: cards, panels and dialogs.
- 16px corners: the largest feature cards.
- Fully round shapes are kept for avatars, status dots, toggle switches and the bouncing busy dots.

## Iconography

- All icons come from **Font Awesome** (solid and regular styles), at small sizes inline with text.
- **More-options menus always use the vertical kebab ⋮, never the horizontal ⋯.** This applies to the Applications list, Team members, Schedules and any future row or card menu. The trigger is always visible, never revealed only on hover.
- Icons support labels; they never replace a label on a primary action.

## Components

**Buttons.**
- **Primary** buttons are solid teal with white text and are used for the one main action in an area ("Start discovery", "Run tests", "Generate test cases", "Invite member").
- **Secondary** buttons are white with a grey border.
- **Destructive** confirmations use red.
- Text links are teal.

**Busy indicators.** Something that is working is always shown as **the label followed by three trailing bouncing dots**:
- A busy button keeps its label without "…" and adds the dots after it, for example "Saving" followed by bouncing dots.
- A running operation's status pill (Discovery, scenario and test case generation, test run, self-healing) shows the same trailing dots.
- There are **never** ring spinners, and never a static "…" on its own.
- Content that is still loading uses grey skeleton placeholder blocks in the shape of the content.

**Status pills.** A small rounded label made of a tinted wash with text in the same hue. Pills normally have a leading dot; while the thing they describe is running, the dot is replaced by the trailing bouncing dots. The vocabulary:
- **Running / in progress** (teal): "Discovery in Progress", "Generating scenarios", "Generating test cases", "Running", "Pending".
- **Done / good** (green): "Test cases generated", "Ready to run", "Completed", "Passed", "Healthy".
- **Attention** (amber): "Paused", "Needs Attention", "Self-healed", "Skipped".
- **Failure** (red): "Failed", "Timed Out", "Errored", "Critical".
- **Flaky** (purple): "Flaky".
- **Neutral** (grey): "Cancelled", "Not Run", "No test cases yet".

**Chips and badges.**
- Test case source badges: "From discovery", "Authored by prompt" and "Recorded".
- Result chips on a test run: "Self-healed", "Flaky", "Retry" and "Heal exhausted".
- Filter chips with counts appear above the Test cases list.
- Chips use the same wash-plus-text pattern as pills and are never solid colour blocks.

**Inputs.**
- White fields with a grey border. Hovering darkens the border; focusing shows a teal border and a soft teal ring.
- Disabled fields turn faint grey.
- Required labels carry a red asterisk.

**Placeholders.**
- Placeholder text is **instructional**: it tells the user what to enter ("Enter the application name", "Enter your email").
- It is **never a fake example value**: no made-up company names, domains or sample data.
- The one exception is the custom cron field, where the real format ("0 2 * * 1-5") is the helpful hint.

**Toggles and checkboxes.** Teal when on. Schedules use a toggle switch for Enabled; Add application uses a toggle for "This application requires sign-in" and a checkbox for "Autonomous discovery".

**Dialogs.** Centred white cards with a title, body and right-aligned actions (secondary then primary). They are used for Invite member, New/Edit schedule, Selective run, Cancel run, delete confirmations and View code.

**Attention pulse.** Anything that is waiting on the person pulses so it is never missed: a soft amber ring that grows and fades around the element, repeating. Explorer uses it on the "Waiting for you" box, the Questions button while a question is waiting, and the Generate tests button once it is available. It is reserved for "this needs you"; a working state still uses bouncing dots.

**Segmented sub-tabs.** The Explorer tab switches between Live, What it learned, Screens and Scenarios with a segmented bar inside the page, below the header.

**Detail drawer.** On the Activity page, choosing a row opens a side drawer with what happened, why, the suggested next step and any evidence.

**Toasts.** Short confirmations and errors appear as small toasts that dismiss themselves.

**Empty states.** A short factual heading, one line of explanation and, where it makes sense, one primary action. Examples: "Add your first application", "No test runs yet".

**Screenshots and evidence.** Journey cards and failure details show screenshots as thumbnails that enlarge when clicked. Failure details also offer a trace and a "Raw error" tab beside the plain-language "Summary". Explorer scenarios offer a **proof video** that plays inline, with standard controls and muted, under the scenario.

**Live indicator.** On the Explorer tab, a small pulsing dot next to the live frame and the status line shows that Explorer is working right now.

## Charts

- Charts are simple and quiet: thin gridlines, no 3D and no heavy fills. Each has a short title in plain words.
- Colours follow the semantic palette:
  - Pass is green and fail is red.
  - Self-healed is amber and flaky is purple.
  - Neutral elements are grey.
  - Teal is used only when there is no pass/fail meaning (for example, test cases per application).
- Charts in use:
  - **Pass rate over time:** a line, with the failure rate as a dashed red line and a hover marker.
  - **Latest run outcome:** a ring showing the pass/fail split.
  - **Test cases per application:** bars.
  - **Pass rate by run:** bars on an application's Overview.
  - **Results by journey:** stacked bars of passed, self-healed, flaky and failed on a run's detail.
- Headline number tiles sit above the charts. Each shows one large figure with a short label, plus "in the last 7 days" where relevant.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use teal only for primary actions, links, focus and selection | Use teal to mean pass/fail, or colour a status with it decoratively |
| Show a working state as the label plus trailing bouncing dots | Use a spinner, or a static "Saving…" with no dots |
| Use the vertical ⋮ kebab for every more-options menu | Use the horizontal ⋯ |
| Write placeholders as instructions ("Enter the application name") | Use invented examples like a fake company name or "you@company.com" |
| Keep purple for the flaky flag only | Reuse purple for other categories |
| Show cancelled runs and tests in neutral grey | Show a user's cancellation as a red failure |
| Pair every pill or chip as a tinted wash with text of the same hue | Fill a pill as a solid colour block |
| Keep captions and labels in the readable grey or darker | Put real information in the faintest decorative grey |
| Stay in light mode | Add dark-mode variants (dropped by decision) |
| Keep copy factual and calm | Add AI confidence scores, hype or celebratory copy |

## Known inconsistencies to tidy

- A few busy labels still show a static "Saving…", "Deleting…" or "Terminating…" without the trailing dots: the saved-credentials save in Settings, the delete-application confirmation and the terminate-generation button. The "View code" button shows a static "Loading…" while fetching.
- The Explorer tab still shows ring spinners in a few places (its first "Loading Explorer…" state, the live frame, the active progress stage and scenarios still being tried), against the bouncing-dots rule.
- A few placeholders still read as values rather than instructions: "Service account email", "Password or token" and "https://".
