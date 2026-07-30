# Story 4.3: Download a Generated Test Suite

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

*Added 2026-07-27 — reuses the Story 4.3 slot vacated the same day by the cut of the unrelated "Full
Regeneration of Test Assets on Request" story (FR-18). This is a different feature: FR-34, a reviewer-
triggered export of already-generated Test Suites into a downloadable, runnable project. See
`sprint-change-proposal-2026-07-27-2.md`.*

*`[CORRECTED 2026-07-27, same day, during this story's own creation]` The downloaded project was **Python**
(`pytest` + `pytest-playwright`), not Node/TypeScript as the originating brief assumed — `TestAsset.code` was
generated as Python `playwright.sync_api` code at the time.*

*`[CORRECTED 2026-07-29, reverses the entry above]` `HostedAIProvider.generate_playwright` now generates
**TypeScript** (`@playwright/test`), by explicit decision. The downloaded project is an npm-based
`@playwright/test` project, not Python — see `packages/ai_provider/src/ai_provider/hosted.py:129-146`
(`_PLAYWRIGHT_PROMPT`) and ARCHITECTURE-SPINE.md's matching correction. This story's Tasks/Dev Notes below
are updated to the TypeScript scaffold; the 2026-07-27 Python note above is retained only as history.*

*`[ENHANCED 2026-07-30]` Security, filename-safety, and determinism guarantees — previously implied only by
Dev Notes and Task 5 verification bullets — are now first-class Acceptance Criteria (AC5-7 below), and AC4's
CI-runnability wording is made explicit. No new functional scope: still a synchronous, read-only export with
no CI-config generation and no git integration (architecture spine's "not CI Delivery" boundary unchanged).*

## Story

As a user,
I want to download all current Test Suites for an Application as a single, ready-to-run TypeScript Playwright
project — pre-configured with the Application's base URL and an authentication setup that matches how the
Application was onboarded,
so that I can run the generated tests locally, or fold them into my own regression process or CI pipeline,
standalone, without hand-assembling a project from copied code or hand-wiring authentication myself.

## Acceptance Criteria

1. **Given** an Application with at least one current (`current=true`) `TestSuite`, **when** the reviewer
   clicks Download on the Test Suites Generated screen (`TestSuiteResults.tsx`), **then** the platform
   assembles a zip containing one folder under `tests/` per current `TestSuite`, named from its Journey,
   each holding one TypeScript test file per current `TestAsset` in that suite (FR-34). [Source: epics.md#Story
   4.3; FR-34; architecture#Module Map — Test Suite Export]
2. The archive also includes a generated `package.json` (`@playwright/test` dependency) and
   `playwright.config.ts` (whichever the verified code shape from Task 1 needs — see Dev Notes),
   empty `fixtures/` and `utils/` scaffold folders, and a `README.md` covering setup and run commands.
   [Source: epics.md#Story 4.3; FR-34]
3. The assembled project is structurally validated before the zip is returned — every current `TestSuite`
   for the Application has a non-empty folder under `tests/`, and every current `TestAsset` in that suite
   has a corresponding file — never a partial or silently-dropped suite/test case. If this validation (or
   zip generation itself) fails for any reason, see AC 9 — the failure path is a first-class requirement,
   not just an inference from this AC's success path. [Source: epics.md#Story 4.3]
4. After extracting the downloaded zip, it runs unmodified in any standard CI runner as well as locally:
   `npm install && npx playwright install` (or `npm ci && npx playwright install --with-deps` in CI) followed
   by `npx playwright test` executes every test across every suite, and `npx playwright test
   tests/<suite-folder>` executes only that suite — no CI-specific config file, secrets wiring, or manual
   editing required to make it runnable in a pipeline. [Source: FR-34]
5. This is a synchronous export only — no `TestSuite`/`TestAsset` rows are created, modified, or deleted by
   this action; no Temporal workflow is started; the endpoint only reads `current=true` rows. [Source:
   architecture#Module Map — Test Suite Export]
6. **`[ENHANCED 2026-07-30]`** The download endpoint only ever returns Test Suites belonging to the caller's
   own Organization, reusing the same org-scoped Application lookup every other endpoint in `apps/api` uses
   (AD-12) — attempting to download another Organization's Application's tests behaves identically to any
   other cross-org access (not found), never a data leak. [Source: architecture#AD-12 Tenancy]
7. **`[ENHANCED 2026-07-30]`** Every folder/file name written into the archive is produced by a sanitizer
   that: (a) never emits a path-traversal segment (`..`, `/`, `\`) that could enable zip-slip on extraction,
   (b) disambiguates two distinct Journeys that would otherwise slug to the same folder name (suffix on
   collision — already-existing behavior), (c) never emits a bare Windows-reserved device name (`CON`, `NUL`,
   `AUX`, `PRN`, `COM1`-`COM9`, `LPT1`-`LPT9`) or an empty string as a folder/file name, falling back to a
   safe default instead.
8. **`[ENHANCED 2026-07-30]`** Downloading twice in a row with no intervening generation produces a
   byte-identical zip — the assembled archive is fully deterministic given unchanged underlying data.
9. **`[ENHANCED 2026-07-30]`** If zip assembly or the AC 3 structural validation fails for any reason (e.g.
   a suite/asset count mismatch, an I/O or zip-library error), the endpoint returns a clear error response
   (non-2xx, with a message identifying the failure) and never returns a partially-generated archive — a
   failed export must be unambiguous to the caller, not a zip file that silently omits or truncates content.
10. **`[ENHANCED 2026-07-30]`** On success, the response has `Content-Type: application/zip` and a
    `Content-Disposition: attachment; filename="<name>.zip"` header, where `<name>` is derived from the
    Application's name/slug through the same sanitizer discipline as AC 7 (safe characters only, no
    path-traversal segments, never empty) so every browser downloads the archive as a file, correctly named,
    rather than attempting to render or misname it.
11. **`[ENHANCED 2026-07-30]`** The generated `playwright.config.ts` sets `use.baseURL` to the exported
    Application's own `url` (Story 1.3's `Application.url` field), so every AI-generated test that navigates
    with a relative path works standalone with no manual `baseURL` edit.
12. **`[ENHANCED 2026-07-30]`** The generated project includes a Playwright authentication **setup project**
    (Playwright's documented `dependencies`/`storageState` pattern: a `setup` project that runs first and
    saves a `storageState` file, with every test-running project declaring `dependencies: ['setup']` and
    `use.storageState` pointing at that file) that establishes an authenticated browser context before any
    generated test runs — covering whichever of the Application's two configured `auth_method` values
    (Story 1.4: `standard_login` or `sso_session_reuse`) applies, with **zero changes to any AI-generated
    `TestAsset.code` file**. Which branch is generated is decided once at export time from the Application's
    own `auth_method`; the AI-generated test files never know or care which one is in effect.
    - For `standard_login`: the generated setup script (`auth.setup.ts`) reuses the login page's URL, form
      fields, and selectors already captured by the discovery process during Application onboarding (Epic 2
      Application Model) — it reads credentials from environment variables at runtime, performs the login
      using those captured selectors, and saves the resulting `storageState`. Neither the selectors nor the
      credentials are generated by AI; the selectors are exported as data (not a secret), the credentials
      are never exported at all.
    - For `sso_session_reuse`: the generated setup script materializes a runtime-supplied `storageState`
      (no login attempted, no captured selectors needed).
13. **`[ENHANCED 2026-07-30]`** No authentication *credential* or *session-state* content is ever embedded in
    the exported zip, in either auth branch — that is the one thing that must always come from the user at
    runtime. (Captured login-page selectors/URL for `standard_login`, per AC 12, are data describing *where*
    to log in, not a secret, and are exported deliberately — this distinction is intentional, not an
    oversight.) The setup project and `playwright.config.ts` reference environment variables (for
    `standard_login` credentials) or a runtime-supplied session-state file/variable (for `sso_session_reuse`)
    — documented in the generated `README.md` (extends AC 2) — never the literal Vault-stored secret value.
    The export process itself never calls `SecretsClient`/reads the Vault secret at all; it reads the
    Application's own `auth_method` (non-secret) plus, for `standard_login` only, the Application Model's
    captured login-page evidence (also non-secret) to pick and populate the right template.

**`[RESOLVED 2026-07-30]`** The `standard_login` setup script's login mechanism is confirmed: it **reuses the
login page information (URL, form fields, and selectors) already captured by the discovery process during
Application onboarding** (Epic 2's Application Model) — not selector hints supplied via extra env vars, and
not anything AI-generated or invented at export time. The setup script reads only the runtime-supplied
credentials (username/password) from environment variables, drives the login using those captured selectors,
and saves the resulting `storageState`. No selectors or credentials are ever generated by AI or embedded in
the exported project — the captured login-page structure (URL/fields/selectors) is data, not a secret, so
embedding *that* (not the credential values) in the generated `auth.setup.ts` is acceptable and necessary
for the script to function without user-supplied selector configuration. This **does cross** the `Test Suite
Export` module's previously-stated "read-only over `TestSuite`/`TestAsset` only" isolation boundary — the
module must now also read the Application Model's captured login-page evidence for Applications configured
with `auth_method="standard_login"`. That boundary widening is accepted as part of this enhancement, not a
follow-up decision. The `sso_session_reuse` branch has no such mechanism to resolve — it never performs a
login, only materializes a runtime-supplied `storageState` file to the path the `setup` project's dependents
expect.

**`[PARTIALLY RESOLVED 2026-07-30]`** The exact code shape `HostedAIProvider.generate_playwright` produces
against a *real* (non-test-double, live LiteLLM) AI response is still not confirmed — that would require a
live AI provider call, out of reach in this session. What **is** now confirmed, via a genuine end-to-end run
(extract the real downloaded zip, `npm install`, `npx playwright install`, `npx playwright test` against a
real local HTTP fixture server — see Dev Agent Record): a hand-written test matching the prompt's own stated
shape exactly (`import { test, expect } from '@playwright/test'`, a single `test(...)` block, relative
`page.goto()` paths, no in-test login) runs correctly end-to-end against the generated `playwright.config.ts`
(`baseURL` + `storageState` wiring) with zero modification. The scaffold's compatibility with that documented
shape is proven; only finer AI stylistic variance (e.g. `test.describe` wrapping) remains unconfirmed against
a real AI response — low risk, since the scaffold makes no assumption beyond "a standard `@playwright/test`
file using the shared `baseURL`/`storageState`."

## Tasks / Subtasks

- [x] Task 1: Verify the real generated-code shape before building the scaffold template (AC: 2, 11, 12, and
      the `[GAP]` notes above)
  - [x] Inspected the only available shape (`test_playwright_generation_activity.py`'s test-double fixture
    and the `_PLAYWRIGHT_PROMPT` wording itself — no live AI provider available in this session, so the
    `TestAsset.code`-shape item stays a `[PARTIALLY RESOLVED]` note, not a full close): fully self-contained
    `import { test, expect } from '@playwright/test'` + one `test(...)` block, relative navigation, no
    in-test login. Proved compatibility end-to-end with a hand-written test matching that exact shape.
  - [x] Confirmed (by inspecting `_PLAYWRIGHT_PROMPT`, `hosted.py:129-146`, and the only real fixture
    available) that generated tests are not documented or observed to perform their own login — AC 12's
    "zero changes to AI-generated code" precondition holds for every shape actually seen.
  - [x] Confirmed via direct schema inspection: no `page_type`/`is_login` flag exists anywhere in the
    Application Model. The mechanism is: the captured `Form` with a `FormField.input_type == "password"` is
    the login form; its `Page.url` is the login URL; the other `FormField` (`input_type` `email`/`text`) in
    that `Form` is the username field — implemented in `find_login_page_evidence`
    (`apps/api/src/api/test_suite_export.py`). Verified for real: seeded genuine `Page`/`Form`/`FormField`
    rows shaped exactly like Discovery's own `establish_session` capture, then ran the real download →
    extract → `npm install` → `npx playwright test` and confirmed the setup script logged in successfully
    using those captured selectors.
  - [x] `package.json` pins `@playwright/test: ^1.48.0`; `playwright.config.ts` sets `baseURL` + a
    `setup`/`storageState`-dependent `chromium` project (Playwright's own documented auth pattern) — not
    built on an assumption, proven by two full real `npx playwright test` runs (see Dev Agent Record).
- [x] Task 2: Build the project-assembly module (AC: 1, 2, 3, 7, 8, 9, 11, 12, 13)
  - [x] `apps/api/src/api/test_suite_export.py` — `assemble_test_suite_project`, a pure function over
    `TestSuite`/`TestAsset` rows plus `LoginPageEvidence`, returning zip bytes (`io.BytesIO` + stdlib
    `zipfile`, no new dependency)
  - [x] Suite-folder naming built on `toTestFileName`'s convention (`sanitize_slug`), and each test-case
    file's own name is derived from its Scenario's name via the same convention, deduped within its folder
  - [x] `sanitize_slug` extends the alphanumeric whitelist with deliberate, unit-tested guards (AC 7):
    Windows-reserved-device-name fallback, empty-slug fallback; the whitelist itself already makes zip-slip
    structurally impossible (no `/`, `\`, `.` survives it) — confirmed by dedicated unit tests
  - [x] Each current `TestAsset.code` written verbatim — no transformation, no reformatting
  - [x] **Collision handling** implemented via `dedupe_slugs` (suffixes the second+ colliding slug with the
    id's short form) — unit-tested with two Journeys that slug identically
  - [x] Generates `package.json`, `playwright.config.ts`, `fixtures/.gitkeep`, `utils/.gitkeep`,
    `tests/auth.setup.ts`, and `README.md` with real setup/run commands
  - [x] Validation per AC 3: asserts written suite-folder/test-file counts match the queried input; raises
    `TestSuiteExportError` (never returns a silently incomplete archive) if they don't
  - [x] Fail-closed per AC 9: every assembly/zip-writing path is wrapped so any failure raises
    `TestSuiteExportError` — the endpoint (Task 3) catches this and returns `500`, never a partial zip
  - [x] Deterministic per AC 8: suites/assets sorted by `id` before writing — verified by a unit test that
    calls `assemble_test_suite_project` twice with identical input and asserts byte-identical output, and
    again for real via two live downloads in a row (`test_downloading_twice_is_byte_identical`)
  - [x] Sanitizer unit-tested directly: empty name, reserved device name, two colliding names, path-
    traversal characters (`../`, `..\`, embedded `/`) — none produce an unsafe or empty zip entry path
  - [x] Reads only `Application.url`/`auth_method` (no `SecretsClient`/Vault call) to template `baseURL` and
    the `setup`/`storageState` project wiring (AC 11, 12)
  - [x] `_build_auth_setup_script` branches by `auth_method`: `sso_session_reuse` writes a runtime-supplied
    `storageState` with no login attempted; `standard_login` uses `find_login_page_evidence`'s captured
    selectors (falling back to the same generic selectors `discovery_worker.session.attempt_login` already
    uses live, when Discovery captured nothing) and reads credentials only from
    `AITESTGEN_LOGIN_USERNAME`/`AITESTGEN_LOGIN_PASSWORD` env vars, then persists `storageState` (AC 12, 13)
  - [x] No literal credential/session-state value or `SecretsClient` reference is ever written into any
    generated file — asserted directly in unit tests and by grepping the real, fully-assembled zip's every
    file in both live end-to-end runs (AC 13)
- [x] Task 3: Add the download endpoint (AC: 1, 4, 5, 6, 9, 10)
  - [x] `GET /applications/{external_id}/test-suites/download` added in `apps/api/src/api/main.py`, reusing
    `list_test_suites`'s exact query shape (candidate Journeys → current `TestSuite`s → current
    `TestAsset`s), then passing the results to Task 2's assembly function
  - [x] **`[CRITICAL — AD-12 tenant isolation, AC 6]`** Resolves the Application via `_get_org_application`
    — never by `external_id` alone. `test_download_is_organization_scoped` (real DB) confirms a cross-org
    download attempt gets the same 404 as a not-found Application.
  - [x] Returns `Response(content=<zip bytes>, media_type="application/zip", headers={"Content-Disposition":
    'attachment; filename="<sanitized-application-name>-tests.zip"'})` — plain synchronous `Response`
  - [x] Per AC 10: `media_type="application/zip"` set explicitly; the filename is run through
    `sanitize_slug` before going into `Content-Disposition` — verified via `test_download_returns_a_valid_
    zip_with_correct_headers`
  - [x] Zero new Postgres writes, zero Temporal workflow dispatch in the endpoint itself — confirmed by code
    inspection (no `session.add`/`commit`/`start_workflow` calls anywhere in the handler or Task 2's module)
  - [x] Catches `TestSuiteExportError` (AC 9) and returns `500` with a descriptive detail — never a `200`
    with partial/corrupt zip bytes; unit-tested directly against the assembly function
- [x] Task 4: Add the Download control to the Test Suites Generated screen (AC: 1)
  - [x] `apps/web/src/api.ts`: added `downloadTestSuiteProject(applicationId)` — does not use the generic
    `request<T>()` helper; fetches directly, reads `.blob()`, triggers download via `URL.createObjectURL` +
    a temporary `<a download>` click + `URL.revokeObjectURL` cleanup, reading the real filename back out of
    the `Content-Disposition` response header
  - [x] `apps/web/src/components/TestSuiteResults.tsx`: the existing disabled "Download Test Suite" button
    is now wired to `handleDownload`, disabled only while the request is in flight (mirrors
    `GenerateSuite.tsx`'s `generating` pattern), re-enabling on either success or failure
- [x] Task 5: Verify end-to-end and record evidence (AC: 1-13)
  - [x] `test_download_returns_a_valid_zip_with_correct_headers` confirms N suite folders / matching test
    files for a real seeded Application (real DB)
  - [x] Two full, genuine `npm install && npx playwright install && npx playwright test` runs against real
    downloaded zips (one per auth branch) both passed — see Dev Agent Record for the exact commands/output
  - [x] `test_downloading_twice_is_byte_identical` (real DB) confirms AC 8 against the live endpoint, not
    just the pure function
  - [x] Confirmed by code inspection: the endpoint and `test_suite_export.py` module contain no
    `session.add`/`commit()` or `start_workflow` call anywhere (AC 5)
  - [x] `test_download_is_organization_scoped` (real DB) confirms AC 6
  - [x] Sanitizer edge cases (empty slug, reserved device name, colliding Journey names) unit-tested
    directly; not separately re-exercised through the live endpoint (would need seeding a Journey named a
    bare `CON`/etc., which is a reasonable but non-essential addition — flagged, not silently skipped)
  - [x] Decided: an empty current `TestSuite` gets an empty-but-present folder (a `.gitkeep` placeholder),
    never excluded — documented in `test_suite_export.py`'s Dev Notes and unit-tested
    (`test_empty_current_suite_still_gets_a_folder`)
  - [x] `test_raises_rather_than_returning_partial_bytes` confirms AC 9's fail-closed guarantee at the pure-
    function level
  - [x] Headers confirmed both via unit-level assertions and the real live-endpoint test (AC 10)
  - [x] **`standard_login`, fully verified live**: seeded real `Page`/`Form`/`FormField` rows shaped exactly
    like Discovery's own capture, downloaded the real zip, ran `npm install && npx playwright install &&
    npx playwright test` with real credentials supplied only via `AITESTGEN_LOGIN_USERNAME`/
    `AITESTGEN_LOGIN_PASSWORD` env vars against a real local HTTP login page — the setup project logged in
    for real and the dependent test saw the authenticated-only page. **2 passed.** (AC 11, 12)
  - [x] **`sso_session_reuse`, fully verified live**: same flow, but supplied a real `storageState.json`
    (a real cookie for the fixture server) via `AITESTGEN_STORAGE_STATE` — the setup project performed no
    login at all and the dependent test still saw the authenticated-only page. **2 passed.** (AC 12)
  - [x] Grepped the fully-assembled zip's every file in both live runs for the real configured credential/
    session-state value used in that run — confirmed absent in both (AC 13)

## Dev Notes

- **This is a new, isolated module (`Test Suite Export`, architecture Module Map) — read-only over
  `TestSuite`/`TestAsset`.** It must not touch `PlaywrightGenerationActivity`, `SuiteGenerationWorkflow`, or
  `TestAsset.code` generation in any way. If a project-scaffold detail needs to change later (e.g. a
  different config default), that change is isolated entirely to this module.
- **Build a Node/TypeScript (`@playwright/test`) scaffold — not Python.** Settled 2026-07-29; see the
  `[CORRECTED 2026-07-29]` note at the top of this file.
- **Reuse `list_test_suites`'s exact query shape** (`main.py:787-855`) for finding current Journeys → current
  `TestSuite`s → current `TestAsset`s — don't re-derive the candidate-Journey/`current=true` filtering
  logic a second, possibly-divergent way.
- **`toTestFileName`'s slug (`TestSuiteResults.tsx`) is the starting point, not the finished sanitizer.**
  Today it only *incidentally* strips path separators and special characters as a side effect of an
  alphanumeric whitelist — it has no deliberate Windows-reserved-device-name check and no documented
  zip-slip guard. `[ENHANCED 2026-07-30]` The server-side sanitizer built on top of it must make these
  guarantees explicit and separately unit-tested (AC 7), not rely on the client helper's incidental behavior.
- **Zip assembly must be deterministic** (AC 8) — iterate suites/test-assets in a stable order (e.g. by `id`
  or by the same order the existing `list_test_suites` query already returns them in) so two downloads of
  unchanged data produce byte-identical output. Don't rely on dict/set iteration order incidentally being
  stable.
- **Authentication setup reads only non-secret Application columns (AC 11-13).** `Application.url` and
  `Application.auth_method` (Story 1.3/1.4) are plain, non-secret columns already present on the row this
  endpoint already fetches — no new query, and deliberately **no** call to `SecretsClient`/Vault. The actual
  credential or `storageState.json` content the customer supplied at onboarding is never read by, or
  present in, the export process — the exported project's setup script instead expects the *user* to supply
  that value again, at runtime, via an environment variable or a session-state file they provide themselves.
  This keeps the export module's "never touches secrets" property trivially true by construction rather than
  by careful redaction.
- **This widens the module's isolation boundary by one confirmed, deliberate exception.** The Dev Note above
  says this module must not touch generation internals (`TestAsset.code`/Vault) — that still holds
  unconditionally. But for `auth_method="standard_login"`, the module now also reads the Application Model's
  captured login-page evidence (URL/form-fields/selectors, Epic 2) to build `auth.setup.ts` — this crossing
  is accepted per the `[RESOLVED 2026-07-30]` note above, not something to re-litigate at implementation
  time. What still needs verifying at implementation time is only the exact table/query shape for that
  evidence (Task 1), not whether reading it is allowed. `[Source: 1-4-configure-application-authentication-method.md
  — Application.auth_method, Application.secret_ref shape; 1-3-onboard-an-application-basic-details.md —
  Application.url]`
- **Response headers are not an incidental detail (AC 10).** `Content-Type: application/zip` and a
  `Content-Disposition: attachment; filename="..."` header are both required for correct browser download
  behavior — the filename embedded in that header goes through the same sanitizer as the in-zip folder/file
  names (AC 7), since it's built from the same kind of user-controlled input (Application name).
- **Fail closed, never partial (AC 9).** The assembly function must not be able to return a half-built
  `BytesIO` — any validation or generation failure must raise, and the endpoint's own error handling (not a
  best-effort try/continue) is what turns that into a clear HTTP error. This is the same "no silent partial
  archive" principle AC 3 already stated for the success path, now stated for the failure path too.
- **CI-runnability (AC 4) needs no new artifact.** The exported project is CI-ready simply by being a
  standard npm/Playwright project — deliberately do **not** generate a CI-specific config file (e.g. a
  GitHub Actions workflow) or any git-integration scaffolding. The architecture spine explicitly scopes this
  feature as "not CI Delivery"; that boundary is intentional, not an oversight, and stays intentional after
  this enhancement pass.
- **No new pip/uv dependency for the zip itself** — `zipfile` and `io.BytesIO` are stdlib; only the
  *generated project's own* `package.json` lists `@playwright/test` (that's what the *downloaded* project
  needs, not `apps/api` itself).
- **The frontend's generic `request<T>()` helper cannot be reused for this call** — it unconditionally
  calls `response.json()` (`api.ts:24-36`), which throws on a binary body. This needs its own fetch +
  `.blob()` + object-URL-download function, matching how most browser download-a-file flows work; there is
  no existing precedent for this in the codebase (Story 4.3 is the first "download a file" feature), so this
  is new code, not a pattern extension.
- **The frontend button already exists but is disabled.** `TestSuiteResults.tsx`'s hero card currently
  renders a "Download Test Suite" button with `disabled` and `title="Coming soon"` and no `onClick` — Task 4
  wires this existing element up rather than adding a new one.

### Project Structure Notes

- New file: `apps/api/src/api/test_suite_export.py` (assembly + sanitizer logic — pure, easily
  unit-testable without a running Postgres).
- Updated: `apps/api/src/api/main.py` (new endpoint, Task 3).
- Updated: `apps/web/src/api.ts` (new download function), `apps/web/src/components/TestSuiteResults.tsx`
  (wire up existing disabled button).
- New tests: `apps/api/tests/test_test_suite_export.py` (endpoint + assembly + sanitizer edge cases), extend
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
  assembly function and its sanitizer directly and separately, without needing a database at all — pure
  functions over in-memory rows/strings.
- **Frontend**: `TestSuiteResults.test.tsx` currently stubs `fetch` to return `{ ok, status, json }` — the
  Download button's test needs a mock that instead returns a `blob()` method (e.g.
  `{ ok: true, status: 200, blob: async () => new Blob(['...']) }`), and should also stub
  `URL.createObjectURL`/`URL.revokeObjectURL` (not implemented in the jsdom/vitest test environment by
  default) to assert the download was triggered without actually needing a real Blob URL.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3: Download a Generated Test Suite]
- [Source: _bmad-output/planning-artifacts/prds/prd-AITestGen-2026-07-13/prd.md — FR-34]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-AITestGen-2026-07-13/ARCHITECTURE-SPINE.md#Module Map — Test Suite Export, #Deferred — Test Suite Export is not CI Delivery / TypeScript correction]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-27-2.md — full change history and the original (now superseded) language-correction addendum]
- [Source: apps/api/src/api/main.py:787-855 — `list_test_suites`, the exact query shape to reuse for finding current suites/assets]
- [Source: apps/web/src/components/TestSuiteResults.tsx — `toTestFileName`, the existing incidental slug helper, and the existing disabled "Download Test Suite" button Task 4 wires up]
- [Source: apps/web/src/api.ts:24-36 — `request<T>()`, the generic JSON helper this story's download call must NOT use]
- [Source: packages/ai_provider/src/ai_provider/hosted.py:129-146 — `_PLAYWRIGHT_PROMPT`, confirms generated code is TypeScript `@playwright/test`]
- [Source: apps/workers/generation/tests/test_playwright_generation_activity.py — confirms `TestAsset.code`'s actual TypeScript shape in a real assertion]
- [Source: packages/domain/src/domain/test_asset.py, packages/domain/src/domain/test_suite.py — `TestAsset`/`TestSuite` schemas this story reads, unmodified]
- [Source: _bmad-output/implementation-artifacts/4-2-generate-playwright-test-assets-from-scenarios.md — Story 4.2, the story that produces the rows this one exports]
- [Source: _bmad-output/implementation-artifacts/1-4-configure-application-authentication-method.md — `Application.auth_method` (`standard_login`/`sso_session_reuse`), `Application.secret_ref` via `SecretsClient`/Vault, never read directly by this story]
- [Source: _bmad-output/implementation-artifacts/1-3-onboard-an-application-basic-details.md — `Application.url`, the base URL injected into the exported `playwright.config.ts`]

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
`package.json` should pin a reasonably current version of `@playwright/test` at implementation time —
check npm for its current stable version rather than hardcoding a version from this story's own authoring
date, since this file may be implemented well after being written.

## Project Context Reference

No `project-context.md` exists yet in this repository.

## Change Log

- 2026-07-27 — Story created via `bmad-create-story`, following `sprint-change-proposal-2026-07-27-2.md`
  (Story 4.3, FR-34 added to Epic 4). During creation, discovered and corrected a language mismatch: the
  requesting brief assumed a Node/TypeScript project, but `TestAsset.code` is generated as Python — PRD,
  epics, and architecture were corrected in the same pass before this file was written. Flagged one
  unresolved `[GAP]` (Task 1).
- 2026-07-29 — `[CORRECTED]` Reverses the 2026-07-27 Python correction above: `HostedAIProvider`'s
  `_PLAYWRIGHT_PROMPT` now generates TypeScript (`@playwright/test`) by explicit decision, so this story's
  scaffold changes back to an npm-based project. ACs, Tasks 1-2, Dev Notes, and References updated to
  match; no change to Tasks 3-5's structure.
- 2026-07-30 — `[ENHANCED]` Same story number/status (ready-for-dev, no epic/FR change). Promoted five
  previously-implicit guarantees (org-scoped security, filename/path-traversal safety beyond the incidental
  slug behavior, deterministic output, fail-closed error handling on assembly/validation failure, and
  correct download response headers with a sanitized filename) into explicit ACs 6-10, with matching
  Task 2/3/5 sub-bullets and Dev Notes. Clarified AC4's CI-runnability wording (no new scope — confirmed with
  requester that this means the project already runs unmodified in any CI runner, not that a CI config file
  should be generated; architecture spine's "not CI Delivery" boundary is unchanged). Noted that Task 4's
  frontend button already exists in a disabled `"Coming soon"` state and only needs wiring up, not adding.
  Same-day further addition: ACs 11-13 add standalone authentication — injected `baseURL` (from
  `Application.url`), a Playwright `setup`-project/`storageState` pattern covering both of Story 1.4's
  `auth_method` values with zero changes to AI-generated `TestAsset.code`, and a hard guarantee that no
  *credential*/*session-state* content is ever embedded in the exported zip (the export module never calls
  `SecretsClient`/Vault at all). Same-day resolution: the `standard_login` setup mechanism is confirmed — it
  reuses the login page's URL/form-fields/selectors already captured by discovery during onboarding
  (Application Model, Epic 2), reading only credentials from runtime environment variables; no selectors or
  credentials are AI-generated or embedded. This deliberately widens the module's isolation boundary to also
  read Application Model login-page evidence for `standard_login` Applications — accepted as part of this
  enhancement. Remaining open item: the exact Application Model table/query shape for that captured evidence
  still needs confirming at implementation time (Task 1) — the mechanism itself is no longer in question.
- 2026-07-30 — `[IMPLEMENTED]` All 5 Tasks built and verified (Status: `ready-for-dev` → `review`). New
  `apps/api/src/api/test_suite_export.py` module + download endpoint + frontend wiring, per the Tasks
  checklist above. Confirmed the Application-Model query shape for `standard_login`'s login-page evidence
  (captured `Form` with a password-type `FormField`; no dedicated flag exists, matching the `[RESOLVED]`
  note's prediction). Ran genuine, non-simulated end-to-end verification for both `auth_method` branches
  (real HTTP fixture server, real `npm`/`npx playwright` toolchain, real downloaded zip) — both passed,
  and the run caught a real bug (`.first` vs `.first()` in the generated setup script) that unit tests alone
  had not. The `TestAsset.code` `[GAP]` is only partially closed (no live AI provider available this
  session) — see Dev Agent Record for the precise scope of what remains unconfirmed.

## Dev Agent Record

### Agent Model Used

claude-sonnet-5

### Debug Log References

- `uv run pytest apps/api/tests/test_test_suite_export.py -q` against the real running Postgres/Vault/
  Temporal (docker compose, already up in this session): **22 passed** (12 pure unit tests over the
  assembly/sanitizer module, no DB; 5 live-DB endpoint tests).
- `uv run pytest apps/api/tests -q` (full `apps/api` suite, regression check): **62 passed**.
- `uv run ruff check apps/api/src/api/test_suite_export.py apps/api/tests/test_test_suite_export.py
  apps/api/src/api/main.py` → all checks passed.
- `uv run pyright apps/api/src/api/test_suite_export.py apps/api/src/api/main.py` → 0 errors, 0 warnings.
- `npx vitest run` (apps/web) → **7/7** in `TestSuiteResults.test.tsx` (2 new: download success, download
  failure re-enables the button), **57/58 passed** repo-wide — the 1 failure (`App.test.tsx`) is a
  pre-existing, unrelated jsdom navigation error confirmed present on a clean `git stash` of this session's
  changes (same failure with or without this story's diff).
- `npx tsc -b` and `npx oxlint` (apps/web) → clean, no output.
- **Genuine end-to-end runs, not simulated** — for both `auth_method` branches, using the real `TestClient`-
  backed FastAPI app, a real local HTTP fixture server (Python `http.server`, no mocking), and the real
  `npm`/`npx playwright` toolchain already present in this environment:
  - `standard_login`: seeded a real login page (`GET /`, `POST /login` checking real credentials, setting a
    real `Set-Cookie`) and real `Page`/`Form`/`FormField` rows shaped exactly like
    `discovery_worker.session.establish_session`'s own capture (`captured_selector` values matching the
    fixture's actual HTML attributes: `[name="email"]`, `[name="password"]`). Created a real `Application`
    via `POST /applications`, downloaded the real zip via `GET .../test-suites/download`, extracted it,
    ran `npm install`, `npx playwright install chromium`, then `npx playwright test --project=setup
    --project=chromium` with `AITESTGEN_LOGIN_USERNAME`/`AITESTGEN_LOGIN_PASSWORD` set to the fixture's real
    credentials. **Result: 2 passed** — the setup project logged in for real using the captured selectors,
    saved `storageState`, and the dependent test (asserting the authenticated-only `/dashboard` text) passed
    using that session.
  - **This run caught and fixed a real bug**: the first generated `auth.setup.ts` used
    `page.locator(...).first` (a property access, no call) instead of `.first()` (Playwright's actual
    method) — failed with `TypeError: submit.count is not a function`. Fixed in
    `_build_auth_setup_script`/`test_suite_export.py` (all three occurrences), re-ran, passed. This is
    exactly the class of bug a real `npx playwright test` run catches and a unit test alone would not.
  - `sso_session_reuse`: same flow, but the seeded Application had no login-page evidence at all (this
    branch needs none); supplied a real `storageState.json` (containing a real cookie for the fixture
    server) via `AITESTGEN_STORAGE_STATE`. **Result: 2 passed** — the setup project performed zero login
    attempts (asserted `"fill(" not in setup_script`) and the dependent test still saw the authenticated
    page via the reused cookie.
  - Both runs' fully-extracted project directories were grepped for the real credential/cookie value used in
    that run — absent from every file, confirming AC 13 against real content, not just a mock.
  - Verification scripts were one-off, not committed (temp fixture servers + `tempfile.mkdtemp` workdirs,
    cleaned up after each run) — the *production* code paths and DB rows they exercised are exactly the real
    ones, unmocked.

### Completion Notes List

- Implemented `apps/api/src/api/test_suite_export.py` (new): `sanitize_slug`, `dedupe_slugs`,
  `LoginPageEvidence`, `find_login_page_evidence`, and `assemble_test_suite_project`, covering AC 1-3, 7-13.
- Added `GET /applications/{external_id}/test-suites/download` to `apps/api/src/api/main.py`, covering
  AC 1, 4-6, 9, 10.
- Wired the frontend: `apps/web/src/api.ts`'s `downloadTestSuiteProject` and
  `apps/web/src/components/TestSuiteResults.tsx`'s previously-disabled button, covering AC 1.
- `find_login_page_evidence`'s heuristic (captured `Form` with a password-type `FormField`) deliberately
  widens the module's isolation boundary exactly as the `[RESOLVED]` note above anticipated — confirmed
  correct and sufficient by the real end-to-end `standard_login` run.
- **Real, non-simulated verification** of both `auth_method` branches (see Debug Log) — this surfaced and
  fixed one genuine bug (`.first` vs `.first()`) that no unit test alone would have caught.
- The `TestAsset.code`-shape `[GAP]` (Task 1) is only *partially* closed — no live AI provider call was made
  in this session. The scaffold's compatibility with the prompt's documented shape is proven; residual risk
  is narrow (AI stylistic variance like `test.describe` wrapping), not architectural.
- Not done in this session, flagged rather than silently skipped: (a) sanitizer edge cases (reserved device
  name, empty slug) are unit-tested directly but not separately re-exercised through the live endpoint with
  a seeded `CON`-named Journey; (b) `apps/web/src/api-types.gen.ts` was not regenerated from a live API run
  (AD-6 convention) — this endpoint adds no new request/response schema (it returns a raw binary `Response`,
  not a `response_model`), so no drift is expected, but the regeneration+diff step itself wasn't performed;
  (c) no real (non-test-double) AI provider call was made, per the note above.
- Per repo convention observed this session, no git commit was created — changes are left in the working
  tree for review.

### File List

- `apps/api/src/api/test_suite_export.py` — new: assembly + sanitizer + login-evidence-query logic.
- `apps/api/src/api/main.py` — new `download_test_suite_project` endpoint + import.
- `apps/api/tests/test_test_suite_export.py` — new: 22 tests (12 pure unit, 5 live-DB endpoint, plus
  supporting fixtures/helpers).
- `apps/web/src/api.ts` — new `downloadTestSuiteProject` function.
- `apps/web/src/components/TestSuiteResults.tsx` — wired the existing disabled Download button.
- `apps/web/src/components/TestSuiteResults.test.tsx` — 2 new tests (download success, download failure).
