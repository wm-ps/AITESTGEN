---
baseline_commit: 5169a5ef67425926d33f632e224328f82a2cd2c7
---

# Story 2.14: Widget & Container Coverage — Frames, Shadow DOM, Tabs, Dialogs, Windows, Uploads

*Implements spine boxes **A (capture half)** and **C** of `docs/DISCOVERY_ENGINE_V2.md`. Rewritten and significantly expanded 2026-08-03 following a feasibility review — iframe traversal and shadow-DOM piercing were entirely absent from the 2026-07-29 batch and from the current crawler. **This story should be built first in Epic 2's remaining backlog** (see Dev Notes).*

Status: in-progress  # Tasks 1,2,4,5,6,7 implemented and verified 2026-08-03 against real Chromium
  # + real fixture routes. Task 3's ARIA-first tab/dialog detection is done; its structural-
  # heuristic low-confidence fallback for non-ARIA elements (AC 7) is NOT implemented — a real,
  # honestly-tracked gap, not a false completion. See Dev Agent Record.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want the platform to see inside the containers real enterprise applications actually use — frames, shadow roots, tabs, modals, popups — and to handle uploads,
so that discovery doesn't report an empty page and call it success.

## Acceptance Criteria

1. **Given** a page containing same-origin `iframe` elements, **when** it is captured, **then** each frame is traversed recursively to a configurable depth (default 3); the accessibility tree, DOM structure and interactive elements inside it are captured as part of the containing page's state; and cross-origin frames — which are unreachable by design — are logged as **unreachable containers** and counted in the coverage report (Story 2.22), never treated as a failure. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE]
2. **Given** a page whose components attach **open shadow roots**, **when** it is captured, **then** traversal descends into those roots for both accessibility-tree/DOM capture and Story 2.10's structural fingerprint; **closed** shadow roots are genuinely opaque and are logged as unreachable containers rather than failing the capture. [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE; #B — IDENTIFY]
3. **Given** a tab-group widget (ARIA `role="tablist"`/`"tab"`, or an equivalent framework-rendered pattern), **when** detected, **then** each tab is a Tier-1 candidate action (Story 2.11) whose revealed content is observed and classified as its own state or a VARIANT via Story 2.10. [Source: docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE; FR-41]
4. **Given** an action opens a dialog/modal/overlay, **when** its contents are observed, **then** they are fingerprinted as a nested state even though the URL does not change, **and** the dialog is reliably closed before exploration continues — attempting, in order: Escape, an element whose accessible name matches Close/Cancel/X, a role-based close button, and finally a forced navigation back to the pre-dialog URL. [Source: docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE; FR-41]
5. **Given** an action opens a new browser tab/window, **when** it is same-origin and in scope, **then** it is followed and explored as a linked sub-flow recorded against the opening action; **when** it is cross-origin or out of scope, **then** it is flagged, not followed, and focus returns to the original tab. [Source: FR-41]
6. **Given** a `type="file"` input, **when** encountered, **then** it is routed to the Data Resolver (Story 2.13) for a safe placeholder file, generated once per run and reused across every upload field, logged like any other resolved value. [Source: FR-41]
7. **Given** an interactive element exposing no standard ARIA role, **when** detected, **then** structural heuristics (tag type, click handlers, class-name conventions, position) apply as a fallback and the resulting `Action`/`Component` is marked **low confidence**, surfaced for review in Story 2.22 rather than silently trusted at full fidelity. [Source: FR-41; docs/DISCOVERY_ENGINE_V2.md#C — ENUMERATE]

## Tasks / Subtasks

- [x] Task 1: **iframe traversal** (AC: 1)
  - [x] Enumerate frames via Playwright's frame API from the top-level page; for each same-origin frame, run the existing capture routine (accessibility tree, DOM, interactive elements) and attribute the results to the containing page's state
  - [x] Recurse into nested frames to a configurable `max_frame_depth` (default 3); record the depth actually reached
  - [x] Cross-origin frames: record an `unreachable_container` entry (type `cross_origin_frame`, plus the frame URL/name) and continue. This is a coverage fact to report, not an error to retry
  - [ ] `[DEFERRED — depends on Story 2.21]` Actions found inside a frame carry their frame path so Story 2.21 can build a locator that resolves through the frame chain — 2.21 doesn't exist yet; captured actions inside a frame are attributed to the containing page's URL but don't yet carry a distinct frame-path locator segment
- [x] Task 2: **Shadow DOM piercing** (AC: 2)
  - [x] Walk shadow roots recursively during capture, injected via `page.evaluate`, collecting structure and interactive elements inside open roots — via an `attachShadow`-tracking init script, since `element.shadowRoot` reads back `null` identically for "no shadow root" and "closed shadow root" (there is no other DOM signal)
  - [ ] `[DEFERRED — depends on Story 2.10]` Feed shadow content into Story 2.10's structural fingerprint — 2.10 doesn't exist yet; open-root interactive elements are discovered and clicked (via Playwright locators, which already pierce open shadow roots) but not yet fed into a fingerprint that doesn't exist
  - [x] Closed roots: record an `unreachable_container` entry (type `closed_shadow_root`) and continue
  - [x] Note for implementation followed: capture uses `page.evaluate` traversal; clicking discovered shadow-DOM buttons uses plain Playwright role/text locators, which already pierce open shadow roots
- [x] Task 3: ARIA-first widget detection with heuristic fallback (AC: 3, 7) — **partial**
  - [x] New `widgets.py` in `apps/workers/discovery` inspecting the accessibility tree first for tabs and dialogs
  - [x] `role="tab"`/`"tablist"` → tab handling; `role="dialog"`/`"alertdialog"`/`aria-modal="true"` → dialog handling
  - [ ] **NOT IMPLEMENTED**: no standard role → structural heuristics with a `confidence: low` marker persisted on the resulting `Action`/`Component` (AC 7). This needs a schema change (`confidence` field) and materially widens what gets clicked (arbitrary `div`/`span` with an `onclick`, not just `button`/dead-href `a`) — a real risk/scope tradeoff deliberately not rushed. Tracked as a genuine gap, not marked done.
- [x] Task 4: Tab handling (AC: 3)
  - [x] Each detected tab is clicked and its revealed content captured as an Action; `[DEFERRED — depends on Story 2.11]` formal Tier-1 tagging and Story 2.10 state classification of revealed content don't exist yet — this story only needs the tab discovered and exercised, per its own Dev Notes
- [x] Task 5: Dialog handling and reliable close (AC: 4)
  - [x] Overlay contents fingerprinted as a nested state via a synthetic `CapturedPage` row (`#dialog:<opener>`); `[DEFERRED — depends on Story 2.10]` real state classification against it doesn't exist yet
  - [x] Implemented the close ladder (Escape → accessible-name match Close/Cancel/X/Dismiss → aria-label close → forced navigation to the pre-dialog URL), verifying after each attempt that the overlay is actually gone
  - [x] Bounded, deterministic ladder; on exhaustion, force-navigates and records `dialog_closed`/`unreachable_container` diagnostics so the run continues
- [x] Task 6: Multi-tab/window handling (AC: 5)
  - [x] Listens for Playwright's `popup` event on the page, queued and drained after every click/submit
  - [x] Same-origin → followed as a linked sub-flow (`CapturedPage` + `CapturedTransition` back to the opening action); cross-origin → flagged via a `widget_coverage` diagnostic (`container: cross_origin_popup`) since Story 2.15's `BlockedTask` doesn't exist yet — a `ponytail:`-equivalent documented substitution, same pattern as Story 2.9's own soft-dependency on 2.10; focus returns to the original page (the popup is only read, never switched to)
- [x] Task 7: File-upload routing (AC: 6)
  - [x] Detects `input[type=file]` during field enumeration; routes to a placeholder generated directly in this story rather than Story 2.13's Data Resolver, which doesn't exist yet — same documented-substitution pattern as above
  - [x] Generates one minimal PNG + one minimal PDF once per process (lazily, on first use) and reuses them across every upload field for the run
- [x] Task 8: Verify end-to-end (AC: 1-7) — **all covered except the AC 7 case, since AC 7 itself isn't implemented**
  - [x] Fixture page embedding a same-origin iframe containing a form: the form's fields and actions are captured and attributed to the containing state
  - [x] Fixture page with a cross-origin iframe: recorded as an unreachable container, run continues
  - [x] Fixture page using a custom element with an open shadow root containing a button: the button is discovered. `[PARTIAL]` "the structural fingerprint differs from an otherwise-identical page" is not asserted — no fingerprint exists yet (Story 2.10)
  - [x] A tab group's tabs are each explored and classified (classified = exercised + captured; not Story 2.10 state classification, which doesn't exist yet)
  - [x] A modal is observed as a nested state and reliably closed; a deliberately unclosable modal triggers the forced-navigation fallback rather than stranding the run
  - [x] A same-origin popup is followed and linked; a cross-origin popup is flagged with focus returned
  - [x] A file input receives a placeholder and the choice is logged
  - [ ] **NOT COVERED** (AC 7 not implemented): a `div`-with-click-handler and no ARIA role produces a low-confidence `Action` row

## Dev Notes

- **Build this story first.** It has the fewest dependencies in the remaining batch and it raises the floor for every later story: Story 2.10 cannot fingerprint correctly without shadow content, Story 2.11 cannot enumerate candidates it never saw inside a frame, and Story 2.21 cannot build durable locators for elements that were never captured. Sequencing it sixth (as the 2026-07-29 batch did) means everything built before it gets partially redone.
- **Frames and shadow DOM were completely missing, and this is not an exotic gap.** Verified at review time: `iframe`, `shadow DOM` and `web component` appear in zero stories, epics, PRD sections or architecture decisions, and `crawler.py` has no frame or shadow handling at all. SAP portals, Salesforce Lightning, and virtually every embedded legacy application put their real content inside a frame; Salesforce Lightning Web Components, Polymer and Stencil-based design systems put theirs inside shadow roots. Against those targets the current crawler captures the empty host page, finds nothing interactive, and reports the page successfully explored. That is the worst possible failure mode — a confident false negative.
- **Framework independence comes from ARIA being a specification, not a framework feature.** React, Angular, Vue, Svelte and server-rendered markup all expose the same accessibility surface when built properly, which is why this story special-cases no framework anywhere and must continue not to. What actually varies is the **component library**: a Material-UI `<Select>` is not a `<select>` — it is a `div` with `role="button"` that opens a portal-rendered listbox appended to `document.body`, entirely outside the triggering element's subtree. Ant Design, Radix and most mature libraries do implement ARIA correctly; bespoke in-house design systems frequently do not, which is exactly what AC 7's low-confidence fallback is for.
- **Portal-rendered content is the subtle case in AC 4.** A modal or dropdown appended to `document.body` is not a descendant of the element that opened it, so a subtree-scoped observer will miss it entirely. Detect overlays by watching for newly visible top-level containers after an action, not by looking inside the trigger's subtree.
- **Dialog close is the highest-risk piece of this story.** An undetected or failed close leaves the crawl operating inside a modal for the remainder of the run, producing garbage for every subsequent state. The forced-navigation fallback is mandatory, not a nice-to-have — build it in the same pass as the happy path, not afterwards.
- **Unreachable containers are a coverage fact, not an error.** Cross-origin frames and closed shadow roots are permanently invisible to any DOM-based crawler. Recording them explicitly is what lets Story 2.22 tell a user "we could not see inside 4 regions of this application" instead of quietly under-reporting the app's size.

### Project Structure Notes

- Adds `widgets.py` to `apps/workers/discovery`, plus frame/shadow traversal in the capture path. Adds an `unreachable_container` record (small table or typed rows — pick the smaller diff) consumed by Story 2.22.
- No new domain entities beyond that; `SyntheticDataEntry` (Story 2.13) covers upload placeholders and `BlockedTask` (Story 2.15) covers cross-origin window deferrals.
- Depends on Story 2.9 (readiness must gate capture, including capture inside frames). Feeds Stories 2.10 (fingerprint), 2.11 (candidate enumeration) and 2.21 (locator capture).

### References

- [Source: docs/DISCOVERY_ENGINE_V2.md#A — OBSERVE, #C — ENUMERATE, #6 Honest capability gradient]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.14]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-29.md — Section 13 of the source design document]
- [Source: _bmad-output/implementation-artifacts/2-2-autonomous-exploration-captures-evidence.md — the existing form/action capture this story extends]

## Previous Story Intelligence

Story 2.2's crawler captures `Action`/`Form` rows via label/selector-shape grouping (representative-action sampling) — extend that same capture path with widget- and container-specific branches rather than building a parallel mechanism. Its per-page action-label cap (AD-15 rule 2) still applies to elements found inside frames and shadow roots; confirm the cap is applied to the merged candidate set, not per container, or a frame-heavy page will exceed the intended budget.

## Latest Technical Notes

Playwright Python (architecture-pinned 1.57+) provides frame enumeration, popup/new-page events, accessibility-tree snapshots and locators that pierce open shadow roots. Shadow-root *traversal* for capture requires an injected `page.evaluate` walk over `element.shadowRoot` — verify the exact current API surface at implementation time.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Completion Notes List

- Implemented Tasks 1, 2, 4, 5, 6, 7 in full against real Chromium + real fixture routes; Task 3 partially (ARIA tab/dialog detection, not the non-ARIA low-confidence fallback — AC 7). Status left `in-progress`, not `review`, because AC 7 is a genuine unimplemented AC, not a documentation gap.
- New `apps/workers/discovery/src/discovery_worker/widgets.py`: `list_tabs`, `detect_open_dialog`, `close_dialog_ladder` (Escape → Close/Cancel/X/Dismiss by accessible name → aria-label → forced navigation, verifying "gone" after every rung).
- `crawler.py` additions: `_iter_same_origin_frames`/`_capture_frame_widgets` (iframe traversal, depth-bounded, reuses `_fill_and_submit_form`/`_click_standalone_buttons` against `Frame` objects rather than a parallel mechanism, per Dev Notes); an `attachShadow`-tracking init script + `_collect_shadow_dom_widgets`/`_click_shadow_dom_buttons` (shadow DOM — the tracking script is the only way to detect a *closed* root's existence at all, since `element.shadowRoot` reads back identically for "none" and "closed"); `_explore_tabs`; `_handle_dialog_if_opened`; `_handle_popups`; file-upload placeholder generation (`_placeholder_file_path`, one PNG + one PDF, lazily created once per process).
- Threaded a new `on_diagnostic(kind, payload)` callback through `run_discovery_crawl` → `activities.py`'s `_record_diagnostic`, which calls Story 2.22 Task 1's `record_diagnostic()` sink — every call site is awaited via a new `_emit_diagnostic` helper (hops onto a thread) rather than called directly, because it shares the same DB `Session` as `_persist` and must stay serialized with it, not run concurrently.
- **Two real bugs found and fixed during verification** (not just written-then-trusted):
  1. `page.on("popup", popup_events.append)` raised `AttributeError` at runtime — Playwright's handler-wrapping caches an attribute on the callable, which a bound built-in method (`list.append`) can't hold. Fixed with a plain lambda wrapper.
  2. A cross-origin popup's own Playwright event consistently arrives ~400-500ms after the triggering click's promise resolves (measured directly, not assumed — Chromium spins up a genuinely new renderer process for site-isolated content; a same-origin popup's event is near-instant). The original code additionally gated the drain call itself behind `if popup_events:`, which meant the intended grace-wait inside `_handle_popups` could never run in the one case it exists for (list still empty right after the click). Fixed by calling `_handle_popups` unconditionally (it internally no-ops on `None`) and widening the grace wait to 0.75s, paid only when nothing is queued yet.
- Also fixed a test-fixture bug found the same way: the "closable" dialog's own `Close` button had no `onclick` handler at all, so the close-button rung of the ladder legitimately never worked, and the test only passed by falling through to forced-navigation — added the handler so `close_button` is exercised as intended.
- New fixture routes in `target_app.py` (`/frames`, `/frame-content`, `/shadow-dom`, `/tabs`, `/dialog`, `/popups`, `/upload`) — deliberately dead-ended (no "Home" link) so a test's crawl stays scoped to one route instead of re-running the whole dashboard crawl. The cross-origin cases (frame + popup) use the same server under the `localhost` hostname instead of `127.0.0.1` — a different origin per RFC 6454 (host differs) even though it's the same process, keeping the tests fast and deterministic without a second server.
- Verified: new `test_widget_coverage.py` (9 tests, all against real Chromium) all pass; full `apps/workers/discovery` suite re-run with no regressions; ruff and pyright clean on every new/modified file.
- **What's left, honestly**: AC 7 (non-ARIA low-confidence fallback) is unimplemented — it needs a `confidence` field on `Action`/`Component` (schema change) and materially widens what the crawler clicks (arbitrary `div`/`span[onclick]`, not just `button`/dead-href `a`), which is a real scope/risk decision, not a small addition; deliberately not rushed into this session. Three items are soft-deferred on stories that don't exist yet (2.10, 2.11, 2.13, 2.15, 2.21), each marked in-code and in this file with which story it's waiting on, matching the pattern Story 2.9's own AC 7 already established.

### File List

- `apps/workers/discovery/src/discovery_worker/widgets.py` (new)
- `apps/workers/discovery/src/discovery_worker/crawler.py` (modified — see Completion Notes)
- `apps/workers/discovery/src/discovery_worker/activities.py` (modified — `_record_diagnostic` closure, threaded into `run_discovery_crawl`)
- `apps/workers/discovery/tests/test_widget_coverage.py` (new — 9 tests)
- `apps/workers/discovery/tests/fixtures/target_app.py` (modified — 7 new routes)

## Change Log

- 2026-07-29 — Story created per `sprint-change-proposal-2026-07-29.md`.
- 2026-08-03 — Rewritten and expanded against `docs/DISCOVERY_ENGINE_V2.md` following a feasibility review. Added iframe traversal (AC 1) and shadow-DOM piercing (AC 2) — both entirely absent from the original batch and from the current crawler despite being pervasive in enterprise targets — added the `unreachable_container` concept feeding Story 2.22, strengthened the dialog close ladder with a mandatory forced-navigation fallback, added portal-rendered-overlay detection guidance, and re-sequenced this story to be built first in the remaining Epic 2 backlog.
- 2026-08-03 — Tasks 1, 2, 4, 5, 6, 7 implemented and verified against real Chromium; Task 3 partially (AC 7's non-ARIA fallback not implemented — tracked gap). Found and fixed two real runtime bugs (a Playwright handler-wrapping crash on popup listener registration, a cross-origin-popup timing race) and one fixture bug (a dialog's Close button with no handler) during verification. Status moved `ready-for-dev` → `in-progress`, deliberately not `review` given the tracked AC 7 gap.
