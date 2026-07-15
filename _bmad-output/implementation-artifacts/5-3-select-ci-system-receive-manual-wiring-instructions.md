# Story 5.3: Select CI System & Receive Manual Wiring Instructions

Status: backlog

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

**`[DEFERRED POST-V1 — 2026-07-15]`** The Connect to CI/CD screen this story depends on is cut from the current reference prototype's IA. Do not schedule this story for dev-story until the real delivery/execution mechanism is designed. Retained below verbatim as a record of original intent — historical spec, not a build target. See `_bmad-output/planning-artifacts/sprint-change-proposal-2026-07-15.md`.

## Story

As a user,
I want instructions specific to my CI system for wiring generated tests into my pipeline's test-run step,
so that I can complete the last mile into my real regression process myself.

## Acceptance Criteria

1. **Given** a user selects a CI system (GitHub Actions, GitLab CI, Jenkins, or Azure Pipelines) for their Application, **when** they view the wiring instructions, **then** `CIInstructionsGenerator` renders a template specific to that CI system, independent of which Git host the Application delivers to — e.g., a Jenkins-on-GitHub Application gets the GitHub `DeliveryAdapter` plus Jenkins-flavored instructions. [Source: epics.md#Story 5.3; FR-20; FR-21; architecture#AD-4]
2. The instructions render inside a `<details>` disclosure, closed by default unless it is the first/most-relevant block on the screen. [Source: epics.md#Story 5.3; EXPERIENCE.md#Component Patterns]

## Tasks / Subtasks

- [ ] Task 1: Extend `CIConfig` with `ci_system` (AC: 1)
  - [ ] Add `ci_system` (`"github_actions" | "gitlab_ci" | "jenkins" | "azure_pipelines"`) to `CIConfig` (Story 5.1) — a field entirely independent of `git_host` (AD-4 is explicit that these are two separate selections, never conflated)
  - [ ] Alembic migration
- [ ] Task 2: Implement `CIInstructionsGenerator` with four static templates (AC: 1)
  - [ ] Implement `render(ci_system: Literal["github_actions", "gitlab_ci", "jenkins", "azure_pipelines"]) -> InstructionsTemplate` in `packages/ci_instructions`, exactly per the Module Contracts signature
  - [ ] **This is a pure function of `ci_system` with no dependencies on any other module** (per the Architecture Spine's Module Map — "Depends on: none"), and no AI/vendor SDK involvement at all: the four templates are static content (a representative pipeline-config snippet per CI system showing how to wire the generated Playwright tests into that system's test-run step), not AI-generated. Don't accidentally route this through `HostedAIProvider`/`litellm` — that would violate the module's own stated isolation
  - [ ] Build one template each for GitHub Actions, GitLab CI, Jenkins, and Azure Pipelines
- [ ] Task 3: Build the CI system selection UI (AC: 1, 2)
  - [ ] Add a second provider-card group to the Connect to CI/CD screen, separate from Story 5.1's Git host cards, using the same real-`<input type="radio">` pattern (UX-DR11)
  - [ ] On selection, call `CIInstructionsGenerator` and render the result inside a `<details>` disclosure using the `code-viewer` component's light syntax tinting (`DESIGN.md`)
  - [ ] **This is the only `<details>` disclosure on the Connect to CI/CD screen** (the Git host and CI system selections are option/provider cards, not disclosures) — under the "closed by default except the first/most-relevant block" rule, being the sole disclosure on the screen makes it trivially the most-relevant one, so it should render **open** by default. This is an inferred application of the rule to this specific screen's layout, not a separate explicit citation — flagged in case a future screen redesign adds a competing disclosure that changes this
  - [ ] **Concretely verify the AD-4 independence example from the Architecture Spine itself**: a Jenkins-on-GitHub Application must show Jenkins-flavored wiring instructions here while Story 5.2's actual delivery still uses `GitHubAdapter` — this is literally the example architecture gives, making it a natural, well-specified test case rather than an edge case to guess at
- [ ] Task 4: Verify end-to-end and record evidence (AC: 1, 2)
  - [ ] Selecting each of the four CI systems shows its own distinct template, unaffected by whichever Git host is separately selected
  - [ ] The Jenkins-on-GitHub combination specifically: Jenkins instructions shown here, GitHub delivery actually used by Story 5.2's `CIDeliveryActivity`
  - [ ] The instructions disclosure renders open by default on this screen

## Dev Notes

- **AD-4's independence rule is the one thing most likely to get cross-wired if Stories 5.2 and 5.3 are implemented close together or by different people** — re-read Story 5.2's Dev Notes warning about the same risk from the other direction (Git host selection accidentally branching on CI system) before finishing this story.
- **`CIInstructionsGenerator`'s total isolation (no dependencies, no AI) is worth protecting explicitly in code review** — every other generation-adjacent module in this system (`ScenarioGenerationActivity`, `PlaywrightGenerationActivity`) does call `AIProvider`; this one deliberately doesn't, and that's correct, not an oversight to "fix" by making the instructions AI-tailored.
- **This is the last story in Epic 5** — CI/CD delivery is now fully spec'd across configuration (5.1), delivery (5.2), and instructions (5.3).

### Project Structure Notes

- Extends `CIConfig` (Story 5.1), implements `packages/ci_instructions` (previously a stubbed interface from Story 1.1), and extends the Connect to CI/CD screen (Stories 5.1/5.2). No new top-level directories.
- **Depends on Epic 1-4 and Stories 5.1-5.2 being actually implemented**, not just created — all remain `ready-for-dev` as of this story's creation, and `git log` shows only the initial BMad-tooling commit.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 5.3: Select CI System & Receive Manual Wiring Instructions]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-20, FR-21]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#AD-4, #Module Contracts — CIInstructionsGenerator, #Module Map — CI Instructions row]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/DESIGN.md#Components — code-viewer]
- [Source: _bmad-output/planning-artifacts/ux-designs/ux-AITestGen-2026-07-13/EXPERIENCE.md#Component Patterns — Code disclosure]
- [Source: _bmad-output/implementation-artifacts/5-1-configure-git-host-export-mode-per-application.md; 5-2-deliver-test-assets-via-pull-request-or-direct-commit.md — `CIConfig` and the Git-host/CI-system independence this story completes]

## Previous Story Intelligence

Epics 1-4 and Stories 5.1-5.2 all remain `ready-for-dev`; `git log` shows only the initial BMad-tooling commit. Once Story 5.1 is implemented, check its File List for `CIConfig`'s exact schema before adding `ci_system` alongside `git_host`/`export_mode`.

## Latest Technical Notes

No new library decisions — this story is static template content plus the existing FastAPI/React stack.

## Project Context Reference

No `project-context.md` exists yet in this repository. Epic 5 is now fully spec'd — a strong point to run `bmad-generate-project-context` once Epics 1-5 are implemented, before starting Epic 6.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
