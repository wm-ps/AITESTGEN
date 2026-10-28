---
last_updated: 2026-10-27
---

# Story 2.14: Widget & Container Coverage — Frames, Embedded Components, Tabs, Dialogs, Windows, Uploads

Status: in-progress

> This story describes the **classic discovery engine**. New applications are discovered by **Explorer** (Epic 8); the classic engine now runs only for applications it discovered before Explorer became the default, or when operations switch new applications back to it.

## Story

As a user,
I want Vantage to see inside the containers real business applications use (embedded frames, embedded components, tabs, pop-up dialogs, new windows) and to handle file uploads,
so that Discovery doesn't record an empty page and call it a success.

## What it does today

- **Embedded frames.** Vantage looks inside frames from the same site, up to three levels deep, and treats their content as part of the page. Frames from another site can't be read by design. They are logged as unreachable and counted in the coverage report, never treated as a failure.
- **Embedded components (shadow DOM).** Vantage looks inside open embedded components, both when recording the page and when comparing screens (Story 2.10). Closed components can't be opened. They are logged as unreachable, and the page is still recorded.
- **Tabs.** Each tab in a properly labelled tab group is an in-page action. Its content is checked as its own screen or as a variant of the current one.
- **Dialogs.** When an action opens a properly labelled pop-up dialog, its content is recorded as a screen of its own even though the address didn't change. Vantage then closes it reliably before carrying on. It tries, in order:
  1. Press Escape.
  2. Click a Close / Cancel / X button.
  3. Click any button marked as a close button.
  4. Go back to the address from before the dialog.
- **New tabs and windows.** A new tab on the same site is recorded as a page linked from the action that opened it (its address and title only; it is not explored further). A tab on another site is noted, not followed, and Vantage returns to the original tab.
- **File uploads.** Upload fields get a harmless placeholder image or PDF, created once and reused (Story 2.13).

## Acceptance criteria

1. **Given** a page with frames from the same site, **then** their content is captured up to three levels deep; frames from other sites are logged as unreachable and counted, not treated as failures.
2. **Given** open embedded components, **then** their content is captured and used when comparing screens; closed ones are logged as unreachable.
3. **Given** a labelled tab group, **then** each tab is tried and its content is classified as a screen or a variant.
4. **Given** an action opens a labelled dialog, **then** its content is recorded as its own screen and the dialog is closed (Escape, Close/Cancel/X, close button, go back) before exploring continues.
5. **Given** a new tab opens, **then** a same-site tab is recorded as a linked page and an other-site tab is noted and left alone.
6. **Given** a file upload field, **then** the run's shared placeholder file is used.

## Gaps / not built

- Tabs, dialogs and buttons that aren't labelled with standard accessibility roles aren't recognised. The planned fallback (guessing from page structure and marking the result "low confidence" for review) has not been built. Apps built with custom, unlabelled widgets will be under-explored.
