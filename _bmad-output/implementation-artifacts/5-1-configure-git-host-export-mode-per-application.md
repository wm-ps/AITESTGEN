# Story 5.1: Configure Git Host & Export Mode per Application

Status: backlog

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**`[DEFERRED POST-V1 — 2026-07-15]`** The Connect to CI/CD screen this story depends on is cut from the current reference prototype's IA. Do not schedule this story for dev-story until the real delivery/execution mechanism is designed. Retained below verbatim as a record of original intent — historical spec, not a build target. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

## Story

As a user,
I want to choose my Application's Git host and export mode (pull request vs. direct commit),
so that generated tests land in my repository the way my team actually works.

## Acceptance Criteria

1. **Given** a user on the Connect to CI/CD screen, **when** they select a Git host (GitHub, GitLab, or Azure Repos) and an export mode via provider/option cards, **then** the choice is saved on the Application's `CIConfig`, with exactly one Git host and one export mode selected at a time. [Source: epics.md#Story 5.1; FR-19]
2. An Application configured for PR mode never receives a direct commit, and vice versa — the two modes are mutually exclusive per Application. [Source: epics.md#Story 5.1; FR-19]

## Tasks / Subtasks

- [ ] Task 1: Add the `CIConfig` domain entity — **including a scope addition beyond the literal AC, explained below** (AC: 1, 2)
  - [ ] Add `CIConfig` (`application_id` FK, unique — one-to-zero-or-one per the ERD; `git_host` [`"github" | "gitlab" | "azure_repos"`]; `export_mode` [`"pr" | "direct_commit"`]) to `packages/domain`, following the UUIDv7/UUIDv4 id convention
  - [ ] **Also add `repo_identifier` (e.g. owner/repo or a repo URL) and `secret_ref` (an access credential, written via `SecretsClient` — same pattern as Story 1.3's discovery credentials) — neither is named in this story's literal AC text, but both are required for Story 5.2's `DeliveryAdapter` to function at all.** Selecting "GitHub" as a Git host is meaningless without knowing *which* GitHub repository and with what write access — this is a genuine, load-bearing gap in the epics/PRD/UX documents, not a minor nicety, flagged here because leaving it out would make Epic 5 undeliverable end-to-end despite satisfying this story's literal AC wording
  - [ ] Alembic migration
- [ ] Task 2: Build the save endpoint (AC: 1, 2)
  - [ ] Add an endpoint to `apps/api`, Organization-scoped via Story 1.2's middleware (through the Application relationship)
  - [ ] Accepts `git_host`, `export_mode`, `repo_identifier`, and an access credential — the credential is written via `SecretsClient` immediately, never stored in plaintext (same discipline as AD-5, which literally only names discovery credentials, but NFR-1's "enterprise-grade secret handling" is written generally and obviously extends to any credential this system stores)
  - [ ] `CIConfig` is one row per Application (upsert on resave) — mutual exclusivity of `git_host`/`export_mode` falls out naturally from this shape, not from separate validation logic
- [ ] Task 3: Build the Connect to CI/CD screen's Git host and export mode selection (AC: 1, 2)
  - [ ] Provider cards for Git host (GitHub, GitLab, Azure Repos) — real `<input type="radio">` under a styled card, exactly one selected at a time, selecting a new one deselects the previous (UX-DR11)
  - [ ] Option cards for export mode (PR vs. direct commit) — same control pattern
  - [ ] Repo identifier and credential fields (per Task 1's scope addition) — label the credential field with what kind of access it needs (e.g. a personal access token with repo write/PR-create scope). **A pasted-token (PAT) flow is the pragmatic default used here, not a confirmed design decision** — a full OAuth App / GitHub App installation flow would be the more polished real product experience but is undesigned anywhere in the planning artifacts, and building it now would be substantial unrequested scope beyond what this story asks for. This mirrors how Story 1.4 treated the SSO/session-reuse mechanism: a working placeholder, not a finished design
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Selecting a Git host and export mode and submitting valid repo/credential details persists exactly one `CIConfig` row for the Application
  - [ ] Re-saving with a different host/mode replaces the prior selection cleanly (no orphaned dual-config state)
  - [ ] The stored credential never appears in plaintext in Postgres or logs (reuse Story 1.3's log/column assertion test pattern)

## Dev Notes

- **The `repo_identifier`/credential scope addition is the largest single gap found across all stories spec'd so far** — bigger than the smaller UX-pill/badge gaps in Epic 2/3, because without it Epic 5 literally cannot deliver anything, not just look slightly different than intended. Worth a deliberate product/design confirmation once a working prototype exists, similar in weight to the AI-vendor question already resolved for Story 2.5 — flagging this explicitly to the user outside this story file too.
- **The PAT-based credential flow is a pragmatic default, not a decision anyone signed off on.** If the product later wants a GitHub App / OAuth App integration instead (generally the more secure, higher-trust approach for a SaaS product acting on a customer's repo), that's a meaningfully different build — separate token-exchange endpoints, app installation flow, webhook handling — worth scoping as its own follow-up rather than assuming this story's PAT approach is final.
- **Mutual exclusivity (AC 2) is a data-model consequence, not a rule to separately enforce** — because `CIConfig` is one row per Application, there is structurally no way for both an active PR-mode and an active direct-commit-mode config to coexist. Don't add redundant application-level validation for something the schema already guarantees.

### Project Structure Notes

- Adds `CIConfig` to `packages/domain`, an endpoint to `apps/api`, and the Git-host/export-mode portion of the Connect to CI/CD screen to `apps/web`. No new top-level directories. This is the first story in Epic 5.
- **Depends on Epic 1 (specifically Story 1.2's Organization scoping and Story 1.3's `SecretsClient` pattern) being actually implemented**, not just created — it remains `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.1: Configure Git Host & Export Mode per Application]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-19]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-5, #AD-4 — DeliveryAdapter keyed by Git host, which Story 5.2 will need `repo_identifier`/`secret_ref` for]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — option-card/provider-card]
- [Source: _bmad-output/implementation-artifacts/1-3-onboard-an-application-basic-details.md — the `SecretsClient` credential-handling pattern this story reuses]
- [Source: _bmad-output/implementation-artifacts/1-4-configure-application-authentication-method.md — the "working placeholder, not a finished design" precedent this story's PAT flow follows]

## Previous Story Intelligence

Epics 1-4 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 1.3 is implemented, check its File List for the exact `SecretsClient` adapter/interface shape before reusing it here.

## Latest Technical Notes

No new library decisions — reuses the existing `SecretsClient` adapter (Story 1.3) and FastAPI/SQLModel/React stack.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
