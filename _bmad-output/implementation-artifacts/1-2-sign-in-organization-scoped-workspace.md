# Story 1.2: Sign In & Organization-Scoped Workspace

Status: ready-for-dev

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

- [ ] Task 1: Add `Organization` and `User` domain entities and a sign-in mechanism (AC: 1, 4)
  - [ ] Add `Organization` (id, name) and `User` (id, organization_id, email, hashed password) SQLModel entities to `packages/domain`, plus an Alembic migration
  - [ ] Story 1.1 added exactly one minimal SQLModel entity purely to prove the Postgres+Alembic wiring end-to-end — it was explicitly scoped as throwaway proof-of-wiring, not a real domain entity. Check Story 1.1's Dev Agent Record File List for what it was named; you are free to leave it in place, rename it, or remove it once `Organization`/`User` exist — do not feel obligated to preserve its shape
  - [ ] Implement password hashing (e.g. `passlib`/`argon2` or `bcrypt`) — never store plaintext passwords
  - [ ] Implement a sign-in endpoint in `apps/api` that verifies credentials and issues a session: recommended default is an httpOnly, secure session cookie (signed, e.g. via `itsdangerous`, or a JWT stored in an httpOnly cookie) — same-origin SPA + API makes a cookie simpler than a bearer-token flow, and this is a "boring technology" choice consistent with the architecture's general bias; this exact mechanism is **not** fixed by the PRD or Architecture Spine, so document the choice made in Completion Notes
  - [ ] No PRD story or epic covers self-service registration (no "Sign Up" screen exists in the 11-screen UX inventory — a "registered user" is an AC precondition, not something this story builds a public flow for). Provide only a minimal, non-UX way to create the first `Organization` + `User` for development/testing (e.g. a seed script or an internal-only endpoint) — do not build a public registration screen
  - [ ] Explicitly out of scope, and not a gap: forgot-password, email verification, MFA, or role/permission tiers for platform users — none are specified anywhere in the PRD, UX, or Architecture for platform accounts (distinct from FR-3's target-application SSO/MFA, which is unrelated)
- [ ] Task 2: Implement the Organization-scoping middleware (AC: 4)
  - [ ] Build one central mechanism (e.g. a FastAPI dependency applied to every authenticated router, or a query-layer filter) that derives `organization_id` from the signed-in session and scopes every query — per AD-12, this must be a single mechanism every module (Onboarding, Review, Analytics) passes through, never re-implemented per-endpoint
  - [ ] Write a test proving cross-Organization isolation: seed two Organizations, confirm a User from Org A can never read/write a row belonging to Org B through any endpoint this story adds
- [ ] Task 3: Build the top bar and Home landing screen in `apps/web` (AC: 1, 3, 6)
  - [ ] Top bar: brand mark + product name pinned left, user-initials avatar pinned right, fluid main column beneath it (content capped per `DESIGN.md`'s layout tokens)
  - [ ] Home renders three action cards — Start a New Project, Managed Applications, Watch a Product Demo — only "Start a New Project"/"Managed Applications" have a real destination in this story (routing into Story 1.3's Connect App form); "Watch a Product Demo" can point at a placeholder until a real destination exists, but the card itself and its copy must be correct now
  - [ ] Avatar click opens a menu showing the signed-in user's name, email, and a Log out action; Log out clears the session and returns to sign-in
  - [ ] Active/hover states and focus treatment follow `DESIGN.md`'s button/link component tokens
  - [ ] Visible focus ring on every interactive element (top-bar links, action cards, avatar menu, buttons) and native keyboard operability — no `<div onclick>` substitutes
- [ ] Task 4: Implement the design-token system (AC: 2, 7)
  - [ ] Port every token in `DESIGN.md`'s frontmatter (colors, typography, rounded, spacing, component tokens) into CSS custom properties
  - [ ] `:root` sets light values + `color-scheme: light`; `@media (prefers-color-scheme: dark)` overrides for OS dark preference; explicit `:root[data-theme="dark"]`/`:root[data-theme="light"]` attribute selectors so an in-app toggle can override the OS preference
  - [ ] No component/screen may hardcode a color outside this token layer — this rule starts now and holds for every subsequent story
  - [ ] A full theme-toggle *control* has no assigned screen yet (Settings, where it would naturally live, isn't built until Epic 7) — wiring the `data-theme` attribute-setting mechanism (e.g. a small JS helper that toggles the attribute + persists to `localStorage`) now, even without a visible UI control for it yet, avoids retrofitting the CSS-selector contract later; a visible toggle affordance is not required by this story's ACs
  - [ ] Route all real label/caption/metadata text in the shell through `ink-muted` (~5:1 AA contrast); reserve `ink-faint` exclusively for decorative/non-text marks
  - [ ] Apply the voice-and-tone rule to any copy added in this story (nav labels, empty states): no exclamation points, no emoji, no celebratory language; capitalize Application/Capability/Journey/Scenario/Test Asset/Trusted Knowledge Model as proper nouns wherever they appear
- [ ] Task 5: Build the Home screen as a minimal, Organization-scoped landing target (AC: 1, 5)
  - [ ] Sign-in success routes to Home, rendered beneath the top bar
  - [ ] Suppress the top-bar Application-name breadcrumb on this screen (it's inherently pre-Application, per UX-DR16)
  - [ ] Since Story 1.3 hasn't run yet, there are no `Application` records — the three action cards render regardless (they are entry points, not data-driven); do not build a Managed Applications table, hero-stat strip, or the Connect App form itself here, those belong to Story 1.3
- [ ] Task 6: Verify end-to-end and record evidence (AC: 1-7)
  - [ ] Sign in as a seeded User lands on Home beneath the top bar, correct breadcrumb suppression
  - [ ] Toggling OS dark-mode preference (and, separately, the `data-theme` attribute) repaints every token-driven surface with no hardcoded-color exceptions
  - [ ] Keyboard-only navigation (Tab) reaches every top-bar link, action card, and the avatar menu with a visible focus ring, in visual order
  - [ ] Avatar menu opens on click/keyboard-activation, shows name/email, and Log out ends the session
  - [ ] Cross-Organization isolation test (Task 2) passes
  - [ ] CI (from Story 1.1) stays green

## Dev Notes

- **This story depends on Story 1.1 being implemented first**, not just created. As of this story's creation, Story 1.1 is `ready-for-dev` (not `done`) and the repository's only commit is the initial BMad scaffold commit — there is no FastAPI app, no `apps/web` Vite project, no Postgres/Alembic wiring, and no OpenAPI codegen pipeline yet to build this story's sign-in/shell work on top of. If you are picking up this story and Story 1.1's scaffold isn't actually in the codebase yet, stop and implement/verify 1.1 first rather than re-deriving its setup ad hoc inside this story.
- **AD-12 is the load-bearing rule here:** "`Organization` is a first-class tenant-boundary entity; every `apps/api` query must be scoped by the authenticated user's Organization through one central mechanism, never left to individual endpoints." Getting this right in one place now (Task 2) is what lets every later module (Review, Analytics, Onboarding) skip re-implementing tenant isolation — get it wrong and it's an N-endpoint fix later, not a one-file fix.
- **Platform auth has no PRD FR** (confirmed via the Implementation Readiness Report's tracked follow-up item) — Architecture AD-12 and the UX's Login screen are what this story builds against, not a numbered FR. This is a known, already-accepted gap, not something to flag as a blocker.
- **Scope discipline, mirroring Story 1.1's note:** Don't build Story 1.3's Connect App form/Managed Applications table, don't build Settings (Epic 7, deferred), don't build a public registration flow (no story covers one). A shell that quietly does a later story's job creates merge conflicts for whoever picks up 1.3 next.
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

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
