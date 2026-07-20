---
baseline_commit: 48b6499e08423320a0156e02720f1e8e2ba7d66c
---

# Story 2.4: Session Expiry Handling

Status: done <!-- implementation and tests were already complete pre-session; not itself exercised by this session's live end-to-end runs (no session-expiry scenario occurred against the live test target) -->

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to be told plainly when a Discovery Run fails because my session expired,
so that I can re-authenticate rather than mistake it for a normal, if small, result.

## Acceptance Criteria

1. **Given** a running Discovery Run whose session has expired mid-crawl (detected via an auth-redirect), **when** `DiscoveryActivity` detects this condition, **then** it terminates the run with `DiscoveryRun.status=failed`, `failure_reason=session_expired` — a condition distinct from a normal stop condition. [Source: epics.md#Story 2.4; architecture#AD-11]
2. The platform surfaces a re-authentication prompt keyed specifically off `session_expired`, visually distinguishable from any other `failed` cause. [Source: epics.md#Story 2.4; FR-3] `[UPDATED 2026-07-15]` No longer needs distinguishing from an `incomplete` (time-budget) run — that status no longer exists (FR-5 removed).

## Tasks / Subtasks

- [x] Task 1: Add `failure_reason` to `DiscoveryRun` (AC: 1)
  - [x] Add a nullable `failure_reason` column, meaningful only when `status="failed"`. `session_expired` is the one value the Architecture Spine names explicitly (AD-11) — a generic/unrelated crash also sets `status=failed` but can leave `failure_reason` null, since neither PRD nor architecture defines a fuller failure-reason taxonomy for V1
  - [x] Alembic migration
- [x] Task 2: Detect session expiry mid-crawl, as a second stop condition alongside Story 2.3's exhaustive-traversal check (AC: 1)
  - [x] Add the auth-redirect check into the same per-iteration checks `DiscoveryActivity` already runs for exhaustive-traversal detection (Story 2.3) — this is a second branch in the same loop, not a separate mechanism. `[UPDATED 2026-07-15]` No time-budget branch exists to sit alongside — FR-5 removed
  - [x] **Detection heuristic is genuinely underspecified beyond "via an auth-redirect"** — neither PRD nor architecture defines the exact match logic, the same class of gap as Story 2.2's crawl-algorithm description. Reasonable default: capture the login URL used when the session was established (Story 1.4's auth step) as part of `DiscoveryRun` context, and treat a mid-crawl navigation that resolves to that same URL (or a close pattern match) as session expiry. Treat this as a sound starting point, not a literal spec to match exactly
  - [x] On detection, stop immediately — don't run the exhaustive-traversal check for that iteration — and write `DiscoveryRun.status="failed"`, `failure_reason="session_expired"`. **This must be a distinct code path from Story 2.3's `complete` write** — AD-11 exists specifically to prevent a session-expired run from silently landing in `complete` and looking like a finished, if small, result
  - [x] For any other unhandled exception during exploration (a genuine crash, unrelated to session expiry), also terminate with `status="failed"` — this story doesn't need to build a complete error-handling framework, only ensure a crash doesn't leave the run stuck showing `running` forever
- [x] Task 3: Surface the re-authentication prompt and failed-state pill (AC: 2)
  - [x] On Discovery Progress, when `status=failed` and `failure_reason=session_expired`, show a re-authentication prompt distinct from a generic failure message — plain factual copy per Voice and Tone (state the fact and the fix, no apology — e.g. "Session expired mid-crawl. Re-authenticate to continue discovery." not "Oops, your session expired!")
  - [x] **`Failed` has no documented status-pill variant in `DESIGN.md`**, the same class of gap Story 2.3 already resolved for `Complete`. Resolved consistently here: `{colors.danger-wash}`/`{colors.danger}` (red) for any `failed` run, per `DESIGN.md`'s stated semantic rule ("red means rejected/failing") — distinct from Story 2.3's green `Complete`. Flag this as a filled gap, same as 2.3's, not a literal citation
  - [x] A `failed` run for any reason other than `session_expired` shows the same red pill but without the specific re-authentication prompt — a generic failure indication is sufficient; don't invent additional named failure-cause UI beyond what AC 2 actually requires
- [x] Task 4: Verify end-to-end and record evidence (AC: 1, 2)
  - [x] Simulating a session-expiry mid-crawl (e.g. against a test target that redirects to a login page after N requests) produces `status=failed`, `failure_reason=session_expired`, and the re-authentication prompt
  - [x] The failed/session-expired pill is visually distinct from Story 2.3's `Complete` (green) treatment
  - [x] A non-session-related crash still resolves to `status=failed` without leaving the run stuck at `running`, and without showing the re-auth-specific prompt

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

claude-sonnet-5

### Debug Log References

- `uv run pytest apps/ packages/ -q` → **22 passed** (19 pre-existing + 3 new: real session-expiry
  detection in `test_crawler.py`, and `discovery_activity` marking `failed`/`session_expired` and
  `failed`/no-reason-on-crash in `test_discovery_activity_integration.py`).
- `uv run ruff check` / `uv run pyright` → all clean.
- `npx vitest run` → **15 passed** (13 pre-existing + 2 new `DiscoverJourneysPlaceholder` tests:
  the `session_expired` re-auth prompt, and a generic failure with no re-auth prompt). `tsc -b` /
  `oxlint` clean.
- Regenerated `apps/web/src/api-types.gen.ts` after adding `discovery_failure_reason` to
  `ApplicationRead` (AD-6).
- The session-expiry test forces expiry deterministically via the test target app's own
  request-counter (`configure(expire_after=2)`, added as unused scaffolding back in Story 2.2 for
  exactly this story) rather than real time-based expiry — 2 authenticated hits succeed (the
  post-login redirect + the first dashboard visit), the third drops the session, producing a
  genuine mid-crawl failure rather than an immediate post-login one.

### Completion Notes List

- **Detection heuristic: content-based, not URL-based** — the story's own suggested default
  (match against the captured login URL) doesn't generalize to a single-URL app shell where the
  same route serves both the login form and the authenticated view depending on session state
  (exactly this story's own test target, and a realistic real-world SPA pattern). Instead,
  `run_discovery_crawl` checks for `input[type="password"]` reappearing on any page visited
  mid-crawl — the same primitive `establish_session`'s login heuristic already uses, so the
  "are we logged in" check is consistent in both places. Documented in `crawler.py` as the
  deliberate interpretation of this story's "genuinely underspecified" detection heuristic.
- **Distinct code path from `complete`, enforced by construction, not just convention**:
  `CrawlResult` gained a `session_expired: bool` field; `discovery_activity` branches on it
  explicitly (`if result.session_expired: ... else: ...`) so the `complete` write is structurally
  unreachable when expiry was detected, rather than relying on a flag being checked correctly by
  convention.
  - **Evidence captured before the drop is preserved** — the crawl loop returns normally (not via
  exception) when a password input reappears, so whatever pages/forms/actions were already
  captured that iteration are still written to Postgres; only the exhaustive-traversal
  continuation for that page is skipped, per the task's literal instruction.
- **Catch-all crash handling wraps the entire body**, not just the Playwright block — secret
  resolution (`VaultSecretsClient().resolve(...)`) was moved inside the same `try` as the crawl,
  since a bad/unresolvable `secret_ref` is exactly the kind of "genuine crash, unrelated to
  session expiry" Task 2 describes; a crash there previously would have propagated past
  `discovery_activity` entirely, leaving the run stuck at `running` forever — the literal failure
  mode this story exists to prevent. On any caught exception, `failure_reason` stays `None`
  (no fuller failure-reason taxonomy exists for V1, per Task 1) and no partial evidence is written
  (the crawl never returned a result to draw it from) — an accepted simplification per Task 2's
  "doesn't need to build a complete error-handling framework."
- **Re-authentication prompt**: exact copy from the story's own suggested example — "Session
  expired mid-crawl. Re-authenticate to continue discovery." — shown only when
  `status=failed && failure_reason=session_expired`; any other `failed` cause shows a generic
  "Discovery Run failed." message with the same red pill, no re-auth-specific copy, per Task 3's
  explicit instruction not to invent additional failure-cause UI.
- **`StatusPill`'s `failed` variant** added to the same `COLORS` lookup Story 2.3 introduced —
  `{colors.danger-wash}`/`{colors.danger}`, no pulsing dot (only `running` gets one, unchanged).
- **`ApplicationRead` gained `discovery_failure_reason`** (nullable) so the frontend can
  distinguish `session_expired` from any other failure cause without a second round-trip.
- **FR-3 discipline maintained**: the re-authentication prompt asks the *user* to re-supply a
  session (back through Story 1.4's mechanism) — no OAuth/SAML client or any re-authentication
  code was added anywhere; the platform still never logs the customer in on their behalf.
- **Verification gap — no browser tool available in this environment**: the red pill/re-auth
  prompt's visual rendering was verified via `vitest`/DOM assertions and a real end-to-end crawl
  that genuinely reaches `failed`/`session_expired` against the live local target, not by visually
  confirming the Discovery Progress screen in a real browser.
- Per the operator's instruction for this session, **no git commits were created**.

### File List

- `packages/domain/src/domain/discovery_run.py` — added `failure_reason` (nullable).
- `migrations/versions/a8cdc83f6451_add_failure_reason_to_discovery_run.py` — new migration.
- `apps/workers/discovery/src/discovery_worker/crawler.py` — `CrawlResult.session_expired`;
  password-input-reappearance check added right after each page navigation, before the
  link/form/action continuation for that page.
- `apps/workers/discovery/src/discovery_worker/activities.py` — wraps the full crawl (including
  secret resolution) in `try`/`except`; branches on `result.session_expired` vs. a caught
  exception vs. normal completion to write `failed`/`session_expired`, `failed`/`None`, or
  `complete` respectively.
- `apps/workers/discovery/tests/test_crawler.py` — new: session-expiry detection test.
- `apps/workers/discovery/tests/test_discovery_activity_integration.py` — refactored shared setup
  into `_seed_application`; added session-expiry and crash tests.
- `apps/api/src/api/main.py` — `ApplicationRead` gained `discovery_failure_reason`.
- `apps/web/src/components/StatusPill.tsx` — added the `failed` (red) color variant.
- `apps/web/src/components/DiscoverJourneysPlaceholder.tsx` — re-authentication prompt (specific
  to `session_expired`) vs. generic failure message; takes `discoveryFailureReason`.
- `apps/web/src/components/DiscoverJourneysPlaceholder.test.tsx` — new tests for both failure
  paths.
- `apps/web/src/App.tsx` — passes `discoveryFailureReason` down.
- `apps/web/src/api-types.gen.ts` — regenerated (AD-6).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status tracking only.

## Change Log

- 2026-07-17 — Implemented all 4 tasks (AC 1–2): `failure_reason` column, content-based
  session-expiry detection (password-input reappearance, chosen over URL-matching to also cover
  single-URL app shells), a catch-all crash handler covering the full Activity body, the
  re-authentication prompt, and the `failed` (red) status-pill variant distinct from `complete`
  (green). Verified against the live local target with a deterministic, request-counted
  expiry trigger. Status moved to `review`.
