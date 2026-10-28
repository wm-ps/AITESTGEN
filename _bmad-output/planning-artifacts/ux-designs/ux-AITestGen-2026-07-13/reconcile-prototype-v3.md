---
updated: 2026-10-27
---

# Prototypes vs. the shipped product

The mockups folder holds four prototypes: prototype v1, prototype v2 (standalone), prototype v3 and the **Vantage v2** prototype. They are kept as history and are not edited. This note explains how the shipped product relates to each of them. `DESIGN.md` and `EXPERIENCE.md` describe the product as it is now and win on any conflict with a prototype.

## Summary

The product began as a four-step guided wizard: Connect App, then Discover Journeys, then Review Scenarios, then Generate Suite. That is the shape prototypes v1 to v3 show. The product has since been rebuilt around the **Vantage v2** prototype: a left-sidebar shell, an organization-wide Overview, an Applications list, and per-application tabs that can be opened in any order. The wizard and its stepper are gone.

## Prototype v1, v2 and v3

These shaped the early decisions, but most of their structure has been replaced.

**Still true from them:**
- The teal accent (#0F766E) and the tinted-wash style for status labels.
- Soft-shadow cards and light mode only.
- Rename and delete as the only actions on a journey. There is no approve/reject gate and no AI confidence score.
- Journey evidence shown as page-by-page steps. The placeholder screenshot column in v3 is now a real captured screenshot on each journey card.

**Replaced:**
- **The wizard and stepper** are replaced by sidebar navigation and application tabs.
- **The Landing screen with project cards** is replaced by the Overview dashboard plus the Applications table.
- **The "Generate Suite" form and "Suite Generated" hero card** are replaced by a progress screen on the Test cases tab (stages, counts, Terminate, Retry, Download, Run) and then the test case list.
- **The Inter font** is replaced by Instrument Sans, with IBM Plex Mono for code.
- **The auth-method choice** (Username & Password / API Key / OAuth): the product offers only a "requires sign-in" toggle with username and password, or no sign-in. API-key and OAuth were never built.
- **The scenario "Ready / Needs Data" filter and pill** are replaced by labels on each field ("Required for this scenario", "Optional — auto-filled if left blank") plus Auto-generate for test data.
- **Python test download:** the downloaded project is TypeScript Playwright, not Python.

**Ideas v3 had that were rejected then and later shipped in another form:**
- **The "Workspace" home with Overview, Test Suite and Runs tabs.** It was rejected at the time because tests could not be run inside the product. Running tests is now a core feature, so the per-application Overview, Test cases and Test runs tabs exist, with live pass/fail, health tiers and reports.
- **The live discovery activity caption.** The product shows a four-stage progress list (Exploring pages, Capturing screenshots, Grouping flows, Mapping journeys) instead of a scrolling feed. Journeys appear live as they are found.

**Still not built:** the "Discovery Attention" approve/skip gate. Discovery does sometimes get stuck needing data it doesn't have, but there is no screen yet for answering it.

## Vantage v2 prototype

This is the reference for the current product. The following match it:
- **Shell and navigation:** the sidebar, the top bar with breadcrumb and account menu, the Overview dashboard, the Applications table, and the application tabs.
- **Palette:** the light grey page, white panels, the near-black text ladder, the teal accent with its deeper shades, and green for pass and red for fail.
- **Status chips and tables:** flat status chips on run headers, bare coloured status text in the Applications table, and plain Prev/Next paging on Test runs.
- **Menus:** the vertical ⋮ kebab on every row menu.

The product goes beyond the prototype in these areas:
- Record and play, and Author a test case.
- Schedules and Activity.
- The viewer role.
- The flaky flag, with purple reserved for it.
- Self-healing chips, cancelling a run, the HTML report and the run-completed email.
- Validating credentials before Discovery starts, and the option to add an app without Discovery.

## Open differences

- A few busy labels and placeholders in the product still break the house rules (a static "Saving…" with no dots; placeholders such as "https://"). These are listed in `DESIGN.md`.
- The invite dialog says invitations last 7 days, but they actually expire after 72 hours.
- The schedule dialog suggests Discovery can be scheduled, but only test runs can.
