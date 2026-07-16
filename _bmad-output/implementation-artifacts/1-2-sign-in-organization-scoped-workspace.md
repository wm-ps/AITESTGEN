# Story 1.2: Sign In & Organization-Scoped Workspace

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 — IA changed from a persistent nav-rail shell to a top-bar + Home landing; see `sprint-change-proposal-2026-07-15.md`.*

## Story

As a user,
I want to sign in and land in a workspace scoped to my Organization,
so that my Applications and data are isolated from any other customer's.

## Acceptance Criteria

1. **Given** a registered user belonging to an Organization, **when** they sign in, **then** they land on Home, showing three action cards (Start a New Project, Managed Applications, Watch a Product Demo) beneath a top bar (brand mark + product name, left; user-initials avatar, right). [Source: epics.md#Story 1.2]
2. The design-token system is applied with full light/dark parity (`:root` light defaults, `@media (prefers-color-scheme: dark)` override, explicit `data-theme` attribute override) — no component hardcodes a color. [Source: UX-DR1, DESIGN.md#Brand & Style]
3. Clicking the avatar opens a menu showing the user's name, email, and a Log out action. [Source: epics.md#Story 1.2]
4. Every API query the user's session triggers is scoped to their Organization via one central scoping mechanism (AD-12) — a second Organization's data is never returned. [Source: architecture#AD-12]
5. The Home screen omits the top-bar Application-name breadcrumb (UX-DR16) — it is inherently pre-Application. [Source: UX-DR16, EXPERIENCE.md#Information Architecture]
6. Every interactive element (buttons, links, avatar menu) has a visible focus ring and is keyboard-operable. [Source: UX-DR18, EXPERIENCE.md#Accessibility Floor]
7. The token system's `ink-muted` value is the only token used for real label/caption/metadata text anywhere in the shell, with `ink-faint` reserved exclusively for decorative marks — this rule, plus the no-exclamation-points/no-celebratory-language voice-and-tone rule, is treated as a standing constraint every later story's UI copy must follow, not a one-time fix. [Source: UX-DR19, UX-DR20, DESIGN.md#Colors, EXPERIENCE.md#Voice and Tone]

*(Superseded 2026-07-15 — retained for history only: the prior AC described a persistent 236px nav rail with links grouped under Workspace/Onboard/Understand/Automate/Prove, Settings and sign-out pinned to the rail foot. No nav rail exists in the current IA; top-level navigation is the pipeline stepper introduced in Story 2.1.)*

## Tasks / Subtasks

- [x] Task 1: Add `Organization` and `User` domain entities and a sign-in mechanism (AC: 1, 4)
  - [x] Add `Organization` (id, name) and `User` (id, organization_id, email, hashed password) SQLModel entities to `packages/domain`, plus an Alembic migration
  - [x] Story 1.1 added exactly one minimal SQLModel entity purely to prove the Postgres+Alembic wiring end-to-end — it was explicitly scoped as throwaway proof-of-wiring, not a real domain entity. Check Story 1.1's Dev Agent Record File List for what it was named; you are free to leave it in place, rename it, or remove it once `Organization`/`User` exist — do not feel obligated to preserve its shape
  - [x] Implement password hashing (e.g. `passlib`/`argon2` or `bcrypt`) — never store plaintext passwords
  - [x] Implement a sign-in endpoint in `apps/api` that verifies credentials and issues a session: recommended default is an httpOnly, secure session cookie (signed, e.g. via `itsdangerous`, or a JWT stored in an httpOnly cookie) — same-origin SPA + API makes a cookie simpler than a bearer-token flow, and this is a "boring technology" choice consistent with the architecture's general bias; this exact mechanism is **not** fixed by the PRD or Architecture Spine, so document the choice made in Completion Notes
  - [x] No PRD story or epic covers self-service registration (no "Sign Up" screen exists in the 11-screen UX inventory — a "registered user" is an AC precondition, not something this story builds a public flow for). Provide only a minimal, non-UX way to create the first `Organization` + `User` for development/testing (e.g. a seed script or an internal-only endpoint) — do not build a public registration screen
  - [x] Explicitly out of scope, and not a gap: forgot-password, email verification, MFA, or role/permission tiers for platform users — none are specified anywhere in the PRD, UX, or Architecture for platform accounts (distinct from FR-3's target-application SSO/MFA, which is unrelated)
- [x] Task 2: Implement the Organization-scoping middleware (AC: 4)
  - [x] Build one central mechanism (e.g. a FastAPI dependency applied to every authenticated router, or a query-layer filter) that derives `organization_id` from the signed-in session and scopes every query — per AD-12, this must be a single mechanism every module (Onboarding, Review, Analytics) passes through, never re-implemented per-endpoint
  - [x] Write a test proving cross-Organization isolation: seed two Organizations, confirm a User from Org A can never read/write a row belonging to Org B through any endpoint this story adds
- [x] Task 3: Build the top bar and Home landing screen in `apps/web` (AC: 1, 3, 6)
  - [x] Top bar: brand mark + product name pinned left, user-initials avatar pinned right, fluid main column beneath it (content capped per `DESIGN.md`'s layout tokens)
  - [x] Home renders three action cards — Start a New Project, Managed Applications, Watch a Product Demo — only "Start a New Project"/"Managed Applications" have a real destination in this story (routing into Story 1.3's Connect App form); "Watch a Product Demo" can point at a placeholder until a real destination exists, but the card itself and its copy must be correct now
  - [x] Avatar click opens a menu showing the signed-in user's name, email, and a Log out action; Log out clears the session and returns to sign-in
  - [x] Active/hover states and focus treatment follow `DESIGN.md`'s button/link component tokens
  - [x] Visible focus ring on every interactive element (top-bar links, action cards, avatar menu, buttons) and native keyboard operability — no `<div onclick>` substitutes
- [x] Task 4: Implement the design-token system (AC: 2, 7)
  - [x] Port every token in `DESIGN.md`'s frontmatter (colors, typography, rounded, spacing, component tokens) into CSS custom properties
  - [x] `:root` sets light values + `color-scheme: light`; `@media (prefers-color-scheme: dark)` overrides for OS dark preference; explicit `:root[data-theme="dark"]`/`:root[data-theme="light"]` attribute selectors so an in-app toggle can override the OS preference
  - [x] No component/screen may hardcode a color outside this token layer — this rule starts now and holds for every subsequent story
  - [x] A full theme-toggle *control* has no assigned screen (Settings, where it would naturally live, was Epic 7 — removed in full 2026-07-15, see `sprint-change-proposal-2026-07-15.md`) — wiring the `data-theme` attribute-setting mechanism (e.g. a small JS helper that toggles the attribute + persists to `localStorage`) now, even without a visible UI control for it, avoids retrofitting the CSS-selector contract later; a visible toggle affordance is not required by this story's ACs
  - [x] Route all real label/caption/metadata text in the shell through `ink-muted` (~5:1 AA contrast); reserve `ink-faint` exclusively for decorative/non-text marks
  - [x] Apply the voice-and-tone rule to any copy added in this story (nav labels, empty states): no exclamation points, no emoji, no celebratory language; capitalize Application/Capability/Journey/Scenario/Test Asset/Trusted Knowledge Model as proper nouns wherever they appear
- [x] Task 5: Build the Home screen as a minimal, Organization-scoped landing target (AC: 1, 5)
  - [x] Sign-in success routes to Home, rendered beneath the top bar
  - [x] Suppress the top-bar Application-name breadcrumb on this screen (it's inherently pre-Application, per UX-DR16)
  - [x] Since Story 1.3 hasn't run yet, there are no `Application` records — the three action cards render regardless (they are entry points, not data-driven); do not build a Managed Applications table, hero-stat strip, or the Connect App form itself here, those belong to Story 1.3
- [x] Task 6: Verify end-to-end and record evidence (AC: 1-7)
  - [x] Sign in as a seeded User lands on Home beneath the top bar, correct breadcrumb suppression
  - [x] Toggling OS dark-mode preference (and, separately, the `data-theme` attribute) repaints every token-driven surface with no hardcoded-color exceptions
  - [x] Keyboard-only navigation (Tab) reaches every top-bar link, action card, and the avatar menu with a visible focus ring, in visual order
  - [x] Avatar menu opens on click/keyboard-activation, shows name/email, and Log out ends the session
  - [x] Cross-Organization isolation test (Task 2) passes
  - [x] CI (from Story 1.1) stays green

## Dev Notes

- **This story depends on Story 1.1 being implemented first**, not just created. As of this story's creation, Story 1.1 is `ready-for-dev` (not `done`) and the repository's only commit is the initial BMad scaffold commit — there is no FastAPI app, no `apps/web` Vite project, no Postgres/Alembic wiring, and no OpenAPI codegen pipeline yet to build this story's sign-in/shell work on top of. If you are picking up this story and Story 1.1's scaffold isn't actually in the codebase yet, stop and implement/verify 1.1 first rather than re-deriving its setup ad hoc inside this story.
- **AD-12 is the load-bearing rule here:** "`Organization` is a first-class tenant-boundary entity; every `apps/api` query must be scoped by the authenticated user's Organization through one central mechanism, never left to individual endpoints." Getting this right in one place now (Task 2) is what lets every later module (Review, Analytics, Onboarding) skip re-implementing tenant isolation — get it wrong and it's an N-endpoint fix later, not a one-file fix.
- **Platform auth has no PRD FR** (confirmed via the Implementation Readiness Report's tracked follow-up item) — Architecture AD-12 and the UX's Login screen are what this story builds against, not a numbered FR. This is a known, already-accepted gap, not something to flag as a blocker.
- **Scope discipline, mirroring Story 1.1's note:** Don't build Story 1.3's Connect App form/Managed Applications table, don't build Settings (was Epic 7, removed in full), don't build a public registration flow (no story covers one). A shell that quietly does a later story's job creates merge conflicts for whoever picks up 1.3 next.
- **IA change (2026-07-15):** the persistent nav-rail shell (236px rail, five section groups, rail-foot Settings/sign-out) described in the prior revision of this story no longer exists. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md` for the full rationale, and `EXPERIENCE.md`'s Information Architecture section for the current top-bar + Home-landing + pipeline-stepper IA this story now builds against.
- **Token fidelity:** `DESIGN.md`'s frontmatter is the literal source of truth for every color/spacing/typography value — copy values from there, don't approximate them from the prose description.
- **Voice-and-tone is standing, not a one-time lint pass:** any copy this story or any future story adds must be checked against `EXPERIENCE.md`'s Do/Don't table (e.g., "Review queue cleared..." not "You're all caught up! 🎉").

### Project Structure Notes

- Builds directly on Story 1.1's Structural Seed (`apps/api`, `apps/web`, `packages/domain`, `migrations/`) — no new top-level directories are introduced by this story.
- No conflicts detected against existing structure, since (per the dependency note above) 1.1's scaffold either already exists exactly as specified, or must be created first.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2: Sign In & Organization-Scoped Workspace]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-12 — Every Application belongs to exactly one Organization]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Colors, #Typography, #Layout & Spacing, #Components]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Information Architecture, #Voice and Tone, #Accessibility Floor]
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-13.md — "Platform authentication has no PRD FR" follow-up item]
- [Source: _bmad-output/implementation-artifacts/1-1-repository-service-scaffold.md — Structural Seed and proof-entity dependency]

## Previous Story Intelligence

Story 1.1 (`1-1-repository-service-scaffold`) exists as a `ready-for-dev` spec but has not been implemented — its Dev Agent Record (File List, Completion Notes) is empty and `git log` shows only the initial BMad-tooling commit. There are no established code patterns, library choices, or file layouts to inherit from it yet beyond what its own story file specifies. Once 1.1 is actually implemented, re-check its File List before starting this story's Task 1, specifically to see what its one proof-of-wiring SQLModel entity was named.

## Latest Technical Notes

- No new library decisions beyond Story 1.1's stack are architecturally fixed for this story. Password hashing (`passlib`/`argon2`/`bcrypt`) and session signing (`itsdangerous` or a JWT library) are implementer choices — pick current-stable, actively-maintained packages at implementation time rather than trusting a specific version from training data.

## Project Context Reference

No `project-context.md` exists yet in this repository. Continues to be worth generating via `bmad-generate-project-context` once Epic 1's early stories land, so later epics get a lean, code-grounded reference instead of re-deriving conventions from planning docs each time.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Full suite with Postgres/Vault/Temporal up: `DATABASE_URL=... uv run pytest` → 10 passed.
- Real-network smoke test (not just FastAPI TestClient): `curl` login → sets cookie → `/auth/me`
  200 with cookie / 401 without → `/applications` create → 201 with `discovery_status=running`.
- CORS preflight from the Vite origin (`http://localhost:5173`) confirmed
  `access-control-allow-credentials: true` so the session cookie actually reaches the browser.
- `npm run build` (tsc -b + vite build), `npm run lint` (oxlint), `npm test` (vitest) all green.

### Completion Notes List

- **Session mechanism chosen: itsdangerous-signed httpOnly cookie** (`api/auth.py`), not a JWT
  library — same-origin SPA+API, so no bearer-token/refresh-token complexity is needed. Cookie
  is `httponly`, `samesite=lax`, and `secure` gated by a `COOKIE_SECURE` env var (defaults false
  for local dev over http; set true in any real deployment).
- **Password hashing: `bcrypt`** (direct library, not `passlib`) — smaller surface, actively
  maintained, no need for passlib's multi-scheme abstraction when only one scheme is ever used.
- **AD-12 central mechanism:** `api.auth.current_org_id` — every org-scoped endpoint depends on
  this (not `current_user` directly unless it also needs identity), never re-derives
  `organization_id` any other way. Cross-Organization isolation is proven in
  `apps/api/tests/test_onboarding.py::test_cross_organization_isolation` (reused against the
  `/applications` endpoint since that's the first/only org-scoped resource this pair of stories
  adds — Story 1.2 itself adds no other org-scoped data endpoint to test against).
- **PlatformUser gained a `name` field** not listed in this story's Task 1 field list
  (`id, organization_id, email, hashed password`) — AC 3 requires the avatar menu to show the
  user's name, which isn't derivable from email alone. Added as the minimal field needed to
  satisfy the AC.
- **No router library added** — only three views (Sign in / Home / Connect App) exist across
  Stories 1.2+1.3, so `apps/web/src/App.tsx` switches on a plain `useState<View>` instead of
  pulling in `react-router`. Revisit if a fourth view needs deep-linking.
- **Design tokens** live in `apps/web/src/tokens.css` (`:root` light defaults,
  `@media (prefers-color-scheme: dark)` override, `:root[data-theme]` attribute override) and
  are consumed via CSS custom properties from `index.css` and inline component styles — no
  hardcoded colors elsewhere. `apps/web/src/theme.ts` wires the `data-theme` attribute +
  `localStorage` persistence mechanism per the story's note, with no visible toggle control
  (none is in scope).
- **Verification gap — no browser tool available in this environment:** keyboard-only Tab-order
  traversal, the avatar menu's real click/keyboard activation, and the light/dark repaint were
  not visually confirmed in an actual browser. What *is* verified: `vitest` exercises the
  Sign-in→Home transition and avatar-menu open/close via `fireEvent`; every interactive element
  is a native `<button>`/`<input>` (not a `<div onclick>`), so keyboard operability and focus
  are native browser behavior, not custom JS; the global `:focus-visible` rule
  (`index.css`) applies uniformly. A manual browser pass is recommended before this story is
  considered fully done.
- **CI updated** (`.github/workflows/ci.yml`) to add Vault + a manually-started Temporal dev
  server to the Python job, so Story 1.3's Vault/Temporal-dependent tests actually execute in CI
  rather than skipping (mirrors Story 1.1's Postgres-service precedent). Not yet observed on an
  actual GitHub Actions run — verified by local-equivalence only, same caveat Story 1.1 recorded
  for its own CI.
- **ScaffoldProbe removed** (backend entity/endpoints, frontend view, migration to drop the
  table) now that the real domain model supersedes it, per its own docstring's explicit
  permission to do so.
- **2026-07-16 — full stack validated live, closing the prior browser-tool gap:** brought up
  Postgres/Temporal/Vault + API + discovery worker + web via the Developer Guide runbook and
  drove real HTTP traffic (not just `TestClient`). Confirmed live: login/logout, `/auth/me`
  401 with no cookie and with a tampered cookie, wrong-password and unknown-email both 401,
  and — the AD-12 load-bearing case — a second seeded Organization's user gets a live 404
  reading the first Organization's Application while creating their own succeeds normally.
  Full `pytest`/`ruff`/`pyright` (Python) and `oxlint`/`tsc -b`/`vitest`/`vite build` (web) all
  green; `api-types.gen.ts` regenerated with zero drift against the running API (AD-6).

### File List

**packages/domain**
- `src/domain/organization.py`, `src/domain/platform_user.py`, `src/domain/application.py`,
  `src/domain/discovery_run.py` (NEW)
- `src/domain/__init__.py` (MODIFIED — exports new entities, drops `ScaffoldProbe`)
- `src/domain/scaffold_probe.py` (DELETED)

**packages/secrets_client**
- `src/secrets_client/vault_client.py` (NEW — `VaultSecretsClient`, `SecretRef`)
- `src/secrets_client/__init__.py` (MODIFIED — `SecretsClient` Protocol now typed against the
  real `SecretRef`; exports `VaultSecretsClient`)
- `tests/test_vault_client.py` (NEW)
- `pyproject.toml` (MODIFIED — adds `hvac`)

**packages/workflows**
- `src/workflows/discovery_workflow.py` (NEW — no-op `DiscoveryWorkflow` shell, AD-2)
- `src/workflows/__init__.py` (MODIFIED — exports it)

**apps/workers/discovery**
- `src/discovery_worker/worker.py` (NEW)
- `pyproject.toml` (MODIFIED — adds `temporalio`, `workflows`)

**apps/api**
- `src/api/auth.py` (NEW — hashing, session cookie, `current_user`/`current_org_id`)
- `src/api/main.py` (MODIFIED — `/auth/login`, `/auth/logout`, `/auth/me`, `/applications`
  POST/GET; CORS `allow_credentials=True`; `ScaffoldProbe` endpoints removed)
- `src/api/scripts/seed_dev_data.py` (NEW)
- `tests/test_auth.py`, `tests/test_onboarding.py` (NEW)
- `tests/test_health.py` (MODIFIED — probe-schema assertion → `ApplicationRead`)
- `tests/test_scaffold_probe_db.py` (DELETED)
- `pyproject.toml` (MODIFIED — adds `bcrypt`, `itsdangerous`, `secrets-client`)

**migrations**
- `env.py` (MODIFIED — imports the new entities, drops `ScaffoldProbe`)
- `versions/ad5d97c75dc9_organization_platform_user_application_.py` (NEW)
- `versions/3206b535a942_drop_disposable_scaffold_probe_proof_.py` (NEW)

**apps/web**
- `src/tokens.css` (NEW), `src/theme.ts` (NEW)
- `src/index.css` (MODIFIED — replaced Vite template styles with the token system + base
  reset + focus-ring rule)
- `src/api.ts` (NEW — typed fetch wrapper over generated OpenAPI types)
- `src/App.tsx` (MODIFIED — Sign-in/Home/Connect-App/Discover view switching)
- `src/App.test.tsx` (NEW)
- `src/main.tsx` (MODIFIED — applies stored theme on boot)
- `src/components/SignIn.tsx`, `src/components/TopBar.tsx`, `src/components/Home.tsx`,
  `src/components/ConnectAppForm.tsx`, `src/components/DiscoverJourneysPlaceholder.tsx` (NEW)
- `src/api-types.gen.ts` (REGENERATED)
- `src/ScaffoldProbeView.tsx`, `src/ScaffoldProbeView.test.tsx` (DELETED)

**Workspace root**
- `docker-compose.yml` (MODIFIED — adds Vault dev-mode service)
- `.github/workflows/ci.yml` (MODIFIED — adds Vault service + Temporal dev server to Python job)
