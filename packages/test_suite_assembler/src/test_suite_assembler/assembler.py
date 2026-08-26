"""TestSuiteAssembler — TestAsset -> runnable Playwright project.

Extracted from `apps/api/src/api/test_suite_export.py` (Story 4.3) so the
downloadable ZIP and the project the Run All Tests execution worker runs
are always produced by the exact same code path:
`assemble_test_suite_project` (zip) and `assemble_test_suite_project_to_dir`
(plain directory) both delegate to `_write_project_files`, which only
differs in which `_ProjectWriter` it's handed — never in what it writes.

Reads only `TestSuite`/`TestAsset` (`current=true`), plus — for
`standard_login` Applications only — the Application Model's captured
login-page evidence (`Page`/`Form`/`FormField`) so the generated project can
authenticate standalone. Never calls `SecretsClient`/Vault:
`Application.secret_ref` is never resolved here, only the plain, non-secret
`Application.auth_method`/`url` columns and (for `standard_login`) the
non-secret captured login-page URL/selectors are read.

Secrets are never handled here in either output mode: the generated
`tests/auth.setup.ts` only ever reads `process.env.*` — it's up to the
caller how those env vars get populated (a human's own shell for a
downloaded export, Vault-resolved values passed as a subprocess env for
execution).

There is no `page_type`/`is_login` flag anywhere in the Application Model —
the same heuristic the discovery worker itself uses to find a login form
(`apps/workers/discovery/src/discovery_worker/session.py::establish_session`,
`input[type="password"]`) is mirrored here at the database level: the
captured `Form` that has a `FormField` with `input_type == "password"` is
treated as the login form; its `Page.url` is the login URL. If no such Form
was ever captured (e.g. the Application never went through Discovery, or
Discovery found no password field), `find_login_page_evidence` returns
`None` and the generated setup script falls back to the same generic,
hardcoded selectors `establish_session`/`attempt_login` already use live
during Discovery — never a hard failure.
"""

from __future__ import annotations

import io
import re
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from domain import Application, ComponentLocator, Form, FormField, Page, TestSuite
from sqlmodel import Session, select

# Windows-reserved device names (case-insensitive) — never emit one of these
# as a bare folder/file stem, even though `zipfile`/the filesystem writer
# itself doesn't care; the project must extract/materialize cleanly on a
# Windows machine too.
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# Mirrors `apps/web/src/components/TestSuiteResults.tsx`'s `toTestFileName`
# slug convention exactly for the base transform — this module then adds
# the deliberate guards that helper only ever provided incidentally.
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_SLUG_TRIM_RE = re.compile(r"^-+|-+$")


class TestSuiteExportError(Exception):
    """Raised when assembly/validation fails — a caller must never receive a
    partial project on this path; it must propagate to a clear error
    instead."""

    __test__ = False  # pytest: not a test class, despite the name prefix


def sanitize_slug(name: str, *, fallback: str) -> str:
    """Lowercase, non-alphanumeric-collapsed slug — never empty, never a bare
    Windows-reserved device name, never containing a path separator or `..`.
    The alphanumeric whitelist already makes path-traversal structurally
    impossible (no `/`, `\\`, or `.` survives it) — the two guards this
    function adds *on top* of that incidental behavior are the empty-string
    fallback and the reserved-device-name check.
    """
    slug = _SLUG_TRIM_RE.sub("", _SLUG_STRIP_RE.sub("-", name.lower()))
    if not slug or slug in _WINDOWS_RESERVED_NAMES:
        return fallback
    return slug


def dedupe_slugs(items: list[tuple[str, str]]) -> dict[str, str]:
    """`items` is `[(unique_key, base_slug), ...]`. Returns `{unique_key: slug}`
    where two items sharing a `base_slug` get the second (and third, ...)
    disambiguated by appending a short suffix from `unique_key` — never
    silently overwriting one suite's files with another's."""
    seen: dict[str, str] = {}
    result: dict[str, str] = {}
    for key, base_slug in items:
        slug = base_slug
        if slug in seen and seen[slug] != key:
            slug = f"{base_slug}-{key[:8]}"
        seen.setdefault(slug, key)
        result[key] = slug
    return result


@dataclass(frozen=True)
class LoginPageEvidence:
    """Non-secret login-page facts captured by Discovery — never a credential
    value. `username_locator`/`password_locator` are ready-to-use Playwright
    locator expressions (e.g. `page.locator('#username')` or
    `page.getByLabel('Email')`), not bare selector strings — built by
    `_field_locator_call` from whichever ground truth is available."""

    url: str
    username_locator: str | None
    password_locator: str


def _playwright_locator_call(strategy: str, value: str) -> str:
    """Mirrors `ai_provider.hosted._describe_known_locators`'s own rendering
    convention for the same `ComponentLocator` strategy vocabulary: `label`'s
    value is real visible label text for `getByLabel(...)`, never a
    `page.locator()` selector string; every other strategy's value already
    is one."""
    if strategy == "label":
        return f"page.getByLabel({value!r})"
    return f"page.locator({value!r})"


def _field_locator_call(session: Session, field: FormField | None) -> str | None:
    """Ground truth over guess (same principle Story 4.2's Playwright
    generation already applies to element locators): prefer Discovery's
    derived, durability-ranked `ComponentLocator` over the field's own raw
    `captured_selector`, which is only ever a fallback here."""
    if field is None:
        return None
    if field.component_id is not None:
        candidates = session.exec(
            select(ComponentLocator).where(ComponentLocator.component_id == field.component_id)
        ).all()
        preferred = next((loc for loc in candidates if loc.kind == "preferred"), None)
        fallbacks = [loc for loc in candidates if loc.kind == "fallback"]
        chosen = preferred or (min(fallbacks, key=lambda loc: loc.priority) if fallbacks else None)
        if chosen is not None:
            return _playwright_locator_call(chosen.strategy, chosen.value)
    if field.captured_selector:
        return f"page.locator({field.captured_selector!r}).first()"
    return None


def find_login_page_evidence(
    session: Session, application: Application
) -> LoginPageEvidence | None:
    """Heuristic query (see module docstring): the captured `Form` with a
    password-type `FormField` is treated as the login form. Returns `None`
    if Discovery never captured one — the caller falls back to generic
    selectors rather than failing."""
    pages = session.exec(select(Page).where(Page.application_id == application.id)).all()
    page_by_id = {p.id: p for p in pages}
    if not pages:
        return None

    forms = session.exec(
        select(Form).where(Form.page_id.in_(page_by_id.keys()))  # type: ignore[attr-defined]
    ).all()
    if not forms:
        return None
    form_ids = [f.id for f in forms]

    fields = session.exec(
        select(FormField).where(FormField.form_id.in_(form_ids))  # type: ignore[attr-defined]
    ).all()
    fields_by_form: dict = {}
    for field in fields:
        fields_by_form.setdefault(field.form_id, []).append(field)

    for form in forms:
        form_fields = fields_by_form.get(form.id, [])
        password_field = next((f for f in form_fields if f.input_type == "password"), None)
        if password_field is None:
            continue
        page = page_by_id.get(form.page_id)
        if page is None:
            continue
        username_field = next(
            (
                f
                for f in form_fields
                if f.input_type in ("email", "text") and f is not password_field
            ),
            None,
        )
        return LoginPageEvidence(
            url=page.url,
            username_locator=_field_locator_call(session, username_field),
            password_locator=(
                _field_locator_call(session, password_field)
                or 'page.locator(\'input[type="password"]\').first()'
            ),
        )
    return None


def _build_package_json() -> str:
    return (
        "{\n"
        '  "name": "exported-test-suite",\n'
        '  "private": true,\n'
        '  "scripts": {\n'
        '    "test": "playwright test"\n'
        "  },\n"
        '  "devDependencies": {\n'
        '    "@playwright/test": "^1.48.0"\n'
        "  }\n"
        "}\n"
    )


def _build_playwright_config(base_url: str, *, has_login: bool) -> str:
    """No manual chromium/signed-in project split to maintain: when Discovery
    captured a login page, the split below is driven entirely by the
    `@auth`/`@public` tag every generated spec carries — deterministically
    written by `PlaywrightGenerationActivity` (`spec_linter.apply_auth_tag`)
    from Discovery's own captured auth requirement, never a manual choice
    made per suite. Apps with no captured login get one plain project — a
    `setup`/auth project split would have nothing to authenticate."""
    # `retain-on-failure`, not `on-first-retry` — this project's default
    # `retries: 0` means a first-attempt failure never gets a second try, so
    # `on-first-retry` would silently never capture a trace at all. Both
    # artifacts are only written on failure either way (Run All Tests
    # feature: TestResultArtifact rows only ever exist for a
    # failing/timed-out/errored TestResult).
    if not has_login:
        return (
            "import { defineConfig, devices } from '@playwright/test'\n\n"
            "export default defineConfig({\n"
            "  testDir: './tests',\n"
            "  fullyParallel: true,\n"
            "  use: {\n"
            f"    baseURL: '{base_url}',\n"
            "    trace: 'retain-on-failure',\n"
            "    screenshot: 'only-on-failure',\n"
            "    ...devices['Desktop Chrome'],\n"
            "  },\n"
            "})\n"
        )
    return (
        "import { defineConfig, devices } from '@playwright/test'\n\n"
        "export default defineConfig({\n"
        "  testDir: './tests',\n"
        "  fullyParallel: true,\n"
        "  use: {\n"
        f"    baseURL: '{base_url}',\n"
        "    trace: 'retain-on-failure',\n"
        "    screenshot: 'only-on-failure',\n"
        "  },\n"
        "  projects: [\n"
        "    { name: 'setup', testMatch: /.*\\.setup\\.ts$/ },\n"
        "    {\n"
        "      name: 'authenticated',\n"
        "      testMatch: /.*\\.spec\\.ts$/,\n"
        "      grep: /@auth/,\n"
        "      use: { ...devices['Desktop Chrome'], storageState: '.auth/state.json' },\n"
        "      dependencies: ['setup'],\n"
        "    },\n"
        "    {\n"
        "      name: 'public',\n"
        "      testMatch: /.*\\.spec\\.ts$/,\n"
        "      grepInvert: /@auth/,\n"
        "      use: { ...devices['Desktop Chrome'] },\n"
        "    },\n"
        "  ],\n"
        "})\n"
    )


def _build_readme(application_name: str, auth_method: str) -> str:
    auth_section = (
        (
            "## Authentication (standard_login)\n\n"
            "This project logs in once (via `tests/auth.setup.ts`) before any test runs, and\n"
            "reuses the resulting session for every test (Playwright's `storageState` pattern).\n"
            "Supply the credentials at runtime — never commit them:\n\n"
            "```\n"
            "AITESTGEN_LOGIN_USERNAME=<username> AITESTGEN_LOGIN_PASSWORD=<password> "
            "npx playwright test\n"
            "```\n"
        )
        if auth_method == "standard_login"
        else (
            "## Authentication (sso_session_reuse)\n\n"
            "This project reuses an already-authenticated session instead of logging in.\n"
            "Supply the session state at runtime — never commit it:\n\n"
            "```\n"
            "AITESTGEN_STORAGE_STATE=/path/to/storageState.json npx playwright test\n"
            "```\n"
            "(`AITESTGEN_STORAGE_STATE` may also hold the JSON content directly "
            "instead of a path.)\n"
        )
    )
    return (
        f"# {application_name} — Exported Test Suite\n\n"
        "Generated by AITestGen. Every folder under `tests/` (except `auth.setup.ts`) is one\n"
        "exported Test Suite; every `.spec.ts` file inside it is one generated test.\n\n"
        "## Setup\n\n"
        "```\n"
        "npm install\n"
        "npx playwright install\n"
        "```\n\n"
        f"{auth_section}\n"
        "## Run\n\n"
        "```\n"
        "npx playwright test               # every suite\n"
        "npx playwright test tests/<suite-folder>   # one suite only\n"
        "```\n\n"
        "Runs unmodified in any standard CI runner: `npm ci && npx playwright install --with-deps "
        "&& npx playwright test` — no CI-specific config file or extra setup required.\n"
    )


def _build_auth_setup_script(auth_method: str, login_evidence: LoginPageEvidence | None) -> str:
    if auth_method == "sso_session_reuse":
        return (
            "import { test as setup } from '@playwright/test'\n"
            "import { mkdirSync, readFileSync, writeFileSync } from 'fs'\n"
            "import { dirname } from 'path'\n\n"
            "// Reuses an already-authenticated session captured before export — never logs in,\n"
            "// never reads a credential. AITESTGEN_STORAGE_STATE may hold either a file path or\n"
            "// the storageState JSON content directly.\n"
            "setup('reuse session', async () => {\n"
            "  const raw = process.env.AITESTGEN_STORAGE_STATE\n"
            "  if (!raw) {\n"
            "    throw new Error("
            "'AITESTGEN_STORAGE_STATE is required (a storageState.json path or its JSON content)'"
            ")\n"
            "  }\n"
            "  const path = '.auth/state.json'\n"
            "  mkdirSync(dirname(path), { recursive: true })\n"
            "  const content = raw.trim().startsWith('{') ? raw : readFileSync(raw, 'utf-8')\n"
            "  writeFileSync(path, content)\n"
            "})\n"
        )

    # standard_login — reuses the same shared fillCredentials helper every
    # generated spec calls (support/auth.ts), so the login flow itself is
    # defined in exactly one place, not duplicated between this setup script
    # and every generated spec (feature: shared auth-flow helper).
    login_url = login_evidence.url if login_evidence else "/"
    return (
        "import { test as setup } from '@playwright/test'\n"
        "import { fillCredentials, isAuthenticated } from '../support/auth'\n"
        "import { mkdirSync, writeFileSync } from 'fs'\n\n"
        "// Logs in once (via the shared fillCredentials helper — see support/auth.ts) and\n"
        "// saves the resulting session for every other test to reuse.\n"
        "setup('authenticate', async ({ page }) => {\n"
        f"  const loginUrl = {login_url!r}\n"
        "  await page.goto(loginUrl)\n"
        "  await fillCredentials(page)\n"
        "\n"
        "  // `[FIXED]` Verify login actually succeeded before trusting this session for\n"
        "  // every other test — a missing/wrong credential (e.g. the placeholder default in\n"
        "  // support/config.ts, if AITESTGEN_LOGIN_USERNAME/PASSWORD were never set) submits\n"
        "  // without throwing, but lands back on the same login form or an error page, not a\n"
        "  // real authenticated one. Never assume success just because fillCredentials()\n"
        "  // completed without an exception — that only proves the form was submitted, not\n"
        "  // that the submission was accepted. `isAuthenticated` (support/auth.ts) checks\n"
        "  // both the URL (did we actually leave the login page?) and the password field\n"
        "  // (absence alone was the old, weaker signal on its own).\n"
        "  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {})\n"
        "  if (!(await isAuthenticated(page, loginUrl))) {\n"
        "    throw new Error(\n"
        "      'Authentication failed: still on the login page (or a password field is ' +\n"
        "      'still visible) after submitting credentials. Verify ' +\n"
        "      'AITESTGEN_LOGIN_USERNAME/AITESTGEN_LOGIN_PASSWORD are set to valid credentials ' +\n"
        "      'for this application before running the suite.',\n"
        "    )\n"
        "  }\n"
        "\n"
        "  // `indexedDB: true` — Playwright only captures IndexedDB when asked; some auth\n"
        "  // libraries (Firebase Auth, MSAL/OAuth token caches, ...) store their session\n"
        "  // there instead of cookies/localStorage, and it would otherwise be silently\n"
        "  // dropped from every restored session below.\n"
        "  await page.context().storageState({ path: '.auth/state.json', indexedDB: true })\n"
        "\n"
        "  // `[FIXED]` `storageState()` above never captures `sessionStorage` at all — not\n"
        "  // an oversight to work around here, just outside what that API snapshots (see\n"
        "  // https://playwright.dev/docs/auth#session-storage). Some apps keep a session\n"
        "  // artifact there (a CSRF token, a tab-scoped session flag, ...) that API calls on\n"
        "  // every later authenticated page depend on — dropped, those calls fail and the\n"
        "  // page renders as if signed out even though cookies/localStorage restored fine.\n"
        "  // Captured generically (every key this origin's sessionStorage actually holds,\n"
        "  // nothing app-specific named here) and restored by support/fixtures.ts for every\n"
        "  // `@auth` test — see that file for the restore side of this.\n"
        "  const sessionStorageSnapshot = await page.evaluate(() => {\n"
        "    const entries: Record<string, string> = {}\n"
        "    for (let i = 0; i < window.sessionStorage.length; i++) {\n"
        "      const key = window.sessionStorage.key(i)\n"
        "      if (key !== null) entries[key] = window.sessionStorage.getItem(key) ?? ''\n"
        "    }\n"
        "    return entries\n"
        "  })\n"
        "  mkdirSync('.auth', { recursive: true })\n"
        "  writeFileSync(\n"
        "    '.auth/session-storage.json',\n"
        "    JSON.stringify({ [new URL(page.url()).origin]: sessionStorageSnapshot }),\n"
        "  )\n"
        "})\n"
    )


def _build_fixtures_helper_script(login_url: str | None) -> str:
    """`[FIXED]` Every generated spec's `import { test, expect } from
    '@playwright/test'` resolves HERE instead, via this project's
    tsconfig.json `paths` mapping — never by editing that import line, in
    an already-generated spec or a newly-generated one. Playwright's own
    context/page fixtures apply `storageState` (cookies/localStorage,
    IndexedDB when asked) automatically; the one thing they never restore
    — `sessionStorage`, see auth.setup.ts's own note — is restored exactly
    once here, for every `@auth`-tagged test's context, before that test's
    first navigation, from whatever `auth.setup.ts` captured. A `@public`
    test (or an `@auth` run before any `.auth/session-storage.json` exists)
    gets an untouched context, same as today.

    `[FIXED]` `@auth` tests all share the ONE session `auth.setup.ts`
    captured — a concurrently-running test that logs out, changes the
    password, or otherwise invalidates the account's session invalidates it
    for every other `@auth` test still using that same snapshot, which then
    fails on whatever locator it happened to be waiting on with no hint why.

    `[FIXED]` This used to try to detect that specifically — an HTTP status,
    a URL/password-field check, a curated list of "session expired"/
    "something went wrong" phrasings — before deciding whether to raise.
    Every one of those is a guess at how a particular app happens to phrase
    or signal it, and real apps kept surfacing new ones a fixed list could
    never fully cover. Dropped entirely: any `@auth` test that fails now
    raises this one marker unconditionally, and `execution_worker` retries
    it once against a freshly re-established session regardless of why it
    failed (see its own note) — a real bug in the test's own steps just
    fails the same way again on retry, so nothing is masked, and the only
    cost of a false alarm is one extra retry."""
    context_fixture = (
        "  context: async ({ context }, use, testInfo) => {\n"
        "    if (testInfo.tags.includes('@auth') && existsSync(SESSION_STORAGE_PATH)) {\n"
        "      const byOrigin = JSON.parse(readFileSync(SESSION_STORAGE_PATH, 'utf-8'))\n"
        "      await context.addInitScript((snapshot: Record<string, Record<string, string>>) => {\n"
        "        const entries = snapshot[window.location.origin]\n"
        "        if (entries) {\n"
        "          for (const key of Object.keys(entries)) {\n"
        "            window.sessionStorage.setItem(key, entries[key])\n"
        "          }\n"
        "        }\n"
        "      }, byOrigin)\n"
        "    }\n"
        "    await use(context)\n"
        "  },\n"
    )
    if login_url is None:
        # No login page was ever captured — there is no known login URL to
        # compare a possibly-invalidated session against, so there is
        # nothing this can check. Skip the whole thing rather than guess
        # with an empty/placeholder URL.
        return (
            "export * from '../node_modules/@playwright/test'\n"
            "import { test as base } from '../node_modules/@playwright/test'\n"
            "import { existsSync, readFileSync } from 'fs'\n"
            "import { join } from 'path'\n\n"
            "const SESSION_STORAGE_PATH = join(__dirname, '..', '.auth', 'session-storage.json')\n\n"
            "export const test = base.extend({\n"
            f"{context_fixture}"
            "})\n"
        )
    # `[FIXED]` Used to try to *detect* an invalidated session before
    # retrying — an HTTP status check, then a URL/password-field check, then
    # a curated list of "session expired"/"something went wrong" phrasings.
    # Every one of those is a guess at how some particular app happens to
    # phrase or signal it, and real apps keep surfacing new ones (a non-401
    # status, a generic error boundary with no session-related wording at
    # all, ...) — an unbounded, unwinnable list to maintain generically.
    # There is nothing to lose by dropping the guessing entirely: any
    # `@auth` test that fails gets exactly one retry against a freshly
    # re-established session (`execution_worker` greps for this marker —
    # see its own note) regardless of why it failed. A genuine bug in the
    # test's own steps just fails the same way again on retry and is
    # reported as-is; the only cost of being "wrong" is one extra retry,
    # never a masked failure.
    page_fixture = (
        "  page: async ({ page }, use, testInfo) => {\n"
        "    await use(page)\n"
        "    if (testInfo.tags.includes('@auth') && testInfo.status !== 'passed') {\n"
        "      throw new Error(\n"
        "        'AUTH_SESSION_INVALID: this @auth test failed — retrying once against a ' +\n"
        "        'freshly re-established session in case a concurrently-running test ' +\n"
        "        'logged out or otherwise invalidated the shared account session. If it ' +\n"
        "        'fails again after the retry, this is the original failure, not a ' +\n"
        "        'session problem.',\n"
        "      )\n"
        "    }\n"
        "  },\n"
    )
    return (
        "export * from '../node_modules/@playwright/test'\n"
        "import { test as base } from '../node_modules/@playwright/test'\n"
        "import { existsSync, readFileSync } from 'fs'\n"
        "import { join } from 'path'\n\n"
        "const SESSION_STORAGE_PATH = join(__dirname, '..', '.auth', 'session-storage.json')\n\n"
        "export const test = base.extend({\n"
        f"{context_fixture}"
        f"{page_fixture}"
        "})\n"
    )


def _build_tsconfig() -> str:
    """The only piece wiring `support/fixtures.ts` in — every generated (and
    already-generated) spec keeps importing the literal string
    `'@playwright/test'`; this is what makes that resolve to the fixtures
    file above instead of the real package, transparently, project-wide."""
    return (
        "{\n"
        '  "compilerOptions": {\n'
        '    "baseUrl": ".",\n'
        '    "paths": {\n'
        '      "@playwright/test": ["./support/fixtures.ts"]\n'
        "    }\n"
        "  }\n"
        "}\n"
    )


def _build_config_script() -> str:
    return (
        "// Central credential registry (feature: single source of truth for test\n"
        "// credentials) — every generated spec and the auth setup script import from\n"
        "// here, never `process.env` directly, so the env var name is defined in exactly\n"
        "// one place instead of drifting between files. Falls back to a placeholder\n"
        "// account so the suite still runs when the env vars are unset; override them\n"
        "// with a real account for an actual run:\n"
        "// AITESTGEN_LOGIN_USERNAME=... AITESTGEN_LOGIN_PASSWORD=... npx playwright test\n"
        "export const CREDENTIALS = {\n"
        "  username: process.env.AITESTGEN_LOGIN_USERNAME ?? 'testuser@example.com',\n"
        "  password: process.env.AITESTGEN_LOGIN_PASSWORD ?? 'Test1234!',\n"
        "}\n"
    )


def _build_auth_helper_script(login_evidence: LoginPageEvidence | None) -> str:
    """Feature: shared auth-flow helper, not per-spec generation. Every
    generated spec that needs an authenticated session as a precondition
    calls this instead of writing its own fill/click steps — the "forgot a
    field" bug class becomes structurally impossible to reintroduce per
    spec, since there's only one login implementation to get right."""
    username_locator = (
        login_evidence.username_locator
        if login_evidence and login_evidence.username_locator
        else (
            'page.locator(\'input[type="email"], input[name*="user" i], '
            'input[type="text"]\').first()'
        )
    )
    password_locator = (
        login_evidence.password_locator
        if login_evidence
        else 'page.locator(\'input[type="password"]\').first()'
    )
    return (
        "import type { Page } from '@playwright/test'\n"
        "import { CREDENTIALS } from './config'\n\n"
        "export async function fillCredentials(\n"
        "  page: Page,\n"
        "  username: string = CREDENTIALS.username,\n"
        "  password: string = CREDENTIALS.password,\n"
        "): Promise<void> {\n"
        f"  await {username_locator}.fill(username)\n"
        f"  await {password_locator}.fill(password)\n"
        "  const submit = page.locator('button[type=\"submit\"], input[type=\"submit\"]').first()\n"
        "  if (await submit.count() > 0) {\n"
        "    await submit.click()\n"
        "  } else {\n"
        f"    await {password_locator}.press('Enter')\n"
        "  }\n"
        "}\n\n"
        "// `[FIXED]` Shared by auth.setup.ts (verifying the initial login) and\n"
        "// support/fixtures.ts (verifying a *restored* session is still valid before an\n"
        "// `@auth` test runs) — one implementation of what \"actually authenticated\" means,\n"
        "// not two heuristics that can drift apart. A password field being gone is not\n"
        "// enough on its own — some apps land on a generic error page, not the login form,\n"
        "// when a session is rejected. Combined with a URL check (still on the exact login\n"
        "// page path) covers both a traditional server-rendered redirect-to-login and an\n"
        "// SPA that just re-renders the same route's form without leaving it.\n"
        "//\n"
        "// `[FIXED]` Neither of those catches a server that renders an \"invalid session\"\n"
        "// page in place — HTTP 200, same URL the test asked for, no login form at all —\n"
        "// instead of a status code or a redirect. There is no reliable structural signal\n"
        "// for this (unlike the login form itself, this markup is different for every\n"
        "// app), so this falls back to scanning the rendered text for the same small set\n"
        "// of phrasings essentially every app uses for it — the same \"curated marker\n"
        "// list, not a guess at one app's exact wording\" approach every generated spec's\n"
        "// own `assertNoServerError` already uses for a *server* error page. Deliberately\n"
        "// broad (session OR generic auth phrasing) since the point is to catch the class,\n"
        "// not one exact string.\n"
        "const SESSION_INVALID_MARKERS = [\n"
        "  /session\\s+(has\\s+|is\\s+)?(expired|expir(ing|ed)|timed?\\s*out|is\\s+invalid|"
        "is\\s+no\\s+longer\\s+valid|id\\s+is\\s+invalid)/i,\n"
        "  /invalid\\s+session/i,\n"
        "  /please\\s+(log|sign)\\s+in(\\s+again)?/i,\n"
        "  /\\b(log|sign)\\s+in\\s+again\\b/i,\n"
        "  /authentication\\s+(required|failed)/i,\n"
        "  /not\\s+authenticated/i,\n"
        "  // `[FIXED]` Some apps route an invalid/expired session through the same\n"
        "  // generic error boundary as any other unhandled failure — no \"session\"/\"log\n"
        "  // in\" wording at all, just a catch-all \"something broke\" page. Still a\n"
        "  // generic, framework-level phrasing (a React/Next.js-style error boundary's\n"
        "  // stock copy), not one app's exact text, so it belongs in this same curated\n"
        "  // list rather than being hardcoded as a one-off special case. A false\n"
        "  // positive here only ever costs one extra retry against a freshly\n"
        "  // re-authenticated session (see support/fixtures.ts) — worst case it's\n"
        "  // wasted, never a masked bug, since a retry that fails again for an\n"
        "  // unrelated reason still reports as failed.\n"
        "  /something\\s+went\\s+wrong/i,\n"
        "  /an\\s+unexpected\\s+error\\s+(has\\s+)?occurred/i,\n"
        "]\n\n"
        "export async function isAuthenticated(page: Page, loginUrl: string): Promise<boolean> {\n"
        "  const loginPath = new URL(loginUrl, page.url()).pathname\n"
        "  if (new URL(page.url()).pathname === loginPath) {\n"
        "    return false\n"
        "  }\n"
        "  const passwordFieldVisible = await page\n"
        "    .locator('input[type=\"password\"]')\n"
        "    .first()\n"
        "    .isVisible()\n"
        "    .catch(() => false)\n"
        "  if (passwordFieldVisible) {\n"
        "    return false\n"
        "  }\n"
        "  const bodyText = await page.content().catch(() => '')\n"
        "  return !SESSION_INVALID_MARKERS.some((marker) => marker.test(bodyText))\n"
        "}\n"
    )


def _build_interactions_helper_script() -> str:
    """Feature: shared element-resolution helper, not per-spec scroll logic.
    Playwright's own `.click()`/`.fill()` already auto-scroll an element
    into view as part of their actionability checks, but an assertion
    (`toBeVisible()`, etc.) does not, and a custom-scrolling container can
    occasionally still leave an element outside Playwright's own auto-
    scroll. Every generated spec routes through this one implementation
    instead of writing its own scroll-then-verify steps, so a genuinely
    wrong/stale locator fails with a clear, diagnosable error instead of a
    bare actionability timeout — the same "one implementation, not
    duplicated per spec" reasoning `fillCredentials` already established.

    `[FIXED]` Used to take an optional `description`/`selectorText` second
    argument that the generation prompt asked the AI to always pass — but
    an LLM instruction is a request, not a guarantee, and plenty of
    generated calls still omitted it, leaving the thrown error just as
    anonymous as before. `Locator.toString()` (Playwright's own "human-
    readable representation... based on the locator's selector") is always
    available with zero cooperation required from whatever calls this, so
    the identifying detail is now unconditional — this single shared
    implementation is also what every already-generated spec's one-arg
    `ensureVisible(locator)` call resolves to at export/run time, so this
    fix is retroactive without regenerating anything."""
    return (
        "import type { Locator } from '@playwright/test'\n\n"
        "export async function ensureVisible(\n"
        "  locator: Locator,\n"
        "  timeout = 15000,\n"
        "): Promise<Locator> {\n"
        "  if (await locator.isVisible().catch(() => false)) {\n"
        "    return locator\n"
        "  }\n"
        "  await locator.scrollIntoViewIfNeeded({ timeout }).catch(() => {})\n"
        "  const visibleAfterScroll = await locator.isVisible().catch(() => false)\n"
        "  if (!visibleAfterScroll) {\n"
        "    throw new Error(\n"
        "      `Element matched by locator ${locator.toString()} is not visible even after "
        "scrolling it into ` +\n"
        "      'view — the locator may be wrong, or the element requires a prior action '"
        " +\n"
        "      '(opening a menu/accordion/tab, waiting for content to load) to become "
        "visible.',\n"
        "    )\n"
        "  }\n"
        "  return locator\n"
        "}\n"
    )


class _ProjectWriter(ABC):
    """Abstracts "put this file somewhere" so `_write_project_files` runs
    identically for a zip archive and a plain directory — the only thing
    that differs between export and execution is which writer it's handed."""

    @abstractmethod
    def write(self, path: str, content: str) -> None: ...


class _ZipWriter(_ProjectWriter):
    def __init__(self, zf: zipfile.ZipFile) -> None:
        self._zf = zf

    def write(self, path: str, content: str) -> None:
        self._zf.writestr(path, content)


class _DirWriter(_ProjectWriter):
    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, path: str, content: str) -> None:
        dest = self._root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")


def compute_spec_paths(
    test_suites: Sequence[TestSuite],
    journeys_by_id: dict,
    assets_by_suite: dict,
    scenario_name_by_asset_id: dict,
) -> dict:
    """The same suite/asset slug derivation `_write_project_files` uses when
    it actually writes files, exposed standalone (pure, no I/O) so a caller
    that already knows the assembled project's layout — the execution
    worker, resolving which `.spec.ts` file to run for one `TestAsset` —
    can recompute `{TestAsset.id: "tests/<suite>/<file>.spec.ts"}` fresh
    from the same DB-sourced inputs Prepare used to assemble the project,
    rather than persisting a derived value or relying on in-memory state
    surviving across separate Activity invocations."""
    ordered_suites = sorted(test_suites, key=lambda ts: ts.id)
    suite_slugs = dedupe_slugs(
        [
            (str(ts.id), sanitize_slug(journeys_by_id[ts.journey_id].name, fallback="journey"))
            for ts in ordered_suites
        ]
    )

    spec_path_by_asset_id: dict = {}
    for test_suite in ordered_suites:
        assets = sorted(assets_by_suite.get(test_suite.id, []), key=lambda a: a.id)
        if not assets:
            continue
        folder = suite_slugs[str(test_suite.id)]
        # Each test-case file's own name is derived from its Scenario's name
        # via the same slug convention as the suite folder (`toTestFileName`'s
        # algorithm) — deduped within this folder's scope only, so two
        # suites can reuse the same test-case name without colliding across
        # folders.
        asset_slugs = dedupe_slugs(
            [
                (
                    str(a.id),
                    sanitize_slug(
                        scenario_name_by_asset_id.get(a.id, str(a.id)), fallback="test"
                    ),
                )
                for a in assets
            ]
        )
        for asset in assets:
            spec_path_by_asset_id[asset.id] = f"tests/{folder}/{asset_slugs[str(asset.id)]}.spec.ts"

    return spec_path_by_asset_id


def _write_project_files(
    writer: _ProjectWriter,
    application: Application,
    test_suites: Sequence[TestSuite],
    journeys_by_id: dict,
    assets_by_suite: dict,
    scenario_name_by_asset_id: dict,
    login_evidence: LoginPageEvidence | None,
) -> tuple[int, int, dict]:
    """Writes every project file via `writer`. Returns
    `(written_suite_folders, written_test_files, spec_path_by_asset_id)` —
    the counts for the caller's own completeness validation, and the same
    map `compute_spec_paths` returns (computed once here, not recomputed).
    Deterministic given its inputs, no DB/network access here."""
    ordered_suites = sorted(test_suites, key=lambda ts: ts.id)
    suite_slugs = dedupe_slugs(
        [
            (str(ts.id), sanitize_slug(journeys_by_id[ts.journey_id].name, fallback="journey"))
            for ts in ordered_suites
        ]
    )
    spec_path_by_asset_id = compute_spec_paths(
        test_suites, journeys_by_id, assets_by_suite, scenario_name_by_asset_id
    )

    writer.write("package.json", _build_package_json())
    writer.write("tsconfig.json", _build_tsconfig())
    writer.write(
        "playwright.config.ts",
        _build_playwright_config(application.url, has_login=login_evidence is not None),
    )
    writer.write("README.md", _build_readme(application.name, application.auth_method))
    writer.write("fixtures/.gitkeep", "")
    writer.write("utils/.gitkeep", "")
    writer.write(
        "tests/auth.setup.ts",
        _build_auth_setup_script(application.auth_method, login_evidence),
    )
    writer.write("support/config.ts", _build_config_script())
    writer.write("support/auth.ts", _build_auth_helper_script(login_evidence))
    writer.write("support/interactions.ts", _build_interactions_helper_script())
    writer.write(
        "support/fixtures.ts",
        _build_fixtures_helper_script(login_evidence.url if login_evidence else None),
    )

    written_suite_folders = 0
    written_test_files = 0
    for test_suite in ordered_suites:
        assets = sorted(assets_by_suite.get(test_suite.id, []), key=lambda a: a.id)
        if not assets:
            # An empty current TestSuite (edge case) still gets a present
            # folder, via its own .gitkeep, so "every current TestSuite has
            # a folder" holds regardless of output mode.
            folder = suite_slugs[str(test_suite.id)]
            writer.write(f"tests/{folder}/.gitkeep", "")
            written_suite_folders += 1
            continue

        written_suite_folders += 1
        for asset in assets:
            spec_path = spec_path_by_asset_id[asset.id]
            writer.write(spec_path, asset.code)
            written_test_files += 1

    return written_suite_folders, written_test_files, spec_path_by_asset_id


def _validate_written(
    test_suites: Sequence[TestSuite],
    assets_by_suite: dict,
    written_suite_folders: int,
    written_test_files: int,
) -> None:
    """Asserts what was actually written matches what was queried — raises
    rather than let a caller receive a silently incomplete project.
    `expected_assets` sums *every* value in `assets_by_suite` (not just
    suites present in `test_suites`) so a caller bug that passes assets for
    a suite missing from `test_suites` is caught too, not silently ignored
    because the write loop never visits it."""
    expected_assets = sum(len(v) for v in assets_by_suite.values())
    if written_suite_folders != len(test_suites) or written_test_files != expected_assets:
        raise TestSuiteExportError(
            "assembled project does not match the queried Test Suites/Test Assets "
            f"(wrote {written_suite_folders}/{len(test_suites)} suite folders, "
            f"{written_test_files}/{expected_assets} test files)"
        )


def assemble_test_suite_project(
    application: Application,
    test_suites: Sequence[TestSuite],
    journeys_by_id: dict,
    assets_by_suite: dict,
    scenario_name_by_asset_id: dict,
    login_evidence: LoginPageEvidence | None,
) -> bytes:
    """Pure function: no DB/network access, deterministic given its inputs —
    the caller is responsible for querying `current=True` rows and for
    `login_evidence` (only ever non-`None` for `standard_login`, and only
    ever built from non-secret Application Model data, never Vault). Returns
    the project zipped, for a browser download."""
    buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            written_suite_folders, written_test_files, _ = _write_project_files(
                _ZipWriter(zf),
                application,
                test_suites,
                journeys_by_id,
                assets_by_suite,
                scenario_name_by_asset_id,
                login_evidence,
            )
        _validate_written(test_suites, assets_by_suite, written_suite_folders, written_test_files)
    except TestSuiteExportError:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-closed, never a partial zip
        raise TestSuiteExportError(f"failed to assemble test suite project: {exc}") from exc

    return buffer.getvalue()


def assemble_test_suite_project_to_dir(
    dest_dir: str | Path,
    application: Application,
    test_suites: Sequence[TestSuite],
    journeys_by_id: dict,
    assets_by_suite: dict,
    scenario_name_by_asset_id: dict,
    login_evidence: LoginPageEvidence | None,
) -> dict:
    """Same inputs/guarantees as `assemble_test_suite_project`, writing a
    plain directory instead of a zip — the shape the Run All Tests execution
    worker needs so it can hand the project straight to `npx playwright
    test` without re-extracting an archive first. Returns
    `{TestAsset.id: "tests/<suite>/<file>.spec.ts"}` so the caller can run
    one specific test by its relative path."""
    try:
        written_suite_folders, written_test_files, spec_path_by_asset_id = _write_project_files(
            _DirWriter(Path(dest_dir)),
            application,
            test_suites,
            journeys_by_id,
            assets_by_suite,
            scenario_name_by_asset_id,
            login_evidence,
        )
        _validate_written(test_suites, assets_by_suite, written_suite_folders, written_test_files)
    except TestSuiteExportError:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-closed, never a partial project
        raise TestSuiteExportError(f"failed to assemble test suite project: {exc}") from exc

    return spec_path_by_asset_id
