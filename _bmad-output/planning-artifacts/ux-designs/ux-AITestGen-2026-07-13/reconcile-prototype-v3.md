# Reconciliation — prototype-v3.html (2026-07-27)

> Input: `mockups/prototype-v3.html` (638KB bundled SPA export; templated with a custom `sc-if`/`sc-for`/`sc-camel-on-click` DSL over `this.state`, embedded on a single ~638KB line around line 392). Reconciled against the locked (2026-07-21) `DESIGN.md`/`EXPERIENCE.md` and `.memlog.md` entries 38-47 (the authoritative resolution record for this round). This report records what v3 introduced, what was adopted vs. rejected and why, and — per the Finalize process — dropped qualitative ideas that might be worth reconsidering later even though rejected now.

## What v3 introduced

v3 restructures around the same 4-step pipeline (`login`, `landing`, `import`, `scanning`, `journeys`, `scenarios`, `suite`, `suiteResult` screens) but adds two entirely new screens (`attention`, `workspace`) and a materially different visual system:

- **New screens:** `attention` ("Discovery Attention" — an approve/skip gate for uncertain discoveries plus manual entry for missing fields) and `workspace` (a tabbed Overview/Test Suite/Runs/Application home, including live Passed/Failed/Not Run test-execution counts on the Runs tab).
- **New visual direction:** Inter webfont (replacing native-stack-only), permitted gradients on two named surfaces (replacing zero-gradient), soft box-shadow card elevation (replacing flat-hairline-only), and a blue accent (`#2563EB`, read from `this.props.accentColor || '#2563EB'` in the component source) replacing the prior teal (`#0F766E`).
- **New behavioral details on existing screens:** a Review Scenarios ready/needs-data filter and status pill (computed from Test Data completeness), a reference-screenshot placeholder column on Discover Journeys, a rotating "Currently exploring: {business area}" caption during Discovery Progress, a vestigial (unwired) Journey description-edit function, and a fully fleshed-out Suite Generated screen.
- **Confirmed unchanged:** the 4-step pipeline shape and its stepper labels, Sign In, and the Journey row's rendered menu (Rename/Delete only, matching the lock despite the vestigial edit function in the JS).

## Adopted

| What | Why | Memlog ref |
|---|---|---|
| Full visual identity redirect — Inter, permitted gradients (brand mark + Suite Generated hero card only), soft shadow elevation, blue accent `#2563EB` with computed 5/13/22% opacity washes | Explicitly called an intentional adopted redesign, not drift — extracted as precisely as the prototype's actual CSS/JS allows | entry 49 |
| Review Scenarios ready/needs-data filter + status pill, Test Data completeness gating | Additive detail on an existing Story 4.1 screen; doesn't conflict with any locked decision | entry 50 (item re: Scenarios status filter) |
| Suite Generated screen (hero card, stat tiles, generated-tests-by-file disclosure, Download Test Suite / Go to Dashboard) | Resolves a `[GAP]` flagged since the 2026-07-15 revision — what appears after generation completes | entry 41 (original gap), resolved this round |
| Landing existing-Application persistence rule (Application card survives on Landing regardless of Journey count; clicking it resumes the pipeline at Discover Journeys) | v3's actual behavior (Landing reverting to "No projects yet" at zero Journeys) was diagnosed as an artifact of one shared `hasJourneys` boolean over a single hardcoded demo Application, not a real rule | entry 53 |
| Discover Journeys bare empty state ("All journeys have been removed.", no title/icon/CTA) | Matches what the prototype actually renders; recovery-CTA question left open, not fabricated | entry 52 |
| Connect App auth-method option set (Username & Password / API Key / OAuth Client Credentials) | Concrete option set for Story 1.4; explicitly does not resolve PRD Open Question 8 | entry 50 |

## Rejected

| What | Why | Memlog ref |
|---|---|---|
| Journey row Edit option | Rename+Delete is the locked V1 action set; the prototype's JS retains an unwired `startEditJourney` function but no visible button calls it — read as leftover code from an earlier build, not a reintroduced decision | entry 44 |
| "Discovery Attention" screen (approve/skip gate + manual field entry) | Unauthorized scope creep — reintroduces a reviewer-gate pattern the Trusted-Knowledge-Model-by-default design (FR-14) was built to remove | entry 45 |
| "Workspace" screen (Overview/Test Suite/Runs/Application tabs, live Passed/Failed results) | No return-to-project home screen is in scope; the Runs tab specifically implies a live CI read-back channel the architecture doesn't support (coverage stays generated-vs-not only) | entry 46 |
| Raw rotating "Currently exploring: {business area}" live-feed caption on Discovery Progress | Reads as exactly the "raw scrolling technical live-feed of discovered areas" the locked decision rejects, even though its individual items are business-language phrases rather than raw routes | entry 47 |
| Single-file TypeScript (`.spec.ts`) suite download | Export-tool generic default, not a real requirement change; download stays the locked Python pytest/pytest-playwright suite-folder project | entry 48 |

## Dropped qualitative ideas worth reconsidering later

These are rejected for V1 but flagged, per the Finalize process, as ideas with some underlying merit that a future round could pick up deliberately rather than by prototype drift:

1. **Discovery's own uncertainty about specific candidates or fields.** "Discovery Attention" is rejected wholesale as a gate, but the underlying idea — that discovery sometimes captures a field it can't confidently label, or a candidate Journey it's less sure about — isn't inherently at odds with the Trusted-Knowledge-Model-by-default design. A future version could surface that uncertainty as a passive annotation on an already-admitted Journey/field (not a gate blocking entry) without reintroducing an approval step. This would need explicit product framing to avoid drifting back into a confidence/risk score, which is a separate hard non-goal (PRD §5).
2. **A lightweight application-health or coverage rollup.** "Workspace"'s Overview tab (a health headline, a "Run Suite" action, generated-vs-not counts) gestures at something UJ-2 (Devon, release-readiness) actually needs — and UJ-2 has had no supporting screen since the 11-screen shell was cut on 2026-07-15. The Runs tab's live pass/fail is correctly rejected (no CI read-back exists), but a coverage-only rollup (generated vs. not, per the already-locked stance) could be a legitimate, much smaller answer to UJ-2's gap. This is exactly the kind of "return to Landing" home surface this reconciliation didn't invent, because inventing it is a product decision, not a UX-only one — but it's worth naming as the most promising unblocked path for UJ-2 the next time that gap comes up for resolution.
3. **Reference-screenshot evidence on Discover Journeys.** v3's placeholder column ("journey screenshot") isn't wired to a real captured image in this export, but the idea of pairing a Journey's evidence trail with an actual screenshot (not just route/action text) is a plausible strengthening of the "make an AI claim inspectable" pattern this product is built around. Worth a real product decision on whether discovery should capture and store screenshots, not just a UI treatment for a placeholder.

## Gaps / unresolved items surfaced by this pass

- Dark mode: `prototype-v3.html` contains zero dark-mode CSS. The prior revision's dark-mode-parity commitment has no grounding in v3 at all; `DESIGN.md` now specifies light mode only and flags this explicitly rather than inventing dark tokens.
- OAuth Client Credentials (Connect App): the prototype reveals no credential fields for this method specifically; needs explicit confirmation of its field set.
- PRD Open Question 8 (SSO/MFA session-handoff): still unresolved; v3's three concrete auth options don't address it.
- Accessibility regression risk: several real informational captions in v3 (Landing's journey/scenario counts, pagination labels, "No matches." text) render in the decorative-only faint-gray tier that already failed AA once before (2026-07-15 fix). `DESIGN.md` and `EXPERIENCE.md` both flag this explicitly so implementation routes these strings through the muted tier rather than copying the prototype's literal color.
- Whether a completed pipeline step is clickable to jump back, and post-edit/remove row visual treatment: both carried forward as unconfirmed from the prior revision; v3 doesn't resolve either.
- Whether an edited Scenario's Test Data/steps actually feed Playwright generation, or the edit is cosmetic: carried forward unconfirmed.
- UJ-2 (Devon/release-readiness) remains blocked with no supporting screen — see Dropped Idea #2 above for the most promising unblocked direction, not adopted here.
