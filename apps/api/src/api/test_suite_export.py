"""Test Suite Export — assemble a downloadable TypeScript Playwright project (Story 4.3).

Reads only `TestSuite`/`TestAsset` (`current=true`), plus — for `standard_login`
Applications only — the Application Model's captured login-page evidence
(`Page`/`Form`/`FormField`) so the generated project can authenticate standalone.
Never calls `SecretsClient`/Vault: `Application.secret_ref` is never resolved here,
only the plain, non-secret `Application.auth_method`/`url` columns and (for
`standard_login`) the non-secret captured login-page URL/selectors are read.

There is no `page_type`/`is_login` flag anywhere in the Application Model — the
same heuristic the discovery worker itself uses to find a login form
(`apps/workers/discovery/src/discovery_worker/session.py::establish_session`,
`input[type="password"]`) is mirrored here at the database level: the captured
`Form` that has a `FormField` with `input_type == "password"` is treated as the
login form; its `Page.url` is the login URL. If no such Form was ever captured
(e.g. the Application never went through Discovery, or Discovery found no
password field), `find_login_page_evidence` returns `None` and the generated
setup script falls back to the same generic, hardcoded selectors
`establish_session`/`attempt_login` already use live during Discovery — never a
hard failure, since a missing login-page capture doesn't affect AC 1-10's
Test Suite export at all, only how well-targeted the AC 12 setup script is.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass

from domain import Application, Form, FormField, Page, TestSuite
from sqlmodel import Session, select

# Windows-reserved device names (case-insensitive) — never emit one of these
# as a bare folder/file stem, even though `zipfile` itself doesn't care; the
# archive must extract cleanly on a Windows machine too (AC 7).
_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# Mirrors `apps/web/src/components/TestSuiteResults.tsx`'s `toTestFileName` slug
# convention exactly for the base transform — this module then adds the
# deliberate guards (AC 7) that helper only ever provided incidentally.
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_SLUG_TRIM_RE = re.compile(r"^-+|-+$")


class TestSuiteExportError(Exception):
    """Raised when assembly/validation fails — the caller must never return
    a partial `BytesIO` on this path (AC 9); it must propagate to a clear
    non-2xx HTTP error instead."""

    __test__ = False  # pytest: not a test class, despite the name prefix


def sanitize_slug(name: str, *, fallback: str) -> str:
    """Lowercase, non-alphanumeric-collapsed slug — never empty, never a bare
    Windows-reserved device name, never containing a path separator or `..`
    (AC 7, AC 10). The alphanumeric whitelist already makes path-traversal
    structurally impossible (no `/`, `\\`, or `.` survives it) — the two
    guards this function adds *on top* of that incidental behavior are the
    empty-string fallback and the reserved-device-name check.
    """
    slug = _SLUG_TRIM_RE.sub("", _SLUG_STRIP_RE.sub("-", name.lower()))
    if not slug or slug in _WINDOWS_RESERVED_NAMES:
        return fallback
    return slug


def dedupe_slugs(items: list[tuple[str, str]]) -> dict[str, str]:
    """`items` is `[(unique_key, base_slug), ...]`. Returns `{unique_key: slug}`
    where two items sharing a `base_slug` get the second (and third, ...)
    disambiguated by appending a short suffix from `unique_key` — never
    silently overwriting one suite's files with another's (AC 7)."""
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
    value. `username_selector`/`password_selector` are plain CSS selectors
    (Playwright `page.locator(...)`-compatible), the same shape
    `discovery_worker.crawler._capture_selector` produces."""

    url: str
    username_selector: str | None
    password_selector: str


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
            username_selector=username_field.captured_selector if username_field else None,
            password_selector=password_field.captured_selector or 'input[type="password"]',
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


def _build_playwright_config(base_url: str) -> str:
    return (
        "import { defineConfig, devices } from '@playwright/test'\n\n"
        "export default defineConfig({\n"
        "  testDir: './tests',\n"
        "  fullyParallel: true,\n"
        "  use: {\n"
        f"    baseURL: '{base_url}',\n"
        "    trace: 'on-first-retry',\n"
        "  },\n"
        "  projects: [\n"
        "    { name: 'setup', testMatch: /.*\\.setup\\.ts$/ },\n"
        "    {\n"
        "      name: 'chromium',\n"
        "      use: { ...devices['Desktop Chrome'], storageState: '.auth/state.json' },\n"
        "      dependencies: ['setup'],\n"
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

    # standard_login — captured selectors when Discovery found the login
    # form, otherwise the same generic fallback selectors
    # `discovery_worker.session.attempt_login` already uses live.
    login_url = login_evidence.url if login_evidence else "/"
    username_selector = (
        f'page.locator({login_evidence.username_selector!r})'
        if login_evidence and login_evidence.username_selector
        else (
            'page.locator(\'input[type="email"], input[name*="user" i], '
            'input[type="text"]\').first()'
        )
    )
    password_selector = (
        f'page.locator({login_evidence.password_selector!r})'
        if login_evidence
        else 'page.locator(\'input[type="password"]\').first()'
    )
    return (
        "import { test as setup } from '@playwright/test'\n\n"
        "// Logs in once using the login page captured by Discovery (falls back to generic\n"
        "// selectors if none was captured) and saves the resulting session for every other\n"
        "// test to reuse. Credentials are read only from environment variables at runtime —\n"
        "// never a literal value in this file.\n"
        "setup('authenticate', async ({ page }) => {\n"
        "  const username = process.env.AITESTGEN_LOGIN_USERNAME\n"
        "  const password = process.env.AITESTGEN_LOGIN_PASSWORD\n"
        "  if (!username || !password) {\n"
        "    throw new Error("
        "'AITESTGEN_LOGIN_USERNAME and AITESTGEN_LOGIN_PASSWORD are required'"
        ")\n"
        "  }\n"
        f"  await page.goto({login_url!r})\n"
        f"  await {username_selector}.fill(username)\n"
        f"  await {password_selector}.fill(password)\n"
        "  const submit = page.locator('button[type=\"submit\"], input[type=\"submit\"]').first()\n"
        "  if (await submit.count() > 0) {\n"
        "    await submit.click()\n"
        "  } else {\n"
        f"    await {password_selector}.press('Enter')\n"
        "  }\n"
        "  await page.context().storageState({ path: '.auth/state.json' })\n"
        "})\n"
    )


def assemble_test_suite_project(
    application: Application,
    test_suites: Sequence[TestSuite],
    journeys_by_id: dict,
    assets_by_suite: dict,
    scenario_name_by_asset_id: dict,
    login_evidence: LoginPageEvidence | None,
) -> bytes:
    """Pure function: no DB/network access, deterministic given its inputs
    (AC 8) — the caller is responsible for querying `current=True` rows and
    for `login_evidence` (only ever non-`None` for `standard_login`, and
    only ever built from non-secret Application Model data, never Vault)."""
    # Deterministic ordering (AC 8) — the caller's query has no guaranteed
    # order, so this function must not rely on incoming list order either.
    ordered_suites = sorted(test_suites, key=lambda ts: ts.id)

    suite_slugs = dedupe_slugs(
        [
            (str(ts.id), sanitize_slug(journeys_by_id[ts.journey_id].name, fallback="journey"))
            for ts in ordered_suites
        ]
    )

    buffer = io.BytesIO()
    written_suite_folders = 0
    written_test_files = 0
    try:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("package.json", _build_package_json())
            zf.writestr("playwright.config.ts", _build_playwright_config(application.url))
            zf.writestr(
                "README.md", _build_readme(application.name, application.auth_method)
            )
            zf.writestr("fixtures/.gitkeep", "")
            zf.writestr("utils/.gitkeep", "")
            zf.writestr(
                "tests/auth.setup.ts",
                _build_auth_setup_script(application.auth_method, login_evidence),
            )

            for test_suite in ordered_suites:
                assets = sorted(assets_by_suite.get(test_suite.id, []), key=lambda a: a.id)
                if not assets:
                    # An empty current TestSuite (edge case — shouldn't occur
                    # per Story 4.2's own flow, but don't silently drop it):
                    # still gets a present folder, via its own .gitkeep, so
                    # AC 3's "every current TestSuite has a folder" holds.
                    folder = suite_slugs[str(test_suite.id)]
                    zf.writestr(f"tests/{folder}/.gitkeep", "")
                    written_suite_folders += 1
                    continue

                folder = suite_slugs[str(test_suite.id)]
                # Each test-case file's own name is derived from its
                # Scenario's name via the same slug convention as the suite
                # folder (`toTestFileName`'s algorithm) — deduped within this
                # folder's scope only, so two suites can reuse the same
                # test-case name without colliding across folders.
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
                written_suite_folders += 1
                for asset in assets:
                    file_slug = asset_slugs[str(asset.id)]
                    zf.writestr(f"tests/{folder}/{file_slug}.spec.ts", asset.code)
                    written_test_files += 1

        # Validation per AC 3/AC 9: assert what was actually written matches
        # what was queried — raise rather than return a silently incomplete
        # archive. `expected_assets` sums *every* value in `assets_by_suite`
        # (not just suites present in `ordered_suites`) so a caller bug that
        # passes assets for a suite missing from `test_suites` is caught
        # too, not silently ignored because the loop above never visits it.
        expected_assets = sum(len(v) for v in assets_by_suite.values())
        if written_suite_folders != len(ordered_suites) or written_test_files != expected_assets:
            raise TestSuiteExportError(
                "assembled archive does not match the queried Test Suites/Test Assets "
                f"(wrote {written_suite_folders}/{len(ordered_suites)} suite folders, "
                f"{written_test_files}/{expected_assets} test files)"
            )
    except TestSuiteExportError:
        raise
    except Exception as exc:  # noqa: BLE001 — fail-closed per AC 9, never a partial zip
        raise TestSuiteExportError(f"failed to assemble test suite project: {exc}") from exc

    return buffer.getvalue()
