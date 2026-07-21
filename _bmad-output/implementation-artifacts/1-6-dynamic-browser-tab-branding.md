---
baseline_commit: 2b72ef3deaba32290fd3d65de027081a5c76f13b
---

# Story 1.6: Dynamic Browser Tab Branding

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Added 2026-07-21 per `sprint-change-proposal-2026-07-21.md` (CR-1, display half — the capture half, `Application.favicon_url`, is Story 1.3's job). Next available Epic 1 story number; 1.5 is not reused since it was already removed in the 2026-07-15 change and reusing it would collide with that history.*

## Story

As a user working in the pipeline for a specific Application,
I want the browser tab to show that Application's name and icon,
so that I can tell which Application I'm working on at a glance across browser tabs.

## Acceptance Criteria

1. **Given** a user is on any of the four pipeline-step screens (Connect App, Discover Journeys, Review Scenarios, Generate Suite) for a given Application, **when** the screen renders, **then** the browser tab title shows the Application's name (e.g. "Claims Processing — AITestGen"). [Source: epics.md#Story 1.6; sprint-change-proposal-2026-07-21.md CR-1]
2. The browser tab favicon shows `ApplicationRead.favicon_url` if set, otherwise the platform's default icon (`apps/web/public/favicon.svg`, unchanged from today). [Source: epics.md#Story 1.6]
3. Navigating to Home or Sign In reverts the tab to the platform's default title ("AITestGen") and default icon — both screens are pre-/cross-Application, per the existing breadcrumb-suppression rule this story's tab-branding rule mirrors (UX-DR16, `EXPERIENCE.md#Information Architecture`). [Source: epics.md#Story 1.6; EXPERIENCE.md]

**`[SCOPE NOTE]`** Only two of the four pipeline screens exist in `apps/web` today — `connect-app` and `discover` (see Dev Notes). Review Scenarios and Generate Suite (Epic 4) are not yet built. Implement the branding mechanism generically, keyed off the same `view`/`application` state `App.tsx` already tracks, so it automatically covers the other two screens once Epic 4's views land — do not hardcode per-screen logic that would need revisiting then. Verification (AC 1–3) can only be exercised against `connect-app` and `discover` today.

**`[DEPENDENCY — BLOCKING]`** This story reads `ApplicationRead.favicon_url`, which does not exist yet. Story 1.3 (currently `in-progress`, reverted for rework per `sprint-change-proposal-2026-07-21.md`) adds this field on the backend and regenerates `apps/web/src/api-types.gen.ts` (AD-6). **Confirm Story 1.3's rework is done and `api-types.gen.ts` has been regenerated before starting this story** — otherwise `ApplicationRead` won't have `favicon_url` and Task 1 below has nothing to read.

## Tasks / Subtasks

- [x] Task 1: Verify the dependency and inspect the regenerated type (AC: 2)
  - [x] Confirmed `apps/web/src/api-types.gen.ts`'s `ApplicationRead` schema has `favicon_url: string | null` from Story 1.3's rework.
- [x] Task 2: Build a small, colocated tab-branding hook (AC: 1, 2, 3)
  - [x] Created `apps/web/src/hooks/useTabBranding.ts` — takes `(view: string, application: ApplicationRead | null)` and, via `useEffect`, sets `document.title` and the favicon `<link>`'s `href`.
  - [x] Self-contained `useEffect`, no routing/head-management library added.
  - [x] Reverts to `/favicon.svg`/`"AITestGen"` whenever `view === 'home'` (covers signed-out/Home/Sign In, since `App.tsx` renders `<SignIn>` before `view` ever changes off its `'home'` default).
- [x] Task 3: Wire the hook into `App.tsx` (AC: 1, 2, 3)
  - [x] `useTabBranding(view, application)` called unconditionally at the top of `App`, alongside the existing `applicationBadge` derivation.
- [x] Task 4: Verify end-to-end and record evidence (AC: 1-3)
  - [x] Extended `apps/web/src/App.test.tsx`'s three existing tests with `document.title`/favicon-href assertions at Sign In, Home, Connect App (still default — no Application yet), and Discover Journeys (Application's name + `favicon_url`).
  - [x] Added `apps/web/src/hooks/useTabBranding.test.ts` covering: default on `home`, name+favicon on a pipeline step, fallback to `/favicon.svg` when `favicon_url` is null, and reverting when `view` goes back to `home`.

### Task Completion Notes (2026-07-21)

- jsdom starts every test with an empty `<head>` — vitest doesn't load `index.html` the way a real browser does. Added `apps/web/src/test-setup.ts` (wired via `vitest.config.ts`'s new `setupFiles`) to seed `document.title`/the favicon `<link>` before each test, so tests exercise the real starting DOM state instead of a null querySelector.
- `apps/web/index.html`'s static `<title>` changed from the generic `web` placeholder to `AITestGen` — the hook overrides it at runtime regardless, but the pre-hydration default should match too.

## Dev Notes

- **`App.tsx` has no router.** [apps/web/src/App.tsx] is a hand-rolled state machine: `view: 'home' | 'connect-app' | 'discover'` plus `application: ApplicationRead | null`, both `useState`. `TopBar` already receives a derived `applicationBadge` computed inline as `view === 'home' ? undefined : application ? {...} : undefined` — this story's hook should key off the same two values the same way, not introduce React Router or a Context provider for what is a two-variable read.
- **Only 2 of 4 pipeline views exist yet.** `View` is currently `'home' | 'connect-app' | 'discover'` — no `'review-scenarios'` or `'generate-suite'` member exists because Epic 4's stories (4.1–4.3) are still `ready-for-dev`, not built. Don't add placeholder view values speculatively; write the hook against the `view`/`application` shape generically enough that adding those two views later is a non-event for this hook.
- **`apps/web/index.html`** currently has a static `<title>web</title>` (lowercase "web" — this is the generic placeholder CR-1 is replacing) and a static `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />`. The favicon `<link>` element itself is not new — this story manipulates its existing `href` attribute at runtime, it does not add a new `<link>` tag.
- **`ApplicationRead.favicon_url` does not exist in `apps/web/src/api-types.gen.ts` as of this story's creation** — confirmed by direct inspection. It is added by Story 1.3's in-flight rework (backend column + OpenAPI regen, AD-6). This is a hard sequencing dependency, not a nice-to-have — see the blocking note above Tasks.
- **No prior art for this pattern in the codebase.** Searched for `document.title`, `useDocumentTitle`, and `createContext`/`ApplicationContext` — none exist. This is genuinely new plumbing, not a refactor of something existing.
- **Testing conventions**: every component in `apps/web/src/components/` has a paired `ComponentName.test.tsx` using `@testing-library/react` + `vitest`, mocking `global.fetch` via `vi.stubGlobal` (see `App.test.tsx`'s `mockFetchOnce` helper and the multi-mock `fetchMock` pattern in its third test, which drives Home → Connect App → Discover Journeys in one flow — the same flow this story's App-level tests should extend). Follow this pattern; do not introduce a different test-double approach (e.g. MSW) for this story alone.
- **Do not touch backend code, migrations, or `packages/domain`** in this story — `favicon_url` capture, its migration, and the OpenAPI regen are entirely Story 1.3's scope. This story is frontend-only (`apps/web`).

### Project Structure Notes

- New file: `apps/web/src/hooks/` (new directory — no `hooks/` folder exists yet in `apps/web/src`; this is the first custom hook extracted in this codebase, colocated the same way components are colocated with their tests).
- Extends `apps/web/src/App.tsx` only — no new top-level directories, no backend changes.
- No conflicts detected with existing structure; `apps/web/src/components/TopBar.tsx`'s existing `applicationBadge` logic is a useful reference pattern (same derivation source) but is not itself modified by this story.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.6: Dynamic Browser Tab Branding]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-21.md — CR-1]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-32]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Information Architecture — browser tab branding rule, mirrors UX-DR16 breadcrumb suppression]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md — AD-6, Application.favicon_url domain addition]
- [Source: apps/web/src/App.tsx — current view/application state machine]
- [Source: apps/web/src/components/TopBar.tsx — existing applicationBadge derivation pattern]
- [Source: apps/web/index.html — current static title/favicon being replaced]
- [Source: apps/web/src/App.test.tsx — existing test pattern this story's tests extend]
- [Source: _bmad-output/implementation-artifacts/1-3-onboard-an-application-basic-details.md — blocking dependency for `ApplicationRead.favicon_url`]

## Previous Story Intelligence

Story 1.4 (`done`) is the most recent completed story in Epic 1 and establishes conventions this story should follow: regenerate `api-types.gen.ts` from a live API run and diff against the checked-in file to confirm no drift (AD-6) whenever a backend schema change is involved — though for this story specifically, the regeneration itself is Story 1.3's responsibility; this story only *consumes* the regenerated type. Story 1.4 also confirms this codebase's testing stack (`vitest`, `@testing-library/react`, `ruff`, `pyright`, `tsc -b`, `oxlint`) and that no browser-based visual verification tool is available in this environment — DOM-assertion tests are the verification bar, not a manual browser pass (though one is still recommended before calling the story done, per 1.4's own note).

Story 1.3 itself (`in-progress`, reverted for this CR) is a **blocking dependency**, not just a precedent — see the note above Tasks. Read its file for the exact shape `favicon_url` lands in before starting Task 1.

## Latest Technical Notes

No new library needed. Setting `document.title` and a `<link rel="icon">`'s `href` imperatively is standard DOM API, available in all supported browsers without a dependency — resist adding `react-helmet-async` or similar for what a four-line `useEffect` covers in an app with no routing.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
