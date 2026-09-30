import pytest
from playwright_typecheck import TypecheckUnavailable, typecheck_playwright_code

from recording_worker.assertion_uncomment import uncomment_codegen_assertions

# Standalone/library format — the real shape `codegen_session.py`'s own
# `--target javascript` flag produces (confirmed against a real persisted
# recording), never the `@playwright/test` `test(...)` format.
_CODE_WITH_COMMENTED_VISIBLE_ASSERTION = """\
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: false
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://example.com');
  // await expect(page.getByText('Welcome')).toBeVisible();
  await context.close();
  await browser.close();
})();
"""

_CODE_WITH_HUMAN_COMMENT = """\
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: false
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  // TODO: replace this selector once the redesign ships
  await page.getByRole('button', { name: 'Submit' }).click();
  await context.close();
  await browser.close();
})();
"""

_CODE_WITH_TODO_MENTIONING_EXPECT = """\
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  // TODO: await expect(page.getByText('X')).toBeVisible();
  await page.getByRole('button').click();
  await context.close();
  await browser.close();
})();
"""

_CODE_WITH_MULTIPLE_COMMENTED_ASSERTIONS = """\
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: false
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://example.com');
  // await expect(page.getByText('Welcome')).toBeVisible();
  // await expect(page.getByText('Old banner')).not.toBeVisible();
  // await expect(page.getByRole('heading')).toHaveText('Dashboard');
  // await expect(page.getByLabel('Email')).toHaveValue('alice@example.com');
  // await expect(page.getByRole('checkbox')).toBeChecked();
  // await expect(page).toHaveTitle('Dashboard');
  // await expect(page).toHaveURL('https://example.com/dashboard');
  await context.close();
  await browser.close();
})();
"""


def test_a_commented_codegen_assertion_becomes_an_active_statement() -> None:
    result = uncomment_codegen_assertions(_CODE_WITH_COMMENTED_VISIBLE_ASSERTION)
    assert "  await expect(page.getByText('Welcome')).toBeVisible();" in result.splitlines()
    assert "// await expect(page.getByText('Welcome')).toBeVisible();" not in result


def test_uncommenting_an_assertion_adds_an_expect_require_line() -> None:
    result = uncomment_codegen_assertions(_CODE_WITH_COMMENTED_VISIBLE_ASSERTION)
    lines = result.splitlines()
    browser_require_index = lines.index("const { chromium } = require('playwright');")
    assert lines[browser_require_index + 1] == "const { expect } = require('@playwright/test');"
    assert result.count("require('@playwright/test')") == 1


def test_a_normal_human_comment_is_left_untouched() -> None:
    result = uncomment_codegen_assertions(_CODE_WITH_HUMAN_COMMENT)
    assert result == _CODE_WITH_HUMAN_COMMENT
    assert "@playwright/test" not in result


def test_a_human_comment_that_merely_mentions_expect_is_not_uncommented() -> None:
    result = uncomment_codegen_assertions(_CODE_WITH_TODO_MENTIONING_EXPECT)
    assert result == _CODE_WITH_TODO_MENTIONING_EXPECT
    assert "@playwright/test" not in result


def test_multiple_assertions_of_different_matcher_types_are_all_activated() -> None:
    result = uncomment_codegen_assertions(_CODE_WITH_MULTIPLE_COMMENTED_ASSERTIONS)
    for line in result.splitlines():
        assert not line.strip().startswith("//")
    assert result.count("await expect(") == 7
    # Exactly one require line added, not one per activated assertion.
    assert result.count("require('@playwright/test')") == 1


async def test_the_uncommented_output_passes_the_playwright_typecheck_gate() -> None:
    processed = uncomment_codegen_assertions(_CODE_WITH_COMMENTED_VISIBLE_ASSERTION)
    try:
        errors = await typecheck_playwright_code(processed)
    except TypecheckUnavailable:
        pytest.skip("typecheck/node_modules not installed")
    assert errors == []
