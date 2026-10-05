import pytest
from playwright_typecheck import TypecheckUnavailable, typecheck_playwright_code
from recording_worker.assertion_uncomment import uncomment_codegen_assertions
from recording_worker.auth_tag import apply_auth_tag
from recording_worker.spec_normalizer import is_legacy_standalone_script, normalize_recorded_spec

# Legacy `--target javascript` shapes, copied from real persisted recordings
# (credentials replaced).
_LEGACY_LOGGED_OUT = """\
const { chromium } = require('playwright');
const { expect } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({
    headless: false
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://app.example.com/#/Login');
  await page.getByRole('textbox', { name: 'User Name' }).click();
  await page.getByRole('textbox', { name: 'User Name' }).fill('someone');
  await page.getByRole('textbox', { name: 'Password' }).click();
  await page.getByRole('textbox', { name: 'Password' }).fill('not-a-real-password');
  await page.getByRole('button', { name: 'Login' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  // ---------------------
  await context.close();
  await browser.close();
})();
"""

_LEGACY_AUTHENTICATED = """\
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: false
  });
  const context = await browser.newContext({
    storageState: '/tmp/recording-auth-0123456789abcdef.json'
  });
  const page = await context.newPage();
  await page.goto('https://app.example.com/Dashboard');
  await page.getByRole('link', { name: 'Investments' }).click();
  // await expect(page.getByRole('main')).toContainText('Portfolio value');

  // ---------------------
  await context.close();
  await browser.close();
})();
"""

# `--target playwright-test` shape, as Codegen writes it with --load-storage.
_NEW_AUTHENTICATED = """\
import { test, expect } from '@playwright/test';

test.use({
  storageState: '/tmp/recording-auth-0123456789abcdef.json'
});

test('test', async ({ page }) => {
  await page.goto('https://app.example.com/Dashboard');
  await page.getByRole('link', { name: 'Investments' }).click();
});
"""

_NEW_WITH_LOGIN = """\
import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('https://app.example.com/Login');
  await page.getByRole('textbox', { name: 'User Name' }).fill('someone');
  await page.getByRole('textbox', { name: 'Password' }).fill('not-a-real-password');
  await page.getByRole('button', { name: 'Login' }).click();
  await page.getByRole('link', { name: 'Accounts' }).click();
});
"""


def test_legacy_logged_out_becomes_a_test_keeping_its_login():
    out = normalize_recorded_spec(_LEGACY_LOGGED_OUT, name="recorded flow", requires_auth=False)
    assert out == (
        "import { test, expect } from '@playwright/test';\n"
        "\n"
        "test('recorded flow', async ({ page }) => {\n"
        "  await page.goto('https://app.example.com/#/Login');\n"
        "  await page.getByRole('textbox', { name: 'User Name' }).click();\n"
        "  await page.getByRole('textbox', { name: 'User Name' }).fill('someone');\n"
        "  await page.getByRole('textbox', { name: 'Password' }).click();\n"
        "  await page.getByRole('textbox', { name: 'Password' }).fill('not-a-real-password');\n"
        "  await page.getByRole('button', { name: 'Login' }).click();\n"
        "  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();\n"
        "});\n"
    )
    assert not is_legacy_standalone_script(out)


def test_legacy_authenticated_drops_browser_and_storage_state_plumbing():
    code = uncomment_codegen_assertions(_LEGACY_AUTHENTICATED)
    out = normalize_recorded_spec(code, name="Recorded flow (7)", requires_auth=True)
    assert out == (
        "import { test, expect } from '@playwright/test';\n"
        "\n"
        "test('Recorded flow (7)', async ({ page }) => {\n"
        "  await page.goto('https://app.example.com/Dashboard');\n"
        "  await page.getByRole('link', { name: 'Investments' }).click();\n"
        "  await expect(page.getByRole('main')).toContainText('Portfolio value');\n"
        "});\n"
    )
    assert "storageState" not in out and "chromium" not in out


def test_new_format_drops_test_use_storage_state_and_renames_default_title():
    out = normalize_recorded_spec(_NEW_AUTHENTICATED, name="check balance", requires_auth=True)
    assert "test.use" not in out
    assert "test('check balance', async ({ page }) => {" in out
    assert "await page.goto('https://app.example.com/Dashboard');" in out


def test_auth_strips_recorded_login_and_starts_from_base_url():
    out = normalize_recorded_spec(_NEW_WITH_LOGIN, name="accounts", requires_auth=True)
    assert out == (
        "import { test, expect } from '@playwright/test';\n"
        "\n"
        "test('accounts', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "  await page.getByRole('link', { name: 'Accounts' }).click();\n"
        "});\n"
    )


def test_auth_login_strip_keeps_a_following_goto_instead_of_prepending():
    code = _NEW_WITH_LOGIN.replace(
        "  await page.getByRole('link', { name: 'Accounts' }).click();\n",
        "  await page.goto('https://app.example.com/Accounts');\n",
    )
    out = normalize_recorded_spec(code, name="accounts", requires_auth=True)
    assert "page.goto('/')" not in out
    assert "not-a-real-password" not in out and "someone" not in out
    assert "await page.goto('https://app.example.com/Accounts');" in out


def test_public_keeps_recorded_login():
    out = normalize_recorded_spec(_NEW_WITH_LOGIN, name="login", requires_auth=False)
    assert ".fill('not-a-real-password')" in out


def test_auth_without_a_password_fill_is_untouched():
    out = normalize_recorded_spec(_NEW_AUTHENTICATED, name="x", requires_auth=True)
    assert "page.goto('/')" not in out


@pytest.mark.parametrize(
    ("code", "requires_auth"),
    [(_LEGACY_LOGGED_OUT, False), (_LEGACY_AUTHENTICATED, True), (_NEW_WITH_LOGIN, True)],
)
def test_idempotent(code, requires_auth):
    once = normalize_recorded_spec(code, name="n", requires_auth=requires_auth)
    assert normalize_recorded_spec(once, name="n", requires_auth=requires_auth) == once


def test_auth_tag_finds_the_normalized_test_call():
    out = apply_auth_tag(
        normalize_recorded_spec(_LEGACY_AUTHENTICATED, name="n", requires_auth=True), True
    )
    assert "test('n', { tag: '@auth' }, async ({ page }) => {" in out


def test_title_is_quoted_safely():
    out = normalize_recorded_spec(_NEW_AUTHENTICATED, name="it's a flow", requires_auth=True)
    assert "test('it\\'s a flow', async" in out


@pytest.mark.asyncio
async def test_normalized_legacy_recording_typechecks():
    code = apply_auth_tag(
        normalize_recorded_spec(
            uncomment_codegen_assertions(_LEGACY_AUTHENTICATED), name="n", requires_auth=True
        ),
        True,
    )
    try:
        errors = await typecheck_playwright_code(code)
    except TypecheckUnavailable:
        pytest.skip("typecheck node_modules not installed")
    assert errors == []
