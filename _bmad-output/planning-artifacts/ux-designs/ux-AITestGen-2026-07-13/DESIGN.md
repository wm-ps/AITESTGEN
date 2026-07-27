---
name: Application Intelligence Platform
description: A guided-pipeline dev-tool interface (product wordmark "AITestGen") — light-only, Inter-set, one teal accent, permitted decorative gradients on brand moments only, soft shadow-based card elevation. Redistilled 2026-07-27 from prototype-v3.html; supersedes the 2026-07-15 no-gradient/flat/Linear-adjacent identity. `[CORRECTED 2026-07-27, same day]` The first pass of this redistillation wrongly claimed the accent moved from teal to blue — that was read off an unused `this.props.accentColor || '#2563EB'` JS fallback without actually rendering the file. Rendering `prototype-v3.html` directly (headless browser, computed styles) shows the accent in effect everywhere (buttons, links, selected rows, stepper, brand mark) is teal `#0F766E`, unchanged from the 2026-07-15 revision. The blue `#2563EB`/`#1D4ED8` pair is real, but scoped to one place only — the Happy Path badge's wash/text — confirmed by the same rendering pass and kept as `{colors.happy-strong}`, decoupled from `{colors.accent-strong}`.
status: final
updated: 2026-07-27
sources:
  - "../../prds/prd-AITestGen-2026-07-13/prd.md"
  - "../../briefs/brief-AITestGen-2026-07-12/brief.md"
  - "../../research/market-application-intelligence-platform-research-2026-07-12.md"
colors:
  canvas: '#FFFFFF'
  canvas-wash: '#F8FAFC'
  canvas-wash-alt: '#F1F5F9'
  surface: '#FFFFFF'
  border: '#E2E8F0'
  border-hairline: '#F1F5F9'
  border-strong: '#CBD5E1'
  ink: '#0F172A'
  ink-secondary: '#334155'
  ink-muted: '#64748B'
  ink-faint: '#94A3B8'
  accent: '#0F766E'
  accent-strong: '#115E59'
  accent-wash-soft: '#0F766E0D'
  accent-wash: '#0F766E21'
  accent-wash-strong: '#0F766E38'
  good: '#16A34A'
  good-strong: '#15803D'
  good-wash: '#F0FDF4'
  danger: '#DC2626'
  danger-strong: '#B91C1C'
  danger-wash: '#FEF2F2'
  warn: '#D97706'
  warn-strong: '#B45309'
  warn-wash: '#FFFBEB'
  warn-wash-border: '#FDE68A'
  happy-wash: '#EFF6FF'
  happy-strong: '#1D4ED8'
typography:
  font-ui:
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    note: 'Inter loaded as a webfont (self-hosted @font-face, full charset incl. cyrillic/greek subsets). Replaces the prior native-system-stack-only rule.'
  font-mono:
    fontFamily: "'SFMono-Regular', Consolas, ui-monospace, Menlo, monospace"
  display:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 28px
    fontWeight: '600'
    lineHeight: '1.25'
    letterSpacing: -0.01em
    note: 'Sign-in screen marketing headline only — not used elsewhere'
  wordmark:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 22px
    fontWeight: '800'
    letterSpacing: -0.02em
    note: 'the literal "AITestGen" product wordmark next to the brand mark — the one place weight 800 is used in the entire system'
  heading-page:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 19px-21px
    fontWeight: '700'
    note: 'one per screen/detail-panel: "Discover Journeys", a selected Journey/Scenario name, "Generate Test Suite", the Suite Generated hero name'
  heading-card:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 15px-16px
    fontWeight: '700'
    note: 'card titles, wizard step titles, top-bar Application name'
  body:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.55'
  label:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 13px-13.5px
    fontWeight: '600'
    note: 'form field labels, secondary buttons, list-row primary text'
  caption:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 12px-12.5px
    fontWeight: '400'
    note: 'must route through {colors.ink-muted}, never {colors.ink-faint} — see Do''s and Don''ts'
  label-section:
    fontFamily: '{typography.font-ui.fontFamily}'
    fontSize: 11px
    fontWeight: '700'
    textTransform: uppercase
    letterSpacing: 0.05em
    note: '{colors.ink-faint} permitted here only — decorative section eyebrow, not information-bearing on its own'
  mono-inline:
    fontFamily: '{typography.font-mono.fontFamily}'
    fontSize: 11.5px-13px
    note: 'route/URL chips, generated filenames (e.g. login-and-mfa.py), raw evidence text'
rounded:
  xs: 6px
  sm: 7px
  DEFAULT: 8px
  md: 9px
  lg: 12px
  xl: 14px
  2xl: 16px
  full: 9999px
spacing:
  '1': 4px
  '2': 6px
  '3': 8px
  '4': 10px
  '5': 12px
  '6': 14px
  '7': 16px
  '8': 20px
  '9': 24px
  '10': 32px
  content-x: 32px
  content-top: 22px
  list-column-width: 260px-280px
  detail-max-width: 680px
  reference-panel-width: 260px
  content-max: 1720px
components:
  brand-mark:
    background: 'linear-gradient(135deg, {colors.accent} 0%, {colors.accent} 65%, rgba(0,0,0,0.22) 100%)'
    radius: '{rounded.md}'
    size: 30px-36px
    inset-highlight: 'inset 0 1px 0 rgba(255,255,255,0.4)'
    inset-shadow: 'inset 0 -6px 10px rgba(0,0,0,0.15)'
    note: 'the one deliberate gradient-as-object surface in the system, always this exact 135deg accent-to-dark-overlay ramp — never a decorative gradient elsewhere on a control'
  button-primary:
    background: '{colors.accent}'
    foreground: '#FFFFFF'
    radius: '{rounded.DEFAULT}'
    fontSize: 13px-14.5px
    fontWeight: '600'
    shadow: '0 6px 16px -6px {colors.accent-wash-strong}'
    note: 'flat solid fill — buttons never carry the brand-mark gradient'
  button-secondary:
    background: '{colors.canvas}'
    foreground: '{colors.ink-secondary}'
    border: '{colors.border-strong}'
    radius: '{rounded.DEFAULT}'
    shadow: '0 1px 2px rgba(15,23,42,0.06)'
    hover-background: '{colors.canvas-wash}'
  icon-button:
    size: 22px-32px
    radius: '{rounded.xs}'
    background: transparent
    hover-background: '{colors.border}'
  input:
    border: '{colors.border}'
    radius: '{rounded.DEFAULT}'
    padding: '9px-11px {spacing.5}'
    focus-border: '{colors.accent}'
    focus-ring: '0 0 0 3px {colors.accent-wash}'
    required-marker: '{colors.danger}'
  card-panel:
    background: '{colors.surface}'
    border: '{colors.border}'
    radius: '{rounded.xl}'
    shadow: '0 4px 14px -3px rgba(15,23,42,0.1), 0 1px 3px rgba(15,23,42,0.06)'
  top-bar:
    background: '{colors.canvas}'
    border-bottom: '{colors.border}'
    height: 64px
    shadow: '0 2px 8px -4px rgba(15,23,42,0.10)'
  pipeline-stepper:
    circle-size: 23px
    circle-radius: '{rounded.full}'
    connector-width: 34px
    connector-height: 1.5px
    label-typography: '{typography.label}'
    note: 'active/done/pending states are token-driven per step — background, border, and connector color all swap, no icon change except a checkmark glyph on done'
  list-row:
    radius: '{rounded.md}'
    border: '{colors.border}'
    selected-border-left: '3px solid {colors.accent}'
    selected-background: '{colors.accent-wash}'
    shadow: '0 1px 3px rgba(15,23,42,0.06)'
    hover-shadow: '0 2px 6px rgba(15,23,42,0.1)'
  kebab-menu:
    trigger-size: 22px
    dropdown-background: '{colors.canvas}'
    dropdown-border: '{colors.border}'
    dropdown-radius: '{rounded.xs}'
    dropdown-shadow: '0 8px 20px rgba(15,23,42,0.12)'
    destructive-item-color: '{colors.danger}'
    destructive-item-hover: '{colors.danger-wash}'
  badge:
    radius: '{rounded.xs}'
    fontSize: 10.5px-12px
    fontWeight: '600'
    pattern: 'tinted wash background + saturated text of the same hue — never a solid fill'
    variants:
      happy-path: '{colors.happy-wash} / {colors.accent-strong}'
      negative-path: '{colors.danger-wash} / {colors.danger-strong}'
      edge-case: '{colors.warn-wash} / {colors.warn-strong}'
  status-pill:
    radius: '{rounded.xs}'
    fontSize: 10.5px
    fontWeight: '700'
    pattern: 'same tinted-wash pattern as badge'
    variants:
      ready: '{colors.good-wash} / {colors.good-strong}'
      needs-data: '{colors.warn-wash} / {colors.warn-strong}'
  test-data-callout:
    background: '{colors.accent-wash-soft}'
    border: '{colors.accent-wash}'
    radius: '{rounded.lg}'
    shadow: '0 2px 8px -4px {colors.accent-wash-strong}'
    warning-banner-background: '{colors.warn-wash}'
    warning-banner-border: '{colors.warn-wash-border}'
    warning-banner-foreground: '#92400E'
  expected-result-rule:
    border-left: '3px solid {colors.good}'
    foreground: '{colors.ink-secondary}'
  segmented-filter:
    track-background: '{colors.canvas-wash-alt}'
    track-border: '{colors.border}'
    track-radius: '{rounded.DEFAULT}'
    item-radius: '{rounded.xs}'
    active-background: '{colors.canvas}'
  stat-tile:
    background: '{colors.accent-wash-soft}'
    radius: '{rounded.md}'
    value-typography: '{typography.heading-page}'
  suite-hero-card:
    background: 'linear-gradient(135deg, {colors.accent} 0%, {colors.accent} 55%, rgba(0,0,0,0.25) 100%)'
    radius: '{rounded.2xl}'
    foreground: '#FFFFFF'
    decorative-orbs: 'two oversized low-opacity white circles, absolutely positioned, clipped by the card — decoration only'
    note: 'the second deliberate gradient-as-object surface in the system; used once, on Suite Generated only'
  generated-tests-disclosure:
    background: '{colors.surface}'
    border: '{colors.border}'
    radius: '{rounded.lg}'
    group-heading-typography: '{typography.mono-inline}'
    note: 'grouped by generated file, click-to-expand chevron pattern; per-scenario rows nest a type badge + name + a secondary "Code" button'
  empty-state-bare:
    typography: '{typography.body}'
    foreground: '{colors.ink-muted}'
    padding: '80px {spacing.9}'
    pattern: 'centered plain text, no icon, no title, no illustration, no CTA — used when a scoped list (Journeys, Scenarios) hits zero'
  empty-state-onboarding:
    border: '1px dashed {colors.border}'
    radius: '{rounded.xl}'
    icon-badge: '{colors.accent-wash} background / {colors.accent} icon, circular, 52px'
    heading-typography: '{typography.heading-card}'
    body-typography: '{typography.body}'
    note: 'used only for zero-Applications-onboarded Landing — a different, richer empty state than the bare in-pipeline one above; see EXPERIENCE.md#State Patterns for which is which'
  login-canvas:
    background: 'linear-gradient(165deg, #FFFFFF 0%, #F4F6FA 45%, #ECEFF5 100%)'
    decorative-pattern: 'faint dot-grid, radial-gradient(rgba(15,23,42,0.05) 1px, transparent 1px), 24px grid, decorative only'
    decorative-glow: 'radial-gradient(circle, {colors.accent-wash} 0%, transparent 70%), animated drift, decorative only'
---

## Brand & Style

The product's UI chrome carries its own wordmark, **AITestGen**, distinct from the "Application Intelligence Platform" name this document and its sibling PRD/brief use for the product line — the wordmark appears in the top bar and the Sign In screen exactly as `{typography.wordmark}` next to `{components.brand-mark}`.

The system is still a modern, data-dense, developer-grade dev-tool interface — that posture from the prior revision (2026-07-15) is unchanged. What changed, confirmed as an intentional redirect (not prototype drift) against `mockups/prototype-v3.html`: the system now loads **Inter** as a real webfont rather than relying on a native OS font stack, it **permits gradients** in two specific, deliberate places (the brand mark, and the Suite Generated hero card) rather than banning them system-wide, and cards now carry **real, soft box-shadow elevation** rather than the flat hairline-only treatment of the prior revision. **`[CORRECTED 2026-07-27]`** The accent hue itself did **not** move — it is still the prior revision's teal (`#0F766E`), confirmed by rendering `prototype-v3.html` and reading computed styles directly (the earlier claim that it moved to blue `#2563EB` was a misread of an unused JS fallback default, not the color actually in effect). The three tinted "soft" wash variants are still computed at 5%/13%/22% opacity off the real (teal) accent. Blue (`#2563EB`/`#1D4ED8`) is real in the prototype, but scoped to exactly one place — the Happy Path badge's wash/text, `{colors.happy-wash}`/`{colors.happy-strong}` — confirmed independently and unrelated to the system's one accent hue.

What did **not** change: the tone is still trustworthy, credible, and auditable rather than playful — no exclamation points, no gamified affordances, no AI confidence/risk score anywhere (see Do's and Don'ts; this is a hard product constraint carried from `EXPERIENCE.md`, not a visual-identity call). The "make an AI claim inspectable" discipline (a scannable list, selecting an item loads its full detail into a panel) is also unchanged.

**`[GAP]`** The 2026-07-15 revision made dark-mode parity a first-class, every-token commitment. `prototype-v3.html` contains **zero** dark-mode CSS anywhere (no `prefers-color-scheme`, no `data-theme` selectors, no `-dark` suffixed values) — this document therefore specifies **light mode only**, extracted faithfully from what the prototype actually contains. Whether dark mode is still a product commitment, and if so what its token values should be, needs an explicit decision before implementation; this file does not invent dark values to fill the gap.

## Colors

- **`{colors.canvas}`** (`#FFFFFF`) is the base surface for the top bar, cards, panels, and form fields. **`{colors.canvas-wash}`** (`#F8FAFC`) and **`{colors.canvas-wash-alt}`** (`#F1F5F9`) are the two supporting neutral tints — used for list-column backgrounds, segmented-control tracks, and subtle inset rows (e.g. the Journeys-included list on Generate Suite). Several screens (Login, Landing, the post-login app shell background) additionally sit on a soft decorative gradient wash (`{components.login-canvas}`) rather than a flat canvas — see Elevation & Depth.
- **`{colors.border}`** (`#E2E8F0`) is the default hairline — card edges, dividers, input borders at rest. **`{colors.border-hairline}`** (`#F1F5F9`) is used where a divider needs to all but disappear (row separators inside a list). **`{colors.border-strong}`** (`#CBD5E1`) is reserved for secondary-button and icon-button outlines that need to read as a distinct clickable control at rest.
- **`{colors.ink}`** (`#0F172A`) is the primary heading/value color. **`{colors.ink-secondary}`** (`#334155`) carries body-adjacent strong text — form labels, secondary-button text. **`{colors.ink-muted}`** (`#64748B`, ~4.6:1 on white) is the tier every real caption/meta string must use. **`{colors.ink-faint}`** (`#94A3B8`, ~2.9:1 on white — fails WCAG AA for text) is reserved for decorative or large-only use: placeholder glyphs, disabled affordances, and `{typography.label-section}` eyebrows, which are orientation labels, not the information itself.
  - **`[NOTE FOR PM/ENG]`** The raw prototype export uses `{colors.ink-faint}` for several strings that *are* real information a user needs to read — the "N journeys · N scenarios" line on a Landing app card, pagination labels ("Page 1 of 3"), and "No matches." empty-row text all render in `#94A3B8` in `prototype-v3.html`. This repeats exactly the contrast failure the 2026-07-15 revision fixed once already (see `EXPERIENCE.md#Accessibility Floor`). Implementation must recolor these specific strings through `{colors.ink-muted}`, not copy the prototype's literal color — the two-tier text-color discipline (Do's and Don'ts) is still binding even though the underlying hex values changed.
- **`[CORRECTED 2026-07-27]` `{colors.accent}`** (`#0F766E`, teal — unchanged from the 2026-07-15 revision) is the system's one accent — primary buttons, the active pipeline-stepper step, selected list rows, links, and the brand mark, confirmed by rendering `prototype-v3.html` directly rather than reading its JS source. **`{colors.accent-strong}`** (`#115E59`) is used where accent needs more weight against a light wash. The three accent washes (`{colors.accent-wash-soft}` `#0F766E0D` / 5% alpha, `{colors.accent-wash}` `#0F766E21` / 13% alpha, `{colors.accent-wash-strong}` `#0F766E38` / 22% alpha) are computed off the accent color, same alpha percentages as before — expressed here as 8-digit hex (`#RRGGBBAA`) per design-md-spec's hex-string requirement for `colors` tokens, not as `rgba()` strings. If the accent ever changes, these three should be recomputed from it, not hand-tuned.
- **The Happy Path badge is the one place blue actually appears** — `{colors.happy-wash}` (`#EFF6FF`) / `{colors.happy-strong}` (`#1D4ED8`), confirmed by the same rendering pass and independent of `{colors.accent}`/`{colors.accent-strong}`. This is a fixed, scoped badge color, not evidence of a system-wide blue accent.
- **Contrast ratios for load-bearing wash+text pairs** (WCAG 2.1 AA floor is 4.5:1 for normal-weight text): `{colors.happy-wash}`/`{colors.happy-strong}` ≈ **6.16:1** (AA pass, not AAA); `{colors.danger-wash}`/`{colors.danger-strong}` ≈ **5.92:1** (AA pass); `{colors.warn-wash}`/`{colors.warn-strong}` ≈ **4.84:1** (AA pass, close to the floor); `{colors.good-wash}`/`{colors.good-strong}` ≈ **4.79:1** (AA pass, close to the floor). `{components.button-primary}`'s white-on-`{colors.accent}` fill ≈ **6.55:1** (AA pass, teal `#0F766E`). All combos are calculated directly from the hex values above, not inherited/pre-verified from the prototype — none was previously stated anywhere in this document.
- **Semantic colors — `{colors.good}` (green), `{colors.danger}` (red), `{colors.warn}` (amber) — remain a separate palette from accent,** same discipline as the prior revision: green means Ready/generated/healthy, red means destructive/error, amber means attention/incomplete. None of the three substitutes for accent, and accent never carries semantic meaning.
- **Scenario type badges** use a small, specific three-color set read directly from the prototype's `typeMeta` map: Happy Path (`{colors.happy-wash}` / `{colors.happy-strong}`), Negative Path (`{colors.danger-wash}` / `{colors.danger-strong}`, labeled "Negative Case" in the raw prototype copy — kept as "Negative Path" here per the established product term from the PRD glossary), Edge Case (`{colors.warn-wash}` / `{colors.warn-strong}`).
- **Gradients are now permitted, but only in two named places** — `{components.brand-mark}` and `{components.suite-hero-card}` — both a 135deg accent-to-dark-overlay ramp. Every other surface (buttons, cards, badges, inputs) stays a flat fill. Decorative canvas washes (Login, Landing, the app shell background) use soft radial/linear washes between near-white and pale slate tones — these are atmosphere, not the accent-gradient pattern, and must not be read as license to gradient-fill controls.

## Typography

- **`{typography.font-ui}`** is now **Inter**, self-hosted as a real `@font-face` webfont (the prototype embeds the full Google Fonts Inter charset, including cyrillic/greek subsets) — this replaces the 2026-07-15 revision's native-system-stack-only rule. Inter carries every heading, label, button, and body string.
- **`{typography.font-mono}`** is unchanged in spirit — reserved for filenames, route/API text, and generated code — though it now renders as `'SFMono-Regular', Consolas, ui-monospace, Menlo, monospace` rather than the prior ui-monospace-first stack. It appears on generated test filenames in the Suite Generated disclosure, the reference-screenshot placeholder label, and inline route chips.
- The scale runs `{typography.display}` (28px/600, the Sign In marketing headline, used nowhere else) → `{typography.wordmark}` (22px/800, the literal "AITestGen" lockup, the only 800-weight text in the system) → `{typography.heading-page}` (19-21px/700) → `{typography.heading-card}` (15-16px/700) → `{typography.body}` (14px/400) → `{typography.label}` (13-13.5px/600) → `{typography.caption}` (12-12.5px/400) → `{typography.label-section}` (11px/700, uppercase, tracked 0.05em). Weights cluster at 400 (reading), 600 (labels/buttons/emphasis), and 700 (anything acting as a heading) — no 500, and 800 is reserved for the wordmark alone.

## Layout & Spacing

There is no persistent nav rail in this IA (unchanged from the 2026-07-15 single-application guided pipeline) — the top bar plus the pipeline stepper are the entire top-level navigation surface. Content padding is `{spacing.content-top}` (22px) top, `{spacing.content-x}` (32px) sides on pipeline screens.

The two-pane list-plus-detail pattern (Discover Journeys, Review Scenarios) runs a `{spacing.list-column-width}` (260-280px) fixed list column against a fluid detail column; the detail column's readable content caps at `{spacing.detail-max-width}` (680px) on Review Scenarios so test-data rows and expected-result text don't stretch into unreadable line lengths. Discover Journeys' detail column additionally reserves a `{spacing.reference-panel-width}` (260px) sticky-positioned slot for a reference-screenshot placeholder. Generate Suite and Suite Generated both cap their content at `{spacing.content-max}` (1720px, via `clamp()`), noticeably wider than the two-pane screens, because both are dashboard-shaped summary layouts rather than list-plus-detail ones.

Spacing is dense and control-panel-like, not editorial — the working increments (`{spacing.1}` 4px through `{spacing.9}` 24px, plus `{spacing.10}` 32px for the widest gaps) cover essentially every padding and gap value found in the prototype.

## Elevation & Depth

This is the most significant structural change from the 2026-07-15 revision, which was deliberately flat (hairline-only, zero shadows, zero gradients). **The current system uses real, soft box-shadow elevation as its primary depth cue.** Every card and panel (`{components.card-panel}`) carries both a 1px `{colors.border}` hairline *and* a soft two-layer shadow (`0 4px 14px -3px rgba(15,23,42,0.1), 0 1px 3px rgba(15,23,42,0.06)`), not one or the other. Dropdowns and popovers (the kebab menu, the user-avatar menu) sit higher, with a single more diffuse shadow (`0 8px 20px rgba(15,23,42,0.12)` to `0 12px 28px rgba(15,23,42,0.14)`). The top bar itself carries a faint shadow separating it from scrolled content beneath (`0 2px 8px -4px rgba(15,23,42,0.10)`).

Two surfaces carry a deliberate gradient-as-object treatment rather than a shadow: `{components.brand-mark}` (a small bevel — an inset highlight top, inset shadow bottom, on top of the accent gradient fill) and `{components.suite-hero-card}` (the Suite Generated screen's celebratory header card, with two oversized soft white decorative circles clipped inside it). Both are named, singular uses — not a general "cards can have gradients now" license.

## Shapes

An eight-step radius scale, used with intent:

- **`{rounded.xs}` (6px)** — badges, status pills, small icon-button triggers (kebab menu, back button at its smallest).
- **`{rounded.sm}` (7px)** — the brand mark at its smaller (30px) size.
- **`{rounded.DEFAULT}` (8px)** — buttons, inputs, selects — the default "interactive control" radius.
- **`{rounded.md}` (9px)** — list rows (Journey/Scenario cards in the list column), the brand mark at its larger (36px) size.
- **`{rounded.lg}` (12px)** — the test-data callout, stat tiles, the generated-tests disclosure panel, dropdown menus.
- **`{rounded.xl}` (14px)** — the two-pane list-plus-detail container, the Connect App form card, the onboarding empty-state panel.
- **`{rounded.2xl}` (16px)** — reserved for the single largest, most celebratory surface in the system: the Suite Generated hero card.
- **`{rounded.full}`** — pills (status/badge shapes at their pill-shaped edge, environment badge), avatars, step circles, small decorative dots.

Circles are still reserved for identity and progress affordances: the user-initials avatar, the pipeline stepper's numbered step-circles, the Discovery Progress spinner, and small dot markers.

## Components

- **Top bar** (`{components.top-bar}`) — flush header on every authenticated screen: `{components.brand-mark}` + `{typography.wordmark}` at the left (click returns to Landing); once inside an Application's pipeline, a divider, the Application's name (`{typography.heading-card}`), and an environment pill (`{colors.accent-wash}` / `{colors.accent}`) appear beside it; a circular user-initials avatar sits at the far right, opening a menu (name, email, Log out) on click.
- **Pipeline stepper** (`{components.pipeline-stepper}`) — unchanged in structure from the 2026-07-15 revision (Connect App → Discover Journeys → Review Scenarios → Generate Suite, one numbered circle + label + connector per step), restyled to the current token set. Circles are 23px, connectors are short (34px) 1.5px-tall bars.
- **Buttons** — `{components.button-primary}` (solid accent fill, white text, flat — never the brand-mark gradient) for the one primary action per screen; `{components.button-secondary}` (bordered, white fill) for everything else. No tertiary/ghost/link-styled button beyond plain text links (e.g. "Forgot password?").
- **Icon button** (`{components.icon-button}`) — a bare, borderless control at `22px-32px` square, `{rounded.xs}` radius, transparent background at rest that fills `{colors.border}` on hover. No icon-fill color is specified per-instance here (see the specific control using it — e.g. the kebab-menu trigger's three-dot glyph); the shape/sizing/hover token is the same across every use. This is the smallest interactive-control size in the system, one step below `{components.button-secondary}`.
- **Badge** (`{components.badge}`) — a small, non-interactive label used for Scenario type (Happy Path / Negative Path / Edge Case), appearing in Review Scenarios list rows, its detail panel, and the Suite Generated per-scenario rows. `{rounded.xs}` radius, `10.5px-12px`/600 text, always the tinted-wash-background + saturated-text-of-the-same-hue pattern — never a solid fill (see Do's and Don'ts). Three variants, each a wash/text color pair: Happy Path (`{colors.happy-wash}` / `{colors.accent-strong}`), Negative Path (`{colors.danger-wash}` / `{colors.danger-strong}`), Edge Case (`{colors.warn-wash}` / `{colors.warn-strong}`). No icon glyph — text label only, no border.
- **Status pill** (`{components.status-pill}`) — visually a sibling of badge (same tinted-wash pattern, `{rounded.xs}` radius), one step bolder: `10.5px`/700 text. Reserved exclusively for Scenario readiness — Ready (`{colors.good-wash}` / `{colors.good-strong}`) and Needs Data (`{colors.warn-wash}` / `{colors.warn-strong}`) — appearing in the Review Scenarios list row and detail-panel header.
- **Kebab menu** (`{components.kebab-menu}`) — a `22px` `{components.icon-button}` trigger (three-dot glyph) at the right edge of every Journey/Scenario list row, always visible, never hover-gated. Its dropdown is `{colors.canvas}` background, `{colors.border}` hairline, `{rounded.xs}` radius, `0 8px 20px rgba(15,23,42,0.12)` shadow, anchored below the trigger. Exactly two items — Rename (default text color) and Delete, which renders in `{colors.danger}` with a `{colors.danger-wash}` hover fill.
- **Connect App form** — a single consolidated card (unchanged IA from 2026-07-15): Application name, Base URL, a divider, then Environment and Authentication method as a paired 2-up grid of native `<select>` elements. Authentication method's three concrete options, read directly from the prototype: **Username & Password, API Key, OAuth Client Credentials** — each reveals its own credential field(s) below the grid (Username+Password fields for the password method; a single API Key field for the API-key method). `[GAP]` the prototype defines no visible field set for OAuth Client Credentials specifically — selecting it reveals nothing further in the current export; this needs explicit confirmation before implementation, not an invented Client ID/Secret pair. `[GAP]` PRD Open Question 8 (the SSO/MFA session-handoff mechanism) remains unaddressed by this option set, unchanged from the prior revision.
- **List row + detail panel** — Discover Journeys' and Review Scenarios' shared core pattern is unchanged: a scannable list on the left (name, `⋯` menu, always-visible not hover-gated), selecting a row loads its detail into a panel on the right. Visually restyled per the current token set: `{components.list-row}` gets a 3px accent left-border plus an accent-wash fill when selected, and a soft shadow that deepens slightly on hover.
  - Discover Journeys' detail panel shows the Journey's name, description, a numbered step list (route/action detail + a stage tag), and a sticky **reference-screenshot placeholder** column (a diagonal-striped `repeating-linear-gradient` swatch labeled "journey screenshot" in `{typography.mono-inline}`) — new in this revision, not previously specified.
  - Review Scenarios' detail panel shows a type badge + a Ready/Needs Data status pill, the Scenario name, a numbered Test Steps list, a **Test Data** callout (`{components.test-data-callout}` — labeled input rows with a red required-marker, and an inline "Required to generate this test" warning under any still-empty required field), and an **Expected Result** block styled as a green-left-bordered rule (`{components.expected-result-rule}`).
- **Row `⋯` menu** — Discover Journeys rows render exactly two items: **Rename, Delete** (in `{colors.danger}`). Review Scenarios rows render the same two visible menu items (Rename, Delete); a scenario's fuller "edit" surface is the inline Test Data field-editing in its detail panel, not a separate destructive menu action — see `{EXPERIENCE.md#Component Patterns}`.
- **Scenario status filter** (`{components.segmented-filter}`) — a 3-way segmented control (All / Ready / Needs Data) above the Review Scenarios list, new in this revision. Each Scenario card in the list also carries its own Ready/Needs-Data `{components.status-pill}`.
- **Discovery Progress** — a centered card: a spinning ring (`{colors.accent}` arc on a pale teal track), the business-language stage label per `{EXPERIENCE.md#State Patterns}` (unchanged mechanism — this document does not adopt the prototype's separate rotating "Currently exploring: {business area}" line as a product behavior; see `reconcile-prototype-v3.md`), a thin indeterminate progress bar, and a 4-up metric-tile row (`{components.stat-tile}`) restyled but not newly specified in content.
- **Generate Suite panel** — a 2-column layout: a form card (Suite name, Target environment select, a 2-up Journeys/Scenarios count pair, a primary generate button) beside a summary card (a scrollable "Journeys included" list, and a checklist of green-check confirmations). Visual restyle only; behavior unchanged from the 2026-07-15 revision's placeholder-execution caveat.
- **Suite Generated** (`{components.suite-hero-card}` + `{components.generated-tests-disclosure}`) — resolves the prior revision's `[GAP]` for what appears after generation completes. A gradient hero card shows the suite name, "Generated {N} test cases across {N} journeys · Est. runtime {X}", a **Download Test Suite** button, and a **Go to Dashboard** button (read as "return to Landing" per the 2026-07-27 reconciliation — there is no separate Dashboard screen). Below it, three `{components.stat-tile}`s (Test cases / Journeys covered / Est. runtime) and a collapsible **Generated Tests** disclosure grouped by generated file, each group expandable to a per-scenario row (type badge, name, a secondary "Code" button). `[NOTE FOR PM/ENG]` The prototype's own generated filenames and single-file download are a TypeScript `.spec.ts` prototype-tool default (one file per Journey, `slugify(journey) + '.spec.ts'`) — the visual *pattern* (grouped-by-file, expandable, per-scenario Code button) is adopted, but the actual artifact stays the locked Python pytest/pytest-playwright suite-folder project (Story 4.3/FR-34); implementation must group by the real generated `.py` file structure, not literally reproduce the prototype's TS filenames.
- **Empty states** — two distinct patterns, not one:
  - `{components.empty-state-bare}` — a scoped list (Discover Journeys, Review Scenarios) hitting zero items shows bare centered text only: "All journeys have been removed." / "No scenarios remain — add journeys back to generate scenarios." No icon, title, or CTA.
  - `{components.empty-state-onboarding}` — the Landing screen, when a user has connected **zero Applications at all**, shows a richer dashed-border panel: icon badge, "No projects yet" heading, one line of body copy, and a primary "+ Create New Project" button. This is a different situation from a single Application's journeys all being deleted (which keeps that Application's card on Landing and shows the bare pattern one level down, inside its Discover Journeys screen) — see `{EXPERIENCE.md#State Patterns}` for the full disambiguation, since the prototype's own demo data conflates the two.
- **Login canvas** (`{components.login-canvas}`) — Sign In sits on a soft diagonal white-to-pale-slate gradient wash with a faint decorative dot-grid overlay and a slow-drifting soft accent-tinted glow; this is atmosphere, not the brand-mark gradient pattern. Sign In itself (fields, buttons, SSO link) is unchanged from the prior revision — see `{EXPERIENCE.md#Foundation}`.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use `{colors.accent}` only for primary actions, active/selected state, and links | Use `{colors.accent}` for semantic status (success/error/warning) or decoratively |
| Route all real label/caption/metadata text through `{colors.ink-muted}` (~4.6:1) | Use `{colors.ink-faint}` for any real text a user needs to read — recolor prototype strings that do this, don't copy them (see Colors note above) |
| Reserve gradients for `{components.brand-mark}` and `{components.suite-hero-card}` only | Add a gradient fill to a button, input, badge, or generic card |
| Give every card/panel both a 1px `{colors.border}` hairline and its specified soft shadow | Add elevation as a single choice of "border only" or "shadow only" — this system uses both together |
| Pair every badge/status-pill as a tinted wash + saturated text of the same hue | Fill a badge or status pill as a solid color block |
| Keep Journey rows to a two-item menu (Rename, Delete) | Add a third Journey-row menu action (Edit) — rejected 2026-07-27 as prototype drift, not a product decision |
| Keep every AI-inferred item's UI free of any confidence, risk, or importance signal | Add a score, percentage, star rating, or priority flag anywhere near discovered/inferred content — a hard product constraint (PRD §5 Non-Goals), not an aesthetic call |
| Group generated tests by their real Python suite-folder structure | Reproduce the prototype's single-file TypeScript download literally |
