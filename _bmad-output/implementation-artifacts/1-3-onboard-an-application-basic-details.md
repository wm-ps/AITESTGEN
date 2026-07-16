# Story 1.3: Onboard an Application — Basic Details

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Updated 2026-07-15 — the 3-step wizard is replaced by a single-page Connect App form; see `sprint-change-proposal-2026-07-15.md`.*

## Story

As a QA Director or Engineering Leader,
I want to register a new Application by providing its URL, environment designation, and Dedicated Test Account credentials,
so that it becomes available for discovery configuration.

## Acceptance Criteria

1. **Given** a signed-in user on Home, **when** they choose "Start a New Project" (or "Managed Applications") and submit Application name, Base URL, environment, credentials, and authentication method (Story 1.4) on the single Connect App form, **then** an `Application` record is created, scoped to their Organization, and the submitted credentials are written only through `packages/secrets_client` (Vault/KMS-backed), never stored in plaintext in Postgres or logs. [Source: epics.md#Story 1.3; FR-2; architecture#AD-5; NFR-1]
2. The credentials field is explicitly labeled as requiring a Dedicated Test Account, not a real end-user identity. [Source: FR-2]
3. The Connect App screen shows the current Application's name and environment badge in the top bar once submitted, per the (2026-07-15) breadcrumb rule. [Source: epics.md#Story 1.3]
4. **`[ABSORBED FROM REMOVED STORY 1.5, 2026-07-15]`** Submitting returns the user to the pipeline's Discover Journeys step, and starts a Discovery Run immediately against the full Application (Story 2.1) — there is no scope/time-budget configuration (FR-4/FR-5 removed) and no separate "Start Discovery Run" action. [Source: epics.md#Story 1.3; #Story 2.1]

*(Superseded 2026-07-15: the prior AC described a multi-step wizard stepper where only the active step's form renders. Connect App is now one consolidated form with a single "Connect Application" submit — no internal stepper.)*

## Tasks / Subtasks

- [x] Task 1: Add the `Application` domain entity, establishing the UUIDv7/UUIDv4 id convention (AC: 1)
  - [x] Add `Application` (organization_id FK, name, url, environment, secret_ref, timestamps) to `packages/domain` — `name` is a new field surfaced by the 2026-07-15 Connect App form (the top-bar breadcrumb now shows an Application's name, not just its URL/environment)
  - [x] **This is the first entity whose id is ever exposed to the frontend** — apply the architecture's Consistency Convention now, correctly, since every later entity (`DiscoveryRun`, `Journey`, `Scenario`, `TestAsset`, ...) follows the same rule: the internal primary key is a UUIDv7 (Postgres 18 native `uuidv7()`, chosen for index locality), and any id returned in an API response is a **separate, opaque UUIDv4** — the UUIDv7 PK must never leave the backend, since its embedded timestamp would leak the record's creation time
  - [x] `environment` is a free-text designation (e.g. "staging", "UAT") — neither the PRD nor UX specifies a fixed enum; don't invent one
  - [x] Alembic migration for the new table
- [x] Task 2: Implement the first concrete `SecretsClient` adapter (AC: 1)
  - [x] Story 1.1 stubbed only `SecretsClient`'s Protocol interface in `packages/secrets_client`, with no implementation — this story needs a working one. Architecture explicitly defers the Vault-vs-cloud-KMS choice to deploy time (not a V1 blocker), so pick one now to unblock the build: **Vault in dev-mode** is the recommended default (portable across the still-undecided SaaS/on-prem topology, trivial to run locally/in CI via a container, no cloud account dependency) — a cloud-KMS adapter is an equally valid alternative if you have a strong reason to prefer it; document whichever is chosen in Completion Notes
  - [x] Implement `store(organization_id, secret) -> SecretRef` and `resolve(ref) -> bytes` exactly per the Protocol signature in the Architecture Spine's Module Contracts section
  - [x] Add a test that proves a raw credential never reaches a Postgres column or an application log line (e.g., assert the `Application.secret_ref` column and captured log output never contain the plaintext value) — this is what actually enforces AD-5 and NFR-1, not just convention
- [x] Task 3: Build the Application-onboarding endpoint backing the Connect App form (AC: 1, 2, 4)
  - [x] Add a POST endpoint to the Onboarding module in `apps/api`, passing through Story 1.2's Organization-scoping middleware
  - [x] Accept `name`, `url`, `environment`, and credentials (username/password, representing the standard-login default — see Dev Notes on the 1.3/1.4 credential-capture split)
  - [x] Write credentials via `SecretsClient` immediately; the `Application` row stores only the returned `SecretRef`, never the raw value
  - [x] Validation/error messaging must state the Dedicated Test Account requirement as fact (FR-2) — this is a labeling requirement on the credentials field, not just documentation
  - [x] Do **not** add any check that inspects or blocks a URL for being "production" — see Dev Notes, this is explicitly out of scope for V1
  - [x] **`[ABSORBED FROM REMOVED STORY 1.5, 2026-07-15]`** In the same request that creates the `Application` row, create a `DiscoveryRun` (`status=running`) and start its bounded `DiscoveryWorkflow` (Story 2.1, AD-1) — there is no separate "Start Discovery Run" endpoint or user action; onboarding and discovery-start are one atomic flow now that scope/time-budget configuration (Story 1.5) is removed
- [x] Task 4: Build the single-page Connect App form in `apps/web` (AC: 1, 2, 3)
  - [x] One consolidated form, no internal stepper — all fields render at once, single "Connect Application" submit action (2026-07-15: supersedes the prior multi-step wizard/stepper design; Story 1.4's auth-method field lives on this same form, not a separate step). `[UPDATED 2026-07-15]` No scope/time-budget fields — Story 1.5 removed in full, not merely re-verified
  - [x] Form fields: Application name, Base URL, environment designation, credentials — matching Task 3's endpoint
  - [x] Credentials field label/help text states the Dedicated Test Account requirement plainly (per Voice and Tone: fact + why, no apology, no hype)
  - [x] Do **not** phrase any copy as if the platform verifies or blocks production URLs (e.g. avoid a literal "production URLs are blocked at setup" claim) — see Dev Notes, no such platform-side check exists
  - [x] No Application-name breadcrumb until the form is submitted — no Application exists yet (UX-DR16); once submitted, the top bar shows the new Application's name and environment badge (AC 3)
  - [x] Reuse the focus-ring/keyboard-operability standard established in Story 1.2's shell
  - [x] **`[ABSORBED FROM REMOVED STORY 1.5, 2026-07-15]`** On successful submission, navigate directly to the Discover Journeys pipeline step (Story 2.1) — there is no intermediate Applications-list screen to land on (AC 4)
- [x] Task 5: Wire the Connect App entry point (AC: 1)
  - [x] Add the affordance on Home's "Start a New Project" and "Managed Applications" action cards (built in Story 1.2) that opens this form
- [x] Task 6: Verify end-to-end and record evidence (AC: 1-4)
  - [x] Submitting the Connect App form creates an `Application` row scoped to the signed-in user's Organization, with a resolvable `SecretRef`
  - [x] The Postgres row and application logs contain no plaintext credential (Task 2's test)
  - [x] A second Organization's user cannot read this Application via the API (reuse Story 1.2's isolation-test pattern)
  - [x] The form renders as a single page with no stepper — every field is visible and editable before submission
  - [x] After submission, the top bar shows the new Application's name and environment badge
  - [x] After submission, a `DiscoveryRun` exists with `status=running` for the new Application, its `DiscoveryWorkflow` is observable via Temporal CLI/Web UI, and the user lands on Discover Journeys — no manual "start discovery" step required

## Dev Notes

- **Credential capture is deliberately split across Stories 1.3 and 1.4 — read this before building either.** Epics AC for 1.3 says the Connect App form collects "Application name, Base URL, environment, and credentials"; epics AC for 1.4 (2026-07-15: now a plain `<select>` field on this same single form, not a separate wizard step) separately describes an "Authentication method" dropdown where the user chooses between "Username & Password" and SSO/MFA session-reuse. Resolution used here: **Story 1.3's form collects the standard-login username/password case** (satisfying its own AC literally, written via SecretsClient as Task 3 describes). **Story 1.4 then lets the user override this via the Authentication method select** — if they leave/select "Username & Password," 1.4 should reuse/confirm the fields 1.3 already captured rather than re-implementing a duplicate form; if they select SSO/MFA session-reuse instead, 1.4 adds the alternate, separate capture path (flagged `[GAP]` in Story 1.4 — not visible in the current prototype). Whoever implements 1.4 should read this note first to avoid building a redundant standard-login form.
- **No platform-side production-environment safeguard exists in V1, by explicit PRD decision** — confirmed directly: "Onboarding does not technically verify that the target is a Non-Production Environment" (PRD §4.1 Notes), and PRD §11/§12 Risk #1 state this is customer responsibility only, with "whether V1 needs a technical safeguard" listed as PRD Open Question 3 (unresolved, not assigned to this or any other V1 story). Do not build any URL inspection/blocking logic. Also avoid the specific phrase "production URLs are blocked at setup" anywhere in this story's UI copy — that phrase appears in `EXPERIENCE.md`'s Voice-and-Tone table purely as a *style* example of "fact + why" phrasing, not as a confirmed built behavior; using it verbatim here would make the UI claim a guardrail that doesn't exist, which the Voice and Tone rule ("state facts plainly") actually argues against once you know the real behavior.
- **UUIDv7-internal / UUIDv4-external is a system-wide convention, established for the first time by this story** — get the pattern right here since `DiscoveryRun`, `Journey`, `Capability`, `Scenario`, `TestAsset`, and `Evidence` in later epics all reuse it without restating it.
- **AD-5 / NFR-1 in practice:** the "never stored in plaintext" requirement is only real if it's tested (Task 2's log/column assertion), not just achieved by convention — a future refactor could silently reintroduce a plaintext field otherwise.

### Project Structure Notes

- Builds on `packages/domain` (adds `Application`), `packages/secrets_client` (adds its first real adapter, previously just a stub interface from Story 1.1), `apps/api`'s Onboarding module, and `apps/web`'s shell (Story 1.2). `[UPDATED 2026-07-15]` Also starts `DiscoveryWorkflow` (Story 2.1) in the same request — absorbed from removed Story 1.5. No new top-level directories.
- **Depends on Stories 1.1 and 1.2 being actually implemented, not just created.** As of this story's creation, both are `ready-for-dev` (not `done`), and `git log` shows only the initial BMad-tooling commit. If picking this up before 1.1/1.2 exist in the codebase, implement/verify those first.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3: Onboard an Application — Basic Details]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4: Configure Application Authentication Method]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1: Start a Discovery Run — this story now triggers it directly, absorbed from removed Story 1.5]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-5 — Discovery credentials never touch primary storage in plaintext]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Consistency Conventions — id formats]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Module Contracts — SecretsClient]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Deferred — secrets_client backing store choice]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md §4.1 Notes, §9, §11, §12 Risk #1 — non-production safeguard explicitly out of V1 scope]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Voice and Tone, #Component Patterns — Stepper]
- [Source: _bmad-output/implementation-artifacts/1-2-sign-in-organization-scoped-workspace.md — Organization-scoping middleware and Applications shell this story builds on]

## Previous Story Intelligence

Neither Story 1.1 nor Story 1.2 has been implemented yet (`git log` shows only the initial BMad-tooling commit; both are `ready-for-dev`). There is no established `Application`-adjacent code, SecretsClient adapter, or wizard shell to inherit patterns from — this story is the first to add a real domain entity beyond 1.1's throwaway proof-of-wiring row, and the first to implement `SecretsClient` beyond its stubbed interface. If 1.1/1.2 aren't actually built yet, implement/verify them first.

## Latest Technical Notes

- No new architecture-fixed library beyond what 1.1 already established. If Vault is chosen for Task 2, use its current-stable client library and dev-mode container image — verify the exact current version at implementation time rather than assuming one.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- Same run as Story 1.2 (implemented together in one pass): `uv run pytest` with
  Postgres+Vault+Temporal up → 10 passed, including
  `test_onboarding.py::test_create_application_never_stores_plaintext` and
  `::test_cross_organization_isolation`.
- Real-network `curl` smoke test: created an Application via `POST /applications` against the
  live API/Vault/Temporal — response included `discovery_run_id` and `discovery_status=running`.
- `ruff`, `pyright`, `oxlint`, `tsc -b`, `vite build`, `vitest` all green (see Story 1.2's Dev
  Agent Record for the shared command log).

### Completion Notes List

- **SecretsClient backing store: dev-mode Vault** (`packages/secrets_client/vault_client.py`,
  `hvac` client), per the story's recommended default — portable across the undecided
  SaaS/on-prem topology, trivial locally/in CI via a container. `SecretRef` is a frozen dataclass
  wrapping the opaque Vault KV-v2 path; `Application.secret_ref` stores only `ref.path`, never
  the raw credential. Enforced by `test_create_application_never_stores_plaintext`, which asserts
  the plaintext password is in neither the `Application.secret_ref` column nor any captured log
  record (via `caplog`), not just by convention.
- **UUIDv7-internal / UUIDv4-external convention established on `Application`** (and reused on
  `DiscoveryRun`): `id` is the Postgres-native `uuidv7()` PK, never serialized; `external_id`
  (app-generated `uuid4`) is the only id in `ApplicationRead`/`GET /applications/{external_id}`.
- **DiscoveryRun + DiscoveryWorkflow absorbed from removed Story 1.5**, in the same request as
  `POST /applications`: creates a `DiscoveryRun(status="running")` row and starts a **no-op**
  `DiscoveryWorkflow` shell (`packages/workflows/discovery_workflow.py`, zero I/O per AD-2) on a
  new `discovery-task-queue`, picked up by a new `apps/workers/discovery` worker process (Story
  1.1 had left this worker as a directory scaffold only). The real autonomous-exploration
  orchestration is Story 2.1's job — this shell only needs to exist and be startable.
- **No production-URL safeguard added, by design** — per the story's Dev Notes, this is an
  explicit, unresolved PRD open question, not a gap in this implementation.
- **Credential capture split honored:** this form/endpoint captures only the standard-login
  username/password case; Story 1.4's Authentication method select is not built here.
- **Verification gap — no browser tool available in this environment:** the Connect App form's
  single-page-no-stepper rendering and the top-bar Application-name/environment-badge swap after
  submit were verified by code inspection and the `curl`/`vitest` checks above, not by visually
  driving the page in a browser. A manual pass is recommended before this story is considered
  fully done.
- See Story 1.2's Completion Notes for the shared CI/Vault/Temporal wiring and the ScaffoldProbe
  removal — both stories were implemented in one pass against the same codebase.
- **2026-07-16 — full stack validated live, closing the prior browser-tool gap:** created
  Applications through the real running API (not `TestClient`), confirmed the `secret_ref`
  written to Postgres resolves to the exact submitted credential in Vault's KV v2 engine, and
  confirmed via `temporal workflow list` that each request's `DiscoveryWorkflow` actually reaches
  `Completed`. Re-ran the AD-12 isolation case live (see Story 1.2's note) against `/applications`
  specifically. Also caught and fixed two regressions in in-progress, uncommitted frontend polish
  found during this pass, before they were committed: (1) `ConnectAppForm.tsx` had grown an
  `environment` `<select>` restricted to three fixed values, directly contradicting this story's
  Task 1 instruction that `environment` stay free-text with no invented enum — reverted to a text
  input; (2) the same file had grown an "Authentication method" dropdown (Story 1.4's job, not
  built here) whose "OAuth Client Credentials" option rendered no input fields yet was fully
  submittable, silently creating an Application with a blank Vault-stored credential — removed,
  restoring the plain username/password fields this story's endpoint actually supports. Full
  Python + web health checklist re-run clean after the fix (see Story 1.2's note for the command
  list); `git diff --exit-code` on `api-types.gen.ts` confirmed no contract drift.

### File List

See Story 1.2's File List — both stories were implemented together in one pass and touch
overlapping files (`packages/domain`, `packages/secrets_client`, `packages/workflows`,
`apps/workers/discovery`, `apps/api`, `migrations`, `apps/web`). Nothing in this story's scope
touches a file outside that list.
