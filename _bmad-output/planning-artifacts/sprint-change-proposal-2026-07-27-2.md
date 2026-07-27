# Sprint Change Proposal — 2026-07-27 (follow-up)

## Add Story 4.3: Download a Generated Test Suite (new FR-34) — reuses the slot vacated by today's earlier cut

## 1. Issue Summary

Same day as `sprint-change-proposal-2026-07-27.md` cut the original Story 4.3 (Full Regeneration on
Request, FR-18), Harsha requested a **new**, unrelated capability for Epic 4: letting a reviewer download
the generated Playwright coverage for an Application as a real, runnable project — not just view code in a
modal (the current state of `TestSuiteResults.tsx`).

**Problem type:** new requirement emerging from stakeholder input, not a technical limitation or a
misunderstanding of existing scope. **Evidence:** `TestAsset.code` (`packages/domain/src/domain/test_asset.py`)
already holds each test's full Playwright source; `GET /applications/{id}/test-suites`
(`apps/api/src/api/main.py:787`) already returns every current suite + test case code for an Application;
`TestSuiteResults.tsx` only renders it read-only in a `<pre>` modal. No download/export endpoint or UI
control exists in `apps/api` or `apps/web` today.

The requested shape (refined via an updated brief from Harsha): a single **Download** action that produces
a complete Playwright project, with generated tests organized into **suite-level folders** under `tests/`
(one folder per current Test Suite, named after its Journey), plus a generated `playwright.config.ts`,
`package.json`, `tsconfig.json`, empty `fixtures/`/`utils/` scaffold folders, and a `README.md` — runnable via
`npm install && npx playwright install && npx playwright test`, or per-suite via
`npx playwright test tests/<suite-folder>`.

## 2. Impact Analysis

### Epic Impact
- **Epic 4 (Scenario & Playwright Test Generation)**: gains a third story, **Story 4.3: Download a Generated
  Test Suite**, reusing the numbering slot the original (unrelated) Story 4.3 vacated earlier today. Epic 4's
  description gains a line about the download capability. No other epic depends on it, no resequencing.
- **No epic becomes obsolete, no new epic needed.**

### Artifact Conflicts
- **PRD**: new **FR-34** added to §4.5, explicitly scoped as an export (not a CI/CD delivery mechanism —
  distinguished from the still-cut FR-19–21). §6.1 MVP Scope bullet gains a clause. §9 Assumptions Index gets
  a dated entry.
- **Architecture**: `binds:` gains FR-34. New Module Map row, **Test Suite Export** (`apps/api`, new
  synchronous download endpoint) — read-only over existing `TestSuite`/`TestAsset` rows (`current=true`
  only), same isolation shape as Analytics (no write path into the Trusted Knowledge Model). Deferred section
  gains a note explicitly distinguishing this from the removed CI Delivery module, so a future reader doesn't
  conflate "export a zip to the browser" with "push to a customer's Git host."
- **UX (DESIGN.md/EXPERIENCE.md)**: checked — no conflict. The post-generation screen
  (`TestSuiteResults.tsx`) was **never actually reached during UX review**; both docs already flag it
  `[GAP]`. This change adds to an already-open gap rather than overwriting a documented decision.
- **Other artifacts**: no deployment/IaC/CI/CD/monitoring impact — this is a synchronous, read-only export
  with no customer-infra touchpoint.

### Code Impact
No code exists yet for this story — it is net-new. Implementation (left to Story 4.3's own dev pass, not
this proposal) will need: a new `apps/api` endpoint that reads current `TestSuite`/`TestAsset` rows for an
Application, assembles the `tests/<suite-folder>/<spec>.spec.ts` layout plus the generated scaffold files,
validates the assembled structure, zips it, and streams it back; a "Download" control on
`TestSuiteResults.tsx`. It should reuse the existing `toSpecFileName` slug helper already in that file for
both the spec filename and (one level up) the suite folder name.

## 3. Recommended Approach

**Option 1 (Direct Adjustment)** — add the story and its FR within the existing Epic 4 structure.
**Effort: Low. Risk: Low.** Purely additive; no rollback question, no MVP-scope question (Epic 4 already
ships 4.1+4.2 regardless of this addition).

**Option 2 (Rollback)** — not applicable, nothing to roll back.

**Option 3 (MVP Review)** — not applicable, doesn't threaten or require redefining MVP.

**Selected: Option 1, direct adjustment.** Scope classification: **Minor** — implementable directly, no
backlog reorganization, no architect/PM escalation.

## 4. Detailed Change Proposals

All doc edits below have been applied.

### PRD (`prds/prd-AITestGen-2026-07-13/prd.md`)
- §4.5: added **FR-34** (Download generated Test Suite as a Playwright project) after FR-29 — full text
  covers suite-folder structure, scaffold files, and explicit non-goals (no per-suite-only download, no
  server-side execution, no Git/CI delivery, no auth wiring in the scaffold).
- §6.1 MVP Scope: FR-16/FR-29 bullet gains a clause referencing FR-34.
- §9 Assumptions Index: new dated entry recording the addition and cross-referencing this document.

### Epics (`epics.md`)
- Frontmatter changelog: new dated follow-up entry.
- FR Coverage Map: new `FR-34` line.
- Epic 4 summary (Epic List) and full Epic 4 section: both description lines updated to mention the download
  capability.
- New `### Story 4.3: Download a Generated Test Suite` section added (story text, ACs, an ENG note on reusing
  `toSpecFileName`), placed after the historical note about the earlier (unrelated) Story 4.3 cut.

### Architecture (`ARCHITECTURE-SPINE.md`)
- `binds:` gains FR-34.
- New Module Map row: **Test Suite Export**.
- Deferred section: new note distinguishing Test Suite Export from the removed CI Delivery module.

### Sprint status (`implementation-artifacts/sprint-status.yaml`)
- New entry under `epic-4`: `4-3-download-a-generated-test-suite: backlog`, with a comment cross-referencing
  this proposal and flagging that the story file itself still needs to be created.
- `last_updated` comment block gains a same-day follow-up line.

### Story file
Not created by this proposal — per BMad convention, Correct Course updates the plan (PRD/epics/architecture/
sprint-status); materializing the actual story file is `bmad-create-story`'s job, run next.

## 5. Implementation Handoff

**Scope: Minor.** No backlog reorganization, no PM/Architect escalation. All doc edits above are applied.
Next step: run `bmad-create-story` for Story 4.3 to materialize the story file, then proceed to `bmad-dev-story`.

## 6. Success Criteria

- FR-34 and Story 4.3 (Download) appear consistently across `epics.md`, `sprint-status.yaml`
  (`backlog`), and the PRD's in-scope sections (§4.5, §6.1).
- Architecture Module Map has a `Test Suite Export` row scoped to FR-34, and the Deferred section clearly
  distinguishes it from the removed CI Delivery module.
- No artifact conflates this export capability with CI/CD delivery (still cut) or with the unrelated,
  same-day-cut regeneration feature (former FR-18).

## 7. Addendum — Language Correction (during `bmad-create-story`)

While materializing Story 4.3's story file, discovered that `TestAsset.code` is generated as **Python**
(`playwright.sync_api`) by `HostedAIProvider.generate_playwright`'s prompt
(`packages/ai_provider/src/ai_provider/hosted.py:129-146`) — confirmed against
`apps/workers/generation/tests/test_playwright_generation_activity.py`'s fixture
(`test_asset.code == "def test_guest_checkout():\n    pass\n"`). No Python→TypeScript conversion step
exists anywhere in the pipeline. The original draft above (and Harsha's requesting brief) assumed a
Node/TypeScript project (`package.json`, `playwright.config.ts`, `tsconfig.json`, `npx playwright test`) —
wrapping that scaffold around Python function bodies would produce a project that cannot run.

**Corrected, with Harsha's explicit confirmation**: the downloaded project is Python
(`requirements.txt` with `pytest`/`pytest-playwright`, `conftest.py`/`pytest.ini`, `pytest`/
`pytest tests/<suite-folder>` to run). PRD FR-34, `epics.md` Story 4.3, and the Architecture Module Map row
+ a new Deferred-section note have all been updated to match. No other part of this proposal changes.
