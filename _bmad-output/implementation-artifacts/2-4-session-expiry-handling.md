# Story 2.4: Session Expiry Handling

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to be told plainly when a Discovery Run fails because my session expired,
so that I can re-authenticate rather than mistake it for a normal, if small, result.

## Acceptance Criteria

1. **Given** a running Discovery Run whose session has expired mid-crawl (detected via an auth-redirect), **when** `DiscoveryActivity` detects this condition, **then** it terminates the run with `DiscoveryRun.status=failed`, `failure_reason=session_expired` — a condition distinct from a normal stop condition. [Source: epics.md#Story 2.4; architecture#AD-11]
2. The platform surfaces a re-authentication prompt keyed specifically off `session_expired`, visually distinguishable from any other `failed` cause. [Source: epics.md#Story 2.4; FR-3] `[UPDATED 2026-07-15]` No longer needs distinguishing from an `incomplete` (time-budget) run — that status no longer exists (FR-5 removed).

## Tasks / Subtasks

- [ ] Task 1: Add `failure_reason` to `DiscoveryRun` (AC: 1)
  - [ ] Add a nullable `failure_reason` column, meaningful only when `status="failed"`. `session_expired` is the one value the Architecture Spine names explicitly (AD-11) — a generic/unrelated crash also sets `status=failed` but can leave `failure_reason` null, since neither PRD nor architecture defines a fuller failure-reason taxonomy for V1
  - [ ] Alembic migration
- [ ] Task 2: Detect session expiry mid-crawl, as a second stop condition alongside Story 2.3's exhaustive-traversal check (AC: 1)
  - [ ] Add the auth-redirect check into the same per-iteration checks `DiscoveryActivity` already runs for exhaustive-traversal detection (Story 2.3) — this is a second branch in the same loop, not a separate mechanism. `[UPDATED 2026-07-15]` No time-budget branch exists to sit alongside — FR-5 removed
  - [ ] **Detection heuristic is genuinely underspecified beyond "via an auth-redirect"** — neither PRD nor architecture defines the exact match logic, the same class of gap as Story 2.2's crawl-algorithm description. Reasonable default: capture the login URL used when the session was established (Story 1.4's auth step) as part of `DiscoveryRun` context, and treat a mid-crawl navigation that resolves to that same URL (or a close pattern match) as session expiry. Treat this as a sound starting point, not a literal spec to match exactly
  - [ ] On detection, stop immediately — don't run the exhaustive-traversal check for that iteration — and write `DiscoveryRun.status="failed"`, `failure_reason="session_expired"`. **This must be a distinct code path from Story 2.3's `complete` write** — AD-11 exists specifically to prevent a session-expired run from silently landing in `complete` and looking like a finished, if small, result
  - [ ] For any other unhandled exception during exploration (a genuine crash, unrelated to session expiry), also terminate with `status="failed"` — this story doesn't need to build a complete error-handling framework, only ensure a crash doesn't leave the run stuck showing `running` forever
- [ ] Task 3: Surface the re-authentication prompt and failed-state pill (AC: 2)
  - [ ] On Discovery Progress, when `status=failed` and `failure_reason=session_expired`, show a re-authentication prompt distinct from a generic failure message — plain factual copy per Voice and Tone (state the fact and the fix, no apology — e.g. "Session expired mid-crawl. Re-authenticate to continue discovery." not "Oops, your session expired!")
  - [ ] **`Failed` has no documented status-pill variant in `DESIGN.md`**, the same class of gap Story 2.3 already resolved for `Complete`. Resolved consistently here: `{colors.danger-wash}`/`{colors.danger}` (red) for any `failed` run, per `DESIGN.md`'s stated semantic rule ("red means rejected/failing") — distinct from Story 2.3's green `Complete`. Flag this as a filled gap, same as 2.3's, not a literal citation
  - [ ] A `failed` run for any reason other than `session_expired` shows the same red pill but without the specific re-authentication prompt — a generic failure indication is sufficient; don't invent additional named failure-cause UI beyond what AC 2 actually requires
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Simulating a session-expiry mid-crawl (e.g. against a test target that redirects to a login page after N requests) produces `status=failed`, `failure_reason=session_expired`, and the re-authentication prompt
  - [ ] The failed/session-expired pill is visually distinct from Story 2.3's `Complete` (green) treatment
  - [ ] A non-session-related crash still resolves to `status=failed` without leaving the run stuck at `running`, and without showing the re-auth-specific prompt

## Dev Notes

- **This is Story 2.3's loop, extended, not a new mechanism.** Read Story 2.3's Dev Notes and File List before starting Task 2 — the exhaustive-traversal and session-expiry checks both belong in the same per-iteration check inside `DiscoveryActivity`.
- **AD-11's whole point is the distinction from `complete`.** A session-expired run must not be miscoded as `complete` — make sure the auth-redirect check is evaluated (and, if triggered, wins) before the exhaustive-traversal check each iteration. `[UPDATED 2026-07-15]` Previously also had to guard against miscoding as `incomplete` (time-budget); that status no longer exists (FR-5 removed), simplifying this to a two-way distinction (`failed` vs. `complete`).
- **Status-pill color gaps are now a repeating, consistent pattern across Stories 2.3 and 2.4** — `DESIGN.md` only ever named `Running` (signal) explicitly; `Complete` (green, 2.3) and `Failed` (red, this story) were both filled in using the design system's own semantic-color rule rather than an explicit citation. If a future design pass formalizes these, that's the design system catching up, not a correction to either story. `[UPDATED 2026-07-15]` `DESIGN.md`'s amber `Incomplete` transition no longer applies to anything — that status is removed.
- **FR-3's "platform never implements a SAML/OAuth/OIDC handshake itself" constraint (from Story 1.4) still applies here** — the re-authentication prompt invites the *user* to re-supply session state (going back through Story 1.4's mechanism), it does not attempt to re-authenticate on the user's behalf.

### Project Structure Notes

- Modifies `DiscoveryActivity` (Stories 2.1-2.3) and Discovery Progress rendering (`apps/web`). No new entities beyond the `failure_reason` column, no new top-level directories.
- **Depends on Stories 2.1–2.3 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4: Session Expiry Handling]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-3]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-11 — Session expiry as a named failure mode]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — status-pill; #EXPERIENCE.md#Voice and Tone]
- [Source: _bmad-output/implementation-artifacts/2-3-discovery-stop-conditions-completeness-status.md — Story 2.3, renamed "Discovery Completion" 2026-07-15; the same per-iteration check loop this story extends, and the pill-color-gap precedent this story follows]
- [Source: _bmad-output/implementation-artifacts/1-4-configure-application-authentication-method.md — the auth mechanism a re-authentication prompt sends the user back to]

## Previous Story Intelligence

Stories 2.1–2.3 remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once 2.3 is implemented, check its File List for the exact shape of the per-iteration stop-condition checks before adding the session-expiry branch here.

## Latest Technical Notes

No new library decisions — extends the existing Playwright-based `DiscoveryActivity` from Stories 2.1–2.3.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
