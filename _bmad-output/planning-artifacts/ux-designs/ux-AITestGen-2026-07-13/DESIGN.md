---
name: Application Intelligence Platform
description: A Linear-adjacent, light-default dev-tool interface with full dark-mode parity, one restrained indigo accent, and a monospace vocabulary reserved exclusively for raw captured evidence — built to make AI-inferred output feel auditable, not black-box.
status: final
updated: 2026-07-13
sources:
  - "../../prds/prd-AITestGen-2026-07-13/prd.md"
  - "../../briefs/brief-AITestGen-2026-07-12/brief.md"
  - "../../research/market-application-intelligence-platform-research-2026-07-12.md"
colors:
  paper: '#FFFFFF'
  paper-dark: '#0F0F13'
  surface: '#F7F7FA'
  surface-dark: '#17171D'
  surface-hover: '#EFEFF4'
  surface-hover-dark: '#1D1D24'
  border: '#E4E4EC'
  border-dark: '#27272F'
  border-strong: '#D3D3DE'
  border-strong-dark: '#34343E'
  ink: '#17171C'
  ink-dark: '#EDEDF2'
  ink-muted: '#6E6E7A'
  ink-muted-dark: '#95959F'
  ink-faint: '#A4A4AF'
  ink-faint-dark: '#5B5B66'
  signal: '#4F5BD5'
  signal-dark: '#8791F5'
  signal-ink: '#FFFFFF'
  signal-ink-dark: '#0F0F13'
  signal-wash: '#EEF0FC'
  signal-wash-dark: '#1C1E33'
  good: '#1A7F5A'
  good-dark: '#3FCE96'
  good-wash: '#E7F5EF'
  good-wash-dark: '#12281F'
  danger: '#C4342F'
  danger-dark: '#F17872'
  danger-wash: '#FBEBEA'
  danger-wash-dark: '#2E1717'
  warn: '#B5750C'
  warn-dark: '#E3A63C'
  warn-wash: '#FBF1DF'
  warn-wash-dark: '#2E2411'
typography:
  font-ui:
    fontFamily: '-apple-system, "Segoe UI", ui-sans-serif, system-ui, Roboto, Helvetica, Arial, sans-serif'
  font-mono:
    fontFamily: 'ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace'
  body:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  heading-hero:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 32px
    fontWeight: '650'
    lineHeight: '1.18'
    letterSpacing: -0.02em
  heading-page:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 19px
    fontWeight: '650'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  heading-card:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 14px-15px
    fontWeight: '650'
    lineHeight: '1.3'
  label-nav:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 13px
    fontWeight: '400'
    note: '600 weight + {colors.signal} when active'
  label-section:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 10.5px-11.5px
    fontWeight: '650'
    letterSpacing: 0.04em-0.06em
    note: 'uppercase, {colors.ink-muted}'
  caption:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 12px-13px
    fontWeight: '400'
    lineHeight: '1.5'
    note: '{colors.ink-muted}'
  numeric-stat:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 24px-34px
    fontWeight: '650'
    letterSpacing: -0.01em to -0.02em
    note: 'font-variant-numeric: tabular-nums, always'
  mono-block:
    fontFamily: '{typography.font-mono.fontFamily}'
    fontSize: 12px
    lineHeight: '1.7'
    note: 'raw evidence / generated code ONLY — never authored UI copy'
  mono-inline:
    fontFamily: '{typography.font-mono.fontFamily}'
    fontSize: 11px-11.5px
    note: 'route paths, API calls, filenames, timestamps'
rounded:
  sm: 4px
  DEFAULT: 6px
  lg: 10px
  full: 9999px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 20px
  '6': 24px
  '7': 28px
  '8': 32px
  '10': 40px
  rail-width: 236px
  content-max: 1180px
  content-x: 28px
  content-top: 26px
  evidence-panel-width: 340px
components:
  button-primary:
    background: '{colors.signal}'
    foreground: '{colors.signal-ink}'
    border: '{colors.signal}'
    radius: '{rounded.DEFAULT}'
    fontSize: 12.5px
    fontWeight: '600'
  button-secondary:
    background: '{colors.paper}'
    foreground: '{colors.ink}'
    border: '{colors.border-strong}'
    radius: '{rounded.DEFAULT}'
    hover-background: '{colors.surface-hover}'
  icon-button:
    size: 28px
    border: '{colors.border-strong}'
    radius: '{rounded.DEFAULT}'
    hover-approve-background: '{colors.good-wash}'
    hover-approve-foreground: '{colors.good}'
    hover-reject-background: '{colors.danger-wash}'
    hover-reject-foreground: '{colors.danger}'
  badge:
    radius: '{rounded.sm}'
    fontSize: 10.5px
    fontWeight: '650'
    textTransform: uppercase
    letterSpacing: 0.04em
    pattern: 'tinted wash background + saturated text of the same hue — never a solid fill'
    variants:
      new: '{colors.signal-wash} / {colors.signal}'
      dupe: '{colors.warn-wash} / {colors.warn}'
      approved: '{colors.good-wash} / {colors.good}'
      rejected: '{colors.danger-wash} / {colors.danger}'
      type-happy: '{colors.signal-wash} / {colors.signal}'
      type-negative: '{colors.warn-wash} / {colors.warn}'
      generated: '{colors.good-wash} / {colors.good}'
  status-pill:
    background: '{colors.signal-wash}'
    foreground: '{colors.signal}'
    radius: '{rounded.full}'
    fontSize: 11.5px
    fontWeight: '650'
    note: 'includes a pulse-dot in {colors.signal}; label text swaps to "Incomplete" on time-budget cutoff (FR-7), pill recolors to {colors.warn-wash}/{colors.warn}'
  card-panel:
    background: '{colors.paper}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    elevation: none
  nav-rail-link-active:
    background: '{colors.signal-wash}'
    foreground: '{colors.signal}'
    fontWeight: '600'
    radius: '{rounded.DEFAULT}'
  evidence-panel:
    background: '{colors.surface}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    position: 'sticky, top offset {spacing.5}'
    item-typography: '{typography.mono-inline}'
  code-viewer:
    background: '{colors.surface}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    typography: '{typography.mono-block}'
    syntax-keyword: '{colors.signal}'
    syntax-string: '{colors.good}'
    syntax-comment: '{colors.ink-muted}'
  toggle:
    track-off: '{colors.border-strong}'
    track-on: '{colors.signal}'
    thumb: '{colors.paper}'
    width: 34px
    height: 20px
  option-card:
    border: '{colors.border}'
    radius: '{rounded.lg}'
    selected-border: '{colors.signal}'
    selected-background: '{colors.signal-wash}'
  brand-mark:
    background: 'linear-gradient(155deg, {colors.signal} 0%, #2F2F9E 100%)'
    radius: 7px
    size: 24px-26px
    note: 'one of exactly two places the system uses a gradient'
  login-hero:
    background: 'linear-gradient(160deg, #10112C 0%, #22246E 58%, #4750D6 100%)'
    foreground: '#F3F3FA'
    note: 'the other of exactly two gradient placements; full-bleed intro panel, pre-authentication only'
  kpi-tile:
    border: '{colors.border}'
    radius: '{rounded.lg}'
    value-typography: '{typography.numeric-stat}'
    bar-track: '{colors.surface}'
    bar-fill: '{colors.signal}'
  hero-stat:
    value-typography: '{typography.numeric-stat}'
    default-foreground: '{colors.ink}'
    attention-foreground: '{colors.signal}'
    note: 'attention variant used at most once per strip, for the single number needing the reader''s eye first'
---

## Brand & Style

The Application Intelligence Platform sits in a specific, deliberately-chosen neighborhood: **Datadog, Linear, GitHub, Harness, Grafana Cloud** — modern, data-dense, developer-grade dev-tool aesthetics. It is explicitly *not* trying to look like a traditional ALM tool, a legacy QA management suite, or a compliance-heavy governance product. Those categories read as bureaucratic, form-heavy, "legacy-enterprise-gray" — exactly the visual language this product's positioning is trying to escape, because the product's own differentiation is that AI-discovered output can be trusted and inspected, not filed and audited.

An earlier comparison-sketch pass — four parallel directions (an ops-console direction, a github-grid direction, a harness-graph direction, and a generic clean-SaaS direction) — was rejected outright as unpolished and unconvincing. The direction that survived and was carried into the approved prototype is **Linear-adjacent**: clean, light, airy, humanist, minimal chrome, generous whitespace, a near-system sans font, subtle 1px hairline borders, one restrained accent color, and no heavy shadows, gradients, or skeuomorphism. This is a considered choice, not a default — it was arrived at only after that rejected pass made clear the product needed to look *finished and quietly confident*, not experimental.

The tone this system is built to earn is **trustworthy, credible, auditable** — never playful, never flashy, never "black box." The product's central mechanic is a human confirming what an AI inferred; the UI has to visually get out of the way of that judgment call, not perform enthusiasm about it. There are no exclamation points, no celebratory animation, no gamified affordances anywhere in this system — see `EXPERIENCE.md`'s Voice and Tone section for the copy-level expression of the same discipline.

**Light is the default surface, dark is a full first-class parity mode — not an afterthought.** Every token in this system is defined for both. The mechanism is token-level: a `:root` block sets light values and `color-scheme: light`; a `@media (prefers-color-scheme: dark)` block overrides the same custom properties for users whose OS prefers dark; and explicit `:root[data-theme="dark"]` / `:root[data-theme="light"]` attribute selectors let an in-app toggle override the OS preference outright. No component ever hardcodes a color — everything routes through the token layer, which is what makes dark mode a real mode rather than a filter.

## Colors

- **`{colors.paper}`** (`#FFFFFF` light / `#0F0F13` dark) — the base canvas. Pure, not tinted: this is a precision instrument, not a mood board.
- **`{colors.surface}`** (`#F7F7FA` / `#17171D`) and **`{colors.surface-hover}`** — a faint cool-violet-grey panel ground, used for the nav rail, evidence panel, table headers, and hover states. Distinguishes "structural chrome" from "content" without needing a border everywhere.
- **`{colors.border}`** / **`{colors.border-strong}`** — hairline dividers in the same cool-grey hue family. `border` for row/section dividers; `border-strong` for interactive-element outlines (buttons, inputs, icon buttons) that need to read as a distinct control at rest.
- **`{colors.ink}`** (`#17171C` / `#EDEDF2`) — primary text. Near-black/near-white with a whisper of violet, never pure `#000`/`#FFF`.
- **`{colors.ink-muted}`** (`#6E6E7A` light / `#95959F` dark, ~5:1 contrast on `{colors.paper}`) — **the only grey permitted for real label, caption, and metadata text.** This is a hard rule, not a style preference: during Discovery, a faint grey token was found in use on real microcopy labels at roughly 2.5:1 contrast on white, which fails WCAG AA. The fix was architectural, not a spot-fix — the system now has two distinct grey tiers with two distinct jobs, and nothing routes text through the wrong one. See Do's and Don'ts.
- **`{colors.ink-faint}`** (`#A4A4AF` / `#5B5B66`) — reserved *exclusively* for non-text, decorative use: disabled-state affordances, placeholder dashes (`—`), and other marks that are not conveying label/caption information a reviewer needs to read. It must never carry real copy again.
- **`{colors.signal}`** (`#4F5BD5` light / `#8791F5` dark, indigo) — the system's **one accent color.** "The signal found in app noise" is the literal design rationale behind the name. Used only for: primary action buttons, the active nav-rail item, links, the one hero-stat callout that most deserves first-glance attention (e.g. "Awaiting your review" on Applications), and selection state (selected queue row, selected option card, selected provider card). It is never used decoratively and never doubles as a semantic status color.
- **Semantic colors — `{colors.good}` (green), `{colors.danger}` (red), `{colors.warn}` (amber) — are a deliberately separate palette from `{colors.signal}`.** Green means approved/generated/healthy; red means rejected/failing; amber means duplicate-flagged/attention/incomplete. None of the three is ever substituted for the accent, and the accent is never asked to carry semantic meaning (e.g., it never means "success"). Each ships as a saturated foreground color plus a matching `-wash` background tint (`{colors.good-wash}`, `{colors.danger-wash}`, `{colors.warn-wash}`), used identically to how badges use signal-wash — see Components.
- **The gradient exception.** Exactly two surfaces in the entire system use a gradient: the brand mark (`{components.brand-mark}`, a 24-26px rounded swatch in the nav rail and login header) and the Login screen's full-bleed intro panel (`{components.login-hero}`, a deeper navy-to-signal wash). Nowhere else. This is the system's one place to "spend boldness" — see Elevation & Depth.

## Typography

- **`{typography.font-ui}`** (`-apple-system, "Segoe UI", ui-sans-serif, system-ui, Roboto, Helvetica, Arial, sans-serif`) carries every heading, label, button, and body string in the product. It's a native system stack on purpose — it reads as "console," not "marketing site," and it renders instantly with zero webfont cost.
- **`{typography.font-mono}`** (`ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace`) is reserved **only** for raw captured evidence: discovered routes, API call signatures, timestamps, file paths, and generated Playwright code. This is a deliberate rule tied directly to the product's core trust mechanic — the evidence trail in Review Journeys exists to prove that every inferred Journey traces back to something discovery actually captured, not something the AI paraphrased. Monospace is the typographic signal that says *"this is truth, not paraphrase."* It must never be used for authored UI copy — button labels, headings, hints, empty-state text — even where a monospace treatment might look "technical" or "cool." Using it for authored copy would blur the one visual cue reviewers rely on to distinguish system-generated fact from system-written prose.
- Scale: `{typography.heading-hero}` (32px/650, Login only) → `{typography.heading-page}` (19px/650, one per screen) → `{typography.heading-card}` (14-15px/650, card and evidence titles) → `{typography.body}` (14px/400, base) → `{typography.caption}` (12-13px, `{colors.ink-muted}`) → `{typography.label-section}` (10.5-11.5px, uppercase, tracked). Weights cluster at 400 (body) and 650 (anything acting as a heading) — there is no 500/700 in between; the ramp is binary between "reading" and "orienting."
- **`{typography.numeric-stat}`** always sets `font-variant-numeric: tabular-nums`. Every large figure in the system — hero stats, KPI values, discovery-run counters — is a number a reviewer or exec will scan quickly or compare across rows; tabular figures keep digits aligned instead of jittering as they update.

## Layout & Spacing

The shell is a fixed two-column grid: a `{spacing.rail-width}` (236px) left nav rail plus a fluid main column, content capped at `{spacing.content-max}` (1180px) so dense tables and card grids never stretch into unreadable line lengths on a wide monitor. Content padding is `{spacing.content-top}` (26px) top, `{spacing.content-x}` (28px) sides.

Spacing is dense and tightly tracked rather than built on a strict 8px doctrine — this is a control-panel product, not an editorial one, and screen real estate is spent on data density over air. The recurring increments (`{spacing.1}` 4px through `{spacing.8}` 32px, plus `{spacing.10}` 40px for the widest gaps like the Applications hero-stat strip) cover essentially every gap and padding value in the system; nothing in the approved prototype breaks this rhythm.

Grid patterns in use: the App Overview capability grid and Settings panels run 3-up and 2-up card grids respectively; the Dashboard KPI row and the CI/CD provider grid run 4-up; the Review Journeys screen is the one deliberately asymmetric layout — a flexible list column plus a fixed `{spacing.evidence-panel-width}` (340px) sticky evidence panel, because that panel's job is to stay in view while the list scrolls.

## Elevation & Depth

This system has **no shadow-based elevation.** Cards, panels, the evidence sidebar, tables, code viewers — everything that would be "elevated" in a Material-style system is instead flat, `{colors.paper}` or `{colors.surface}`, with a single 1px `{colors.border}` hairline. This is the GitHub/Linear choice deliberately: depth cues read as decoration in a product whose entire premise is "trust what you're looking at," and a flat, bordered surface reads as more like an instrument panel and less like a stack of floating cards competing for attention.

The one exception is the gradient described in Colors — see "The gradient exception" above. Treat it as a hard constraint: a new screen earning a gradient, a soft shadow, or a glassy surface anywhere outside those two placements would break the "spend boldness in one place" discipline that keeps the rest of the product feeling calm and inspectable.

The only other quasi-elevation cues in the system are functional, not decorative: a 1px `inset` highlight on the brand mark (`box-shadow:inset 0 1px 0 rgba(255,255,255,.16)`) that reads as a bevel on the gradient swatch, and a small drop shadow on the toggle-switch thumb (`0 1px 2px rgba(0,0,0,.25)`) that helps it read as a physically-sliding control. Neither is a general-purpose elevation tool; neither should be reused elsewhere.

## Shapes

A three-step radius scale, used with intent rather than uniformly:

- **`{rounded.sm}` (4px)** — the tightest radius, used only for badge/tag chips (`new`, `approved`, `dupe`, etc.) and inline `<code>`-style route/API chips. Small and crisp because these are dense, repeated, high-frequency elements.
- **`{rounded.DEFAULT}` (6px)** — buttons, inputs, icon buttons, nav-rail links. The default "interactive control" radius.
- **`{rounded.lg}` (10px)** — cards, panels, the evidence sidebar, modals, the stepper, option cards, provider cards. The "container" radius — visibly softer than a control, signaling "this holds content" rather than "click me."
- **`{rounded.full}`** — status pills and count pills (discovery status, review-queue count, capability journey counts). Fully rounded because these are small, label-like, at-a-glance chips, and a pill shape reads as "state," distinct from a badge's rectangular "category" shape.

Circles are reserved for people/identity and progress affordances only: the user avatar, environment/health dots, the stepper's numbered step-circle, and the small `dot` marker preceding a capability's journey list.

## Components

- **Nav rail** — fixed-width, `{colors.surface}` background, links grouped under uppercase section labels that mirror the product narrative: *Workspace → Onboard → Understand → Automate → Prove*, with Settings and sign-out pinned to the rail foot below a divider. The active link gets `{components.nav-rail-link-active}` treatment (signal-wash fill, signal text, 600 weight). Review Journeys is the only rail link that carries a live count badge (pending-review count) — reinforcing that it's a queue, not a static page.
- **Buttons** — `{components.button-primary}` (solid signal fill, signal-ink text) for the one primary action per screen; `{components.button-secondary}` (bordered, transparent) for everything else. No tertiary/ghost/link-styled button variant exists in the system beyond plain text links.
- **Icon buttons** (`{components.icon-button}`) — 28px square, bordered, neutral at rest. On hover, approve and reject icon buttons pick up a *semantic* tint (`{colors.good-wash}`/`{colors.good}` for approve, `{colors.danger-wash}`/`{colors.danger}` for reject) — the only place hover state carries meaning beyond "this is clickable."
- **Badges** (`{components.badge}`) — every badge variant (`new`, `dupe`, `approved`, `rejected`, `type-happy`, `type-negative`, `generated`) follows one pattern without exception: a tinted wash background plus saturated text in the *same* hue, never a solid fill. This keeps every badge legible at small size without visually shouting.
- **Status pill** (`{components.status-pill}`) — pill-shaped, signal-wash by default, with a small pulsing dot for "in progress" states (Discovery Progress's "Running," the Applications table's "Discovery in progress"). Per PRD FR-7, a Discovery Run that hits its time budget before finishing transitions this same pill to an amber "Incomplete" state — same component, different token pairing, never a separate visual pattern.
- **Two-pane review row + evidence panel** — Review Journeys' core pattern: a scannable list of `queue-row` items on the left, each with a name, status/type badge, capability tag, and (for undecided rows) four icon-button actions; selecting a row loads its full evidence trail — pages visited, actions taken, API calls made, each rendered in `{typography.mono-inline}` — into the sticky `{components.evidence-panel}` on the right. This pairing (scannable list + detail-on-select sidebar) is the system's canonical "make an AI claim inspectable" pattern.
- **Capability cards** — bordered `{components.card-panel}` grid cells, each holding a Capability name, a journey-count pill, a one-line description, and a nested list of that Capability's approved Journeys with a small green status dot and a test-count in `{typography.mono-inline}`.
- **KPI tiles** (`{components.kpi-tile}`) — label, `{typography.numeric-stat}` value, optional signal-colored progress bar beneath. Used on the Dashboard for portfolio-level counts.
- **Hero-stat strip** (`{components.hero-stat}`) — the Applications landing page's top-of-page callout row: large bold tabular numbers, `{colors.ink}` by default, with exactly one stat (the item most deserving first attention — "Awaiting your review") rendered in `{colors.signal}` instead. Never more than one accent-colored number per strip.
- **Stepper** (Add Application wizard) — vertically stacked numbered steps; each step's circle is neutral at rest, fills `{colors.signal}` when active, and recolors to `{colors.good-wash}`/`{colors.good}` once done. Step body content only renders for the active step; done and pending steps show a one-line summary instead — this is itself a progressive-disclosure move, keeping a 3-step form from presenting all fields at once.
- **Option cards / provider cards** — radio-styled selection controls (auth method, CI/CD export mode, CI/CD provider). Visually a bordered card containing a real `<input type="radio">`; selected state adds a signal border and signal-wash fill. Used wherever a user is choosing exactly one option from a small, meaningfully-different set — never used for simple boolean toggles (that's the toggle switch, below).
- **Code viewer + `<details>` disclosure** — generated Playwright code and CI/CD pipeline snippets render in `{components.code-viewer}` with light syntax tinting (keywords in `{colors.signal}`, strings in `{colors.good}`, comments in `{colors.ink-muted}`), wrapped in a native `<details>`/`<summary>` disclosure. This is a direct, named fix from Discovery: Add Application and Connect to CI/CD were both flagged as cluttered when every code block and secondary field was open by default. The system rule going forward is **disclosure-over-always-open** for any dense technical content that isn't the primary reason the user is on the screen — a Test Asset's code is supporting evidence for "this Journey has a test," not the headline of the row.
- **Toggle switch** (`{components.toggle}`) — for genuine on/off settings only (Settings' AI-provider mode, notification preferences). Track fills `{colors.signal}` when on.
- **Empty state** — dashed-border panel, a circular green check icon, a one-line confirmation, and (on Review Journeys specifically) an approve/reject count summary. Used to close a workflow, not to fill dead space — it only appears when a queue or list has been fully triaged.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use `{colors.signal}` only for primary actions, active nav/selection, links, and one hero-stat callout | Use `{colors.signal}` for semantic status (success/error/warning) or decoratively |
| Route all real label/caption/metadata text through `{colors.ink-muted}` (AA, ~5:1) | Use `{colors.ink-faint}` for any real text a reviewer needs to read — it's decorative-only |
| Use `{typography.font-mono}` only for discovered evidence and generated code | Use monospace for authored UI copy, even to look "technical" |
| Keep cards/panels flat with a 1px `{colors.border}` hairline | Add drop shadows or elevation as a hierarchy device anywhere outside the two gradient placements |
| Spend the system's one gradient only on the brand mark and the Login hero panel | Introduce a second gradient, glassy surface, or shine effect elsewhere |
| Pair every badge as a tinted wash + saturated text of the same hue | Fill a badge as a solid color block |
| Progressively disclose dense code/technical content via `<details>` | Render all generated code, config, or secondary fields open by default on a setup or integration screen |
| Give Journey review exactly four actions: Approve, Rename, Reject, Delete | Design or imply a merge, split, or inline-composition-edit affordance for a Journey — cut for V1, duplicates are rejected, not merged |
| Treat Generated Scenarios as read-only reference chrome | Add checkbox selection, per-scenario approval, or action buttons to a scenario row — the approval gate is the Journey, not the Scenario |
| Keep every AI-inferred item's UI free of any confidence, risk, or importance signal | Add a score, percentage, star rating, or priority flag anywhere near discovered/inferred content — this is a hard product constraint (PRD §5 Non-Goals), not an aesthetic choice deferred for later |
