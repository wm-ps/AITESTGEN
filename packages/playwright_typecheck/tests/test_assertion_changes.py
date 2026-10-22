"""`assertion_changes` — self-healing's assertion guard. Runs the real
assertions.js under node (needs `npm install` in ../typecheck, the same
install `typecheck_playwright_code` uses)."""

import asyncio
import os

import pytest
from playwright_typecheck import assertion_changes
from playwright_typecheck.assertions import _TYPESCRIPT_DIR

pytestmark = pytest.mark.skipif(
    not os.path.exists(_TYPESCRIPT_DIR),
    reason="run `npm install` in packages/playwright_typecheck/typecheck",
)

BASE = """import { test, expect } from '@playwright/test';
import { ensureVisible } from '../../support/interactions';

test('submit a claim', async ({ page }) => {
  await page.goto('https://app.example.com/claims');
  const heading = page.getByRole('heading', { name: 'Claims' });
  const submit = await ensureVisible(page.getByRole('button', { name: 'Submit' }));
  await page.getByLabel('Amount').fill('120');
  await submit.click();
  await expect(heading).toBeVisible();
  await expect(page.getByText('Claim submitted')).toHaveText('Claim submitted', { timeout: 15000 });
  await expect(page.getByRole('row')).not.toHaveCount(0);
});
"""


def changes(new: str, old: str = BASE) -> list[str]:
    return asyncio.run(assertion_changes(old, new))


def test_identical_spec_has_no_changes():
    assert changes(BASE) == []


def test_formatting_comments_and_quote_style_are_not_changes():
    reformatted = BASE.replace(
        "await expect(page.getByText('Claim submitted')).toHaveText('Claim submitted', { timeout: 15000 });",
        '// still the same check\n  await expect(\n    page.getByText("Claim submitted"),\n  ).toHaveText(\n'
        '    "Claim submitted",\n    { timeout: 15000, },\n  );',
    )
    assert changes(reformatted) == []


def test_action_only_locator_fix_is_allowed():
    healed = BASE.replace(
        "await page.getByLabel('Amount').fill('120');",
        "await page.getByRole('textbox', { name: 'Claim amount' }).fill('120');",
    ).replace(
        "page.getByRole('button', { name: 'Submit' })",
        "page.getByTestId('submit-claim')",
    )
    assert changes(healed) == []


def test_splitting_an_action_off_a_shared_assertion_variable_is_allowed():
    old = BASE.replace(
        "await submit.click();\n  await expect(heading).toBeVisible();",
        "await heading.click();\n  await expect(heading).toBeVisible();",
    )
    healed = old.replace(
        "await heading.click();",
        "await page.getByRole('heading', { name: 'Claims overview' }).click();",
    )
    assert changes(healed, old) == []


def test_changed_locator_inside_expect_is_reported():
    healed = BASE.replace("page.getByText('Claim submitted'))", "page.getByText('Submitted'))")
    [change] = changes(healed)
    assert change.startswith("assertion 2 changed:")
    assert "Submitted" in change


def test_changed_declaration_of_an_assertion_subject_is_reported():
    healed = BASE.replace(
        "const heading = page.getByRole('heading', { name: 'Claims' });",
        "const heading = page.getByRole('heading', { name: 'My claims' });",
    )
    [change] = changes(healed)
    assert change.startswith("assertion 1 changed:")


def test_changed_declaration_one_hop_back_is_reported():
    old = BASE.replace(
        "const heading = page.getByRole('heading', { name: 'Claims' });",
        "const main = page.locator('main');\n  const heading = main.getByRole('heading', { name: 'Claims' });",
    )
    healed = old.replace("page.locator('main')", "page.locator('#content')")
    assert len(changes(healed, old)) == 1


def test_changed_expected_text_is_reported():
    healed = BASE.replace(
        "toHaveText('Claim submitted', { timeout: 15000 })",
        "toHaveText('Saved', { timeout: 15000 })",
    )
    assert len(changes(healed)) == 1


def test_flipped_not_is_reported():
    healed = BASE.replace(".not.toHaveCount(0)", ".toHaveCount(0)")
    assert len(changes(healed)) == 1


def test_expect_to_expect_soft_is_reported():
    healed = BASE.replace("await expect(heading)", "await expect.soft(heading)")
    assert len(changes(healed)) == 1


def test_changed_timeout_option_is_reported():
    healed = BASE.replace("{ timeout: 15000 }", "{ timeout: 60000 }")
    assert len(changes(healed)) == 1


def test_removed_await_is_reported():
    healed = BASE.replace("await expect(heading).toBeVisible();", "expect(heading).toBeVisible();")
    assert len(changes(healed)) == 1


def test_removed_assertion_is_reported():
    healed = BASE.replace("  await expect(page.getByRole('row')).not.toHaveCount(0);\n", "")
    assert changes(healed) == [
        'assertion removed: await expect ( page . getByRole ( "row" ) ) . not . toHaveCount ( 0 )'
    ]


def test_added_assertion_is_reported():
    healed = BASE.replace(
        "await submit.click();", "await submit.click();\n  await expect(submit).toBeEnabled();"
    )
    [change] = changes(healed)
    assert change.startswith("assertion added:")


def test_matcher_changed_is_reported():
    healed = BASE.replace(
        "await expect(heading).toBeVisible();", "await expect(heading).toBeAttached();"
    )
    assert len(changes(healed)) == 1
