# Story 1.4: Configure Application Authentication Method

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 — "Authentication method" is now a plain `<select>` field on the single Connect App form, not a wizard step with option cards; see `sprint-change-proposal-2026-07-15.md`.*

## Story

As a user onboarding an Application,
I want to choose how the platform authenticates to it — standard login or a reusable pre-authenticated session,
so that SSO/MFA-protected apps can still be discovered.

## Acceptance Criteria

1. **Given** a user filling out the Connect App form, **when** they select "Username & Password" from the Authentication method dropdown, **then** username/password fields are captured and stored via `SecretsClient` for later use establishing a session before discovery. [Source: epics.md#Story 1.4]
2. **Given** the user instead needs SSO/MFA session-reuse, **when** they provide the reusable session state through the (explicitly provisional, per PRD Open Question 8) placeholder mechanism, **then** that session state is stored via `SecretsClient` as a secret reference, never in plaintext. [Source: epics.md#Story 1.4; PRD Open Question 8]
3. The Authentication method control is a plain `<select>` dropdown, not an option-card selector — a keyboard-operable native element with a visible focus ring, offering "Username & Password" and the SSO/MFA session-reuse choice. [Source: epics.md#Story 1.4; UX-DR18, EXPERIENCE.md#Accessibility Floor]
4. The UI does not claim the platform performs a SAML/OAuth/OIDC handshake or MFA-code retrieval itself. [Source: FR-3 consequence]

**`[GAP — flagged 2026-07-15]`** The current reference prototype's Connect App form shows only a generic Authentication method `<select>` with no visible SSO/MFA session-handoff option or field. PRD Open Question 8 remains unresolved — do not read this absence as "SSO/MFA support was cut." Needs explicit confirmation (from a fuller prototype export or direct product decision) before this story is built, specifically for the SSO/MFA branch of AC 2 above. [Source: epics.md#Story 1.4]

## Tasks / Subtasks

- [ ] Task 1: Extend the `Application` entity for auth-method selection (AC: 1, 2)
  - [ ] Add `auth_method` (`"standard_login" | "sso_session_reuse"`) to `Application` (added by Story 1.3), plus an Alembic migration
  - [ ] Keep a single `secret_ref` column pointing at whichever credential type is currently active, rather than two parallel ref columns — this mirrors the `<select>`'s "exactly one selected at a time" rule at the data-model level too. Switching auth method repoints `secret_ref`; it does not need to preserve the previously-stored secret (the selection is mutually exclusive, not additive)
- [ ] Task 2: Build the "Username & Password" path — reusing, not duplicating, Story 1.3's capture (AC: 1, 3)
  - [ ] Story 1.3's Connect App form already collects a username/password pair as the default/standard case and writes it via `SecretsClient` — **do not build a second, separate standard-login form here.** The Authentication method `<select>` should default to "Username & Password" pre-selected, displaying/confirming the fields already captured on the same form (with an edit affordance), not re-prompting blank fields
  - [ ] If the user edits the username/password here, write the update via `SecretsClient` the same way Task 3 of Story 1.3 did, and repoint `Application.secret_ref` accordingly
- [ ] Task 3: Build the SSO/MFA session-reuse path as an explicit, provisional placeholder (AC: 2) — **retain this task even though the current prototype doesn't show it; see the `[GAP]` note above**
  - [ ] **This mechanism is a known unresolved product decision — PRD Open Question 8 states the actual session-state handoff mechanism is undecided and "must be resolved before UX/architecture work on the Application Onboarding flow proceeds," yet both UX and Architecture already carry it forward as a named placeholder rather than blocking all of Epic 1 on it.** Build to the placeholder shape the UX spine names — paste session-state JSON, or reference a `storageState.json` file (Playwright's native session-state format, a reasonable fit given the architecture's Playwright-based discovery worker) — but do not treat this as a finished design. Keep the implementation simple and isolated (one field, one storage call) so it is cheap to revise once OQ8 is actually resolved; do not build supporting infrastructure (e.g. a session-state validator, expiry-detection UI beyond what Story 2.4 already owns) speculatively around it
  - [ ] Whatever the user provides (JSON blob or file reference) is written via `SecretsClient` as Task 2 of Story 1.3 did — never persisted in Postgres or logs in plaintext
  - [ ] `Application.auth_method` is set to `sso_session_reuse` and `secret_ref` repointed to this new secret
  - [ ] Since the current prototype's `<select>` doesn't visibly expose this option, confirm with product/UX before wiring the option into the dropdown itself — the storage logic (Task 3) can be built provisionally, but the UI affordance for reaching it needs the re-verification called out in the `[GAP]` note
- [ ] Task 4: Build the Authentication method select dropdown (AC: 3)
  - [ ] A plain, native `<select>` (per epics.md's 2026-07-15 update — no option cards, no `<input type="radio">`) offering "Username & Password" and (pending the `[GAP]` above) SSO/MFA session reuse
  - [ ] Native `<select>` keyboard operability (arrow keys, type-ahead) and a visible focus ring per `DESIGN.md`'s form-control tokens; selecting a new option in the dropdown updates `auth_method` and swaps the form's visible credential fields accordingly
- [ ] Task 5: Enforce the no-overclaiming constraint in copy (AC: 4)
  - [ ] Nowhere in this step's UI copy (labels, help text, placeholder text) may it state or imply the platform performs a SAML/OAuth/OIDC handshake or retrieves an MFA code itself — phrase the SSO/session-reuse option as the customer supplying an already-authenticated session, not the platform logging in on their behalf
  - [ ] Standard voice-and-tone rules apply (fact + why, no apology, no hype, capitalize Application as a proper noun)
- [ ] Task 6: Verify end-to-end and record evidence (AC: 1-4)
  - [ ] "Username & Password" (default) shows Story 1.3's already-captured credentials; editing and resaving updates the same `SecretRef` path
  - [ ] Selecting SSO/session-reuse (once the `[GAP]` above is resolved) and submitting a placeholder value stores it via `SecretsClient`, sets `auth_method=sso_session_reuse`, and the Postgres row/logs contain no plaintext session state
  - [ ] Keyboard-only interaction (Tab, arrow keys) can operate the `<select>` and change the visible credential fields
  - [ ] Switching selection after already choosing one correctly repoints `secret_ref`

## Dev Notes

- **This story is explicitly, formally blocked on an unresolved product decision (PRD Open Question 8), and the planning artifacts already tell you how to handle that rather than leaving it to guesswork:** OQ8 asks how a customer actually hands off a reusable session state, and the PRD states it "must be resolved before UX/architecture work on the Application Onboarding flow (§4.1) proceeds" — yet Architecture's own Deferred section and the UX spine (`EXPERIENCE.md`'s `[NOTE FOR PM/ENG — placeholder, not a confirmed decision]` callout) both already carry it forward as a **named, provisional placeholder**, not a hard blocker on this story. The Implementation Readiness Report confirmed this treatment is correct and non-blocking for starting Epic 1. Build Task 3 to that placeholder shape, keep it minimal, and don't gold-plate it — it is very likely to be revised once OQ8 is actually answered.
- **Do not duplicate Story 1.3's standard-login form.** This was flagged explicitly in Story 1.3's Dev Notes when that story was written: 1.3's Connect App form already captures username/password for the default case; this story's "Username & Password" `<select>` option must reuse/confirm that capture, not re-implement it. Read Story 1.3's file before starting Task 2.
- **AC 4 is a real functional constraint, not just a copy nitpick** — per FR-3's consequence, "Platform never implements a SAML/OAuth/OIDC handshake or MFA-code retrieval itself in V1." Don't add any library or code path (e.g. an OAuth client, a TOTP/MFA-code generator) that would make that claim true — the SSO path is purely "accept a session the customer already produced," never "log the customer in via SSO ourselves."
- **Secrets discipline is identical to Story 1.3's**: everything goes through `SecretsClient`, nothing plaintext in Postgres or logs — reuse the log/column assertion test pattern Story 1.3 established rather than writing a new one from scratch.
- **2026-07-15 IA change:** the option-card/radio selector described in the prior revision of this story no longer applies — Authentication method is now a plain `<select>` on the single Connect App form (Story 1.3). See the `[GAP — flagged 2026-07-15]` note above the Acceptance Criteria: the SSO/MFA branch itself (PRD Open Question 8) is still unresolved, not confirmed cut, so Task 3's storage logic is retained as provisional work pending that decision. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

### Project Structure Notes

- Extends `Application` (added in Story 1.3) and reuses the `SecretsClient` adapter Story 1.3 stood up — no new top-level directories or packages.
- **Depends on Stories 1.1, 1.2, and 1.3 being actually implemented**, not just created — all three are `ready-for-dev`, not `done`, as of this story's creation, and only the initial BMad-tooling commit exists in git. Verify those are built before starting this one.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4: Configure Application Authentication Method]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — Open Question 8, FR-3]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Deferred — SSO/MFA session-state capture mechanism]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Component Patterns — placeholder note on the Authenticate step]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Accessibility Floor — radio-driven selection patterns]
- [Source: _bmad-output/planning-artifacts/implementation-readiness-report-2026-07-13.md — OQ8 confirmed non-blocking, treated as a named placeholder]
- [Source: _bmad-output/implementation-artifacts/1-3-onboard-an-application-basic-details.md — standard-login capture this story must reuse, not duplicate]

## Previous Story Intelligence

Stories 1.1, 1.2, and 1.3 all remain `ready-for-dev` (not `done`) as of this story's creation — `git log` shows only the initial BMad-tooling commit, so there's no implemented code yet to inherit real patterns from. The load-bearing carry-forward isn't code, it's the explicit design decision recorded in 1.3's Dev Notes: standard-login credential capture belongs to 1.3's step 1, and this story (the auth-method step) must build on top of that rather than re-collecting it. Verify 1.1–1.3 are actually implemented before starting this story.

## Latest Technical Notes

No new library decisions beyond what Stories 1.1 and 1.3 already established (SecretsClient adapter, FastAPI/SQLModel stack). If a `storageState.json`-shaped placeholder is used for Task 3, note that this is Playwright's own session-state export format — worth confirming its current shape against whatever Playwright Python version Story 1.1 pinned, since the discovery worker (Epic 2) will eventually need to consume it.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
