# Story 4.3: Download a Generated Test Suite

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Added 2026-07-27 — reuses the Story 4.3 slot vacated the same day by the cut of the unrelated "Full
Regeneration of Test Assets on Request" story (FR-18). This is a different feature: FR-34, a reviewer-
triggered export of already-generated Test Suites into a downloadable, runnable project. See
`sprint-change-proposal-2026-07-27-2.md`.*

*`[CORRECTED 2026-07-27, same day, during this story's own creation]` The downloaded project is **Python**
(`pytest` + `pytest-playwright`), not Node/TypeScript as the originating brief assumed — `TestAsset.code` is
generated as Python `playwright.sync_api` code (confirmed against `HostedAIProvider.generate_playwright`'s
prompt and the fixture in `test_playwright_generation_activity.py`), and no Python→TypeScript conversion
step exists anywhere in the pipeline. PRD FR-34, `epics.md`, and the Architecture Module Map/Deferred
section were all corrected to match before this story file was written. See the Addendum in
`sprint-change-proposal-2026-07-27-2.md`.*

## Story

As a user,
I want to download all current Test Suites for an Application as a single, ready-to-run Python Playwright
project,
so that I can run the generated tests locally, or fold them into my own regression process, without
hand-assembling a project from copied code.

## Acceptance Criteria

1. **Given** an Application with at least one current (`current=true`) `TestSuite`, **when** the reviewer
   clicks Download on the Test Suites Generated screen (`TestSuiteResults.tsx`), **then** the platform
   assembles a zip containing one folder under `tests/` per current `TestSuite`, named from its Journey,
   each holding one Python test file per current `TestAsset` in that suite (FR-34). [Source: epics.md#Story
   4.3; FR-34; architecture#Module Map — Test Suite Export]
2. The archive also includes a generated `requirements.txt` (`pytest`, `pytest-playwright`), a
   `conftest.py` and/or `pytest.ini` (whichever the verified code shape from Task 1 needs — see Dev Notes),
   empty `fixtures/` and `utils/` scaffold folders, and a `README.md` covering setup and run commands.
   [Source: epics.md#Story 4.3; FR-34]
3. The assembled project is structurally validated before the zip is returned — every current `TestSuite`
   for the Application has a non-empty folder under `tests/`, and every current `TestAsset` in that suite
   has a corresponding file — never a partial or silently-dropped suite/test case. [Source: epics.md#Story
   4.3]
4. After extracting the downloaded zip and running `pip install -r requirements.txt && playwright install`,
   running `pytest` from the project root executes every test across every suite; running
   `pytest tests/<suite-folder>` executes only that suite. [Source: FR-34]
5. This is a synchronous export only — no `TestSuite`/`TestAsset` rows are created, modified, or deleted by
   this action; no Temporal workflow is started; the endpoint only reads `current=true` rows. [Source:
   architecture#Module Map — Test Suite Export]

**`[GAP — flag for verification at implementation time, do not silently assume]`** The exact code shape
`HostedAIProvider.generate_playwright` produces is not confirmed against a real (non-test-double) AI
response — the prompt (`packages/ai_provider/src/ai_provider/hosted.py:129-146`) asks for a `test_...`
function "using `playwright.sync_api`" but does not specify whether it's self-contained (opens its own
`with sync_playwright() as p:` block) or fixture-based (`def test_x(page):`, relying on
`pytest-playwright`'s `page`/`browser` fixtures). This determines whether `conftest.py` needs anything at
all: if self-contained, `pytest-playwright` isn't strictly required (plain `pytest` + `playwright` suffice)
and `conftest.py` can be empty/omitted; if fixture-based, `pytest-playwright` is required and its plugin
auto-registers the fixtures with no `conftest.py` content needed either way. **Action:** generate one real
Test Suite end-to-end (or inspect a few live `TestAsset.code` rows) before finalizing `requirements.txt`
and the `conftest.py`/`pytest.ini` template in Task 2 — do not guess which shape and ship untested
boilerplate.

## Tasks / Subtasks

- [ ] Task 1: Verify the real generated-code shape before building the scaffold template (AC: 2, and the
      `[GAP]` above)
  - [ ] Inspect several real (non-test-double) `TestAsset.code` values — either from an existing seeded
    Application that has gone through Story 4.2's generation, or by running generation once — to confirm
    whether tests are self-contained (`with sync_playwright() as p: ...`) or fixture-based (`def
    test_x(page): ...`)
  - [ ] Decide `requirements.txt`'s exact contents and whether `conftest.py`/`pytest.ini` needs any real
    content, based on this — do not ship a template built on an assumption
- [ ] Task 2: Build the project-assembly module (AC: 1, 2, 3)
  - [ ] New module, e.g. `apps/api/src/api/test_suite_export.py` — a pure function taking the list of
    current `TestSuite` rows (with their journeys) and current `TestAsset` rows, returning an in-memory zip
    (`io.BytesIO` + stdlib `zipfile`, no new dependency)
  - [ ] Suite-folder naming: adapt the existing `toSpecFileName` slug convention (`apps/web/src/components/TestSuiteResults.tsx`)
    to a Python-safe form — lowercase, non-alphanumeric runs collapsed to `-` for the folder name (matching
    what the UI already shows the reviewer for that suite), and to `test_<slug_with_underscores>.py` for
    each test-case file within it (pytest only discovers `test_*.py`/`*_test.py` — the existing hyphenated
    `.spec.ts`-style slug is not itself a legal Python module name and must be adapted, not reused verbatim)
  - [ ] Write each current `TestAsset.code` verbatim into its file — no code transformation, no reformatting
  - [ ] **Collision handling**: two Journeys whose names slugify to the same folder (e.g. "Claim Search!" vs
    "Claim Search?") must not silently overwrite one suite's files with another's — disambiguate by
    appending the `TestSuite`'s own short id/suffix to the folder name on collision (check-as-you-build, not
    a post-hoc fix)
  - [ ] Generate `requirements.txt`, `conftest.py`/`pytest.ini` (per Task 1's finding), empty `fixtures/` and
    `utils/` folders (empty folders need a `.gitkeep`-style placeholder file to survive zipping — `zipfile`
    does not preserve truly empty directories reliably across all unzip tools), and a `README.md` with the
    setup/run commands from AC 4
  - [ ] Validation per AC 3: assert the assembled in-memory structure has one folder per current `TestSuite`
    passed in and one file per current `TestAsset` in that suite before zipping — raise/500 rather than
    return a silently incomplete archive if the counts don't match what was queried
- [ ] Task 3: Add the download endpoint (AC: 1, 4, 5)
  - [ ] `GET /applications/{external_id}/test-suites/download` in `apps/api/src/api/main.py`, alongside the
    existing `list_test_suites` endpoint (`main.py:787`) — reuse its exact same query shape (candidate
    Journeys → current `TestSuite`s → current `TestAsset`s) rather than re-deriving it, then pass the
    results to Task 2's assembly function
  - [ ] **`[CRITICAL — AD-12 tenant isolation]`** Must resolve the Application via `_get_org_application(session,
    organization_id, external_id)` — the same org-scoped lookup `list_test_suites` already uses — never by
    `external_id` alone. Every query in `apps/api` is Organization-scoped (architecture AD-12, Tenancy
    module); skipping this would let one Organization download another's generated tests
  - [ ] Return `Response(content=<zip bytes>, media_type="application/zip", headers={"Content-Disposition":
    'attachment; filename="<application-slug>-tests.zip"'})` — a plain synchronous `Response` (already
    imported in `main.py`) is sufficient at this size; no `StreamingResponse` needed
  - [ ] No new Postgres writes, no Temporal workflow dispatch — purely additive, read-only endpoint
- [ ] Task 4: Add the Download control to the Test Suites Generated screen (AC: 1)
  - [ ] `apps/web/src/api.ts`: add a dedicated function (e.g. `downloadTestSuiteProject(applicationId)`) that
    does **not** go through the existing generic `request<T>()` helper (`api.ts:24`) — that helper always
    calls `.json()` on the response, which fails on a binary zip. Fetch directly, read `.blob()`, then
    trigger a browser download via `URL.createObjectURL` + a temporary `<a download>` click + `URL.revokeObjectURL`
    cleanup
  - [ ] `apps/web/src/components/TestSuiteResults.tsx`: add a "Download Test Suite" button in the completed
    (`isComplete`) view, near the existing "Go to Dashboard →" button — disable it while the download
    request is in flight, mirroring `GenerateSuite.tsx`'s existing `generating` boolean-disable pattern
- [ ] Task 5: Verify end-to-end and record evidence (AC: 1-5)
  - [ ] Downloading for an Application with N current Test Suites (M total current Test Assets across them)
    produces a zip with exactly N folders under `tests/` and exactly M test files total
  - [ ] Extracting the zip and running `pip install -r requirements.txt && playwright install` succeeds; `pytest`
    from the project root discovers and attempts every test; `pytest tests/<suite-folder>` runs only that
    suite's tests
  - [ ] Downloading twice in a row (no new generation in between) produces byte-for-byte-equivalent test
    content both times (same current rows, same deterministic assembly) — confirms no hidden non-determinism
    (e.g. dict/set ordering) in the assembly step
  - [ ] Confirm the endpoint issues zero writes to Postgres and starts zero Temporal workflows (AC 5)
  - [ ] An Application with a current `TestSuite` that has zero current `TestAsset`s (edge case — shouldn't
    occur per Story 4.2's own generation flow, but don't assume) either gets an empty-but-present folder or
    is excluded — decide and document which, don't leave it undefined behavior

## Dev Notes

- **This is a new, isolated module (`Test Suite Export`, architecture Module Map) — read-only over
  `TestSuite`/`TestAsset`.** It must not touch `PlaywrightGenerationActivity`, `SuiteGenerationWorkflow`, or
  `TestAsset.code` generation in any way. If a project-scaffold detail needs to change later (e.g. a
  different `conftest.py` default), that change is isolated entirely to this module.
- **Do not build a Node/TypeScript scaffold.** This was the original (incorrect) draft of FR-34/Story 4.3,
  based on the requesting brief before the actual generated-code language was checked. `TestAsset.code` is
  Python. See the `[CORRECTED]` note at the top of this file and the Addendum in
  `sprint-change-proposal-2026-07-27-2.md` for the full discovery. If a future story wants a genuine
  TypeScript export, that requires a new Python→TypeScript (or a parallel TS-generation) capability — not a
  packaging change here.
- **Reuse `list_test_suites`'s exact query shape** (`main.py:787-855`) for finding current Journeys → current
  `TestSuite`s → current `TestAsset`s — don't re-derive the candidate-Journey/`current=true` filtering
  logic a second, possibly-divergent way.
- **`toSpecFileName`'s slug (`TestSuiteResults.tsx`) is not directly reusable as a Python module name** —
  it's hyphenated and suffixed `.spec.ts`. Adapt the *slugification logic* (lowercase, collapse
  non-alphanumeric runs), not the literal function, and apply Python's `test_*.py` naming rule on top.
- **Zip assembly must be deterministic** — iterate suites/test-assets in a stable order (e.g. by `id` or by
  the same order the existing `list_test_suites` query already returns them in) so two downloads of
  unchanged data produce byte-identical output. Don't rely on dict/set iteration order incidentally being
  stable.
- **No new pip/uv dependency for the zip itself** — `zipfile` and `io.BytesIO` are stdlib; only the
  *generated project's own* `requirements.txt` lists `pytest`/`pytest-playwright` (those are what the
  *downloaded* project needs, not `apps/api` itself).
- **The frontend's generic `request<T>()` helper cannot be reused for this call** — it unconditionally
  calls `response.json()` (`api.ts:24-36`), which throws on a binary body. This needs its own fetch +
  `.blob()` + object-URL-download function, matching how most browser download-a-file flows work; there is
  no existing precedent for this in the codebase (Story 4.3 is the first "download a file" feature), so this
  is new code, not a pattern extension.

### Project Structure Notes

- New file: `apps/api/src/api/test_suite_export.py` (assembly logic — pure, easily unit-testable without a
  running Postgres).
- Updated: `apps/api/src/api/main.py` (new endpoint, Task 3).
- Updated: `apps/web/src/api.ts` (new download function), `apps/web/src/components/TestSuiteResults.tsx`
  (new button).
- New tests: `apps/api/tests/test_test_suite_export.py` (endpoint + assembly), extend
  `apps/web/src/components/TestSuiteResults.test.tsx` (Download button behavior).
- No `packages/domain` changes, no Alembic migration — this story reads existing `TestSuite`/`TestAsset`
  rows only; no new columns or tables.
- No `packages/workflows` or `apps/workers/generation` changes — no Temporal workflow is involved.

### Testing Requirements

- **Backend**: follow `apps/api/tests/test_test_suite_generation.py`'s existing skip-cleanly convention
  (`pytestmark = pytest.mark.skipif(not (_db_available() and ...))`) for the endpoint test — seed
  `TestSuite`/`TestAsset` rows directly (same pattern that file already uses), call the new endpoint via
  `TestClient`, and assert on the zip's contents (open the response bytes with stdlib `zipfile.ZipFile` and
  check its namelist/contents) rather than just the response status. Unit-test `test_suite_export.py`'s
  assembly function directly and separately, without needing a database at all — it's a pure function over
  in-memory rows.
- **Frontend**: `TestSuiteResults.test.tsx` currently stubs `fetch` to return `{ ok, status, json }` — the
  Download button's test needs a mock that instead returns a `blob()` method (e.g.
  `{ ok: true, status: 200, blob: async () => new Blob(['...']) }`), and should also stub
  `URL.createObjectURL`/`URL.revokeObjectURL` (not implemented in the jsdom/vitest test environment by
  default) to assert the download was triggered without actually needing a real Blob URL.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3: Download a Generated Test Suite]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-34]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Module Map — Test Suite Export, #Deferred — Test Suite Export is not CI Delivery / No Python→TypeScript conversion]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-27-2.md — full change history and the language-correction addendum]
- [Source: apps/api/src/api/main.py:787-855 — `list_test_suites`, the exact query shape to reuse for finding current suites/assets]
- [Source: apps/web/src/components/TestSuiteResults.tsx — `toSpecFileName`, the existing slug convention to adapt; the screen this story adds a button to]
- [Source: apps/web/src/api.ts:24-36 — `request<T>()`, the generic JSON helper this story's download call must NOT use]
- [Source: packages/ai_provider/src/ai_provider/hosted.py:129-146 — `_PLAYWRIGHT_PROMPT`, confirms generated code is Python `playwright.sync_api`]
- [Source: apps/workers/generation/tests/test_playwright_generation_activity.py:247 — confirms `TestAsset.code`'s actual Python shape in a real assertion]
- [Source: packages/domain/src/domain/test_asset.py, packages/domain/src/domain/test_suite.py — `TestAsset`/`TestSuite` schemas this story reads, unmodified]
- [Source: _bmad-output/implementation-artifacts/4-2-generate-playwright-test-assets-from-scenarios.md — Story 4.2, the story that produces the rows this one exports; confirms `TestAsset` has no `generation_run_id` of its own (derive via `test_suite_id`) if that's ever needed for display]

## Previous Story Intelligence

Story 4.2 (`4-2-generate-playwright-test-assets-from-scenarios.md`) is the direct predecessor and producer of
the data this story exports. Its own Dev Agent Record File List is empty in that file (never filled in
despite the feature being implemented — see `sprint-change-proposal-2026-07-27.md`'s finding that commit
`6df2663` implemented it under a mislabeled "4.3 has been completed" message), so this story's file-location
guidance above was derived directly from that commit's actual diff (`git show --stat 6df2663`), not from
Story 4.2's own (unfilled) documentation:
`apps/api/src/api/main.py`, `apps/web/src/api.ts`, `apps/web/src/api-types.gen.ts`,
`apps/web/src/components/{GenerateSuite,TestSuiteResults}.tsx` (+ `.test.tsx`),
`apps/workers/generation/src/generation_worker/activities.py`,
`packages/ai_provider/src/ai_provider/{__init__.py,hosted.py,test_asset_code.py}`,
`packages/domain/src/domain/{test_asset.py,test_suite.py}`,
`packages/workflows/src/workflows/{__init__.py,suite_generation_workflow.py}`. This story's own new files
(Task 2/3/4) slot into that same existing layout — no new top-level directory.

Key carried-forward facts from Story 4.2 relevant here: `TestAsset` has no `generation_run_id` field of its
own (always derive via `test_suite_id` → `TestSuite.generation_run_id`); `TestSuite.name` is auto-derived
from its Journey's name, not manually entered; both `TestSuite`/`TestAsset` use the `current: bool` flag
convention this story must filter on (`current=true` only, matching `list_test_suites`'s own filtering).

## Latest Technical Notes

No new external dependency for `apps/api` itself (stdlib `zipfile`/`io`). The *generated project's own*
`requirements.txt` should pin reasonably current versions of `pytest` and `pytest-playwright` at
implementation time — check PyPI for their current stable versions rather than hardcoding versions from
this story's own authoring date, since this file may be implemented well after being written.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-27 — Story created via `bmad-create-story`, following `sprint-change-proposal-2026-07-27-2.md`
  (Story 4.3, FR-34 added to Epic 4). During creation, discovered and corrected a language mismatch: the
  requesting brief assumed a Node/TypeScript project, but `TestAsset.code` is generated as Python — PRD,
  epics, and architecture were corrected in the same pass (see the Addendum in the sprint change proposal)
  before this file was written. Flagged one unresolved `[GAP]` (Task 1) — the exact self-contained-vs-
  fixture-based shape of AI-generated Playwright code is not yet confirmed against a real (non-test-double)
  sample, and must be checked before the `requirements.txt`/`conftest.py` template is finalized.

## Dev Agent Record

### Agent Model Used

_To be filled by the Dev Agent during implementation._

### Debug Log References

### Completion Notes List

### File List
