from recording_worker.steps_parser import parse_steps

_SAMPLE_CODEGEN_OUTPUT = """\
import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('https://example.com/login');
  await page.getByLabel('Username').click();
  await page.getByLabel('Username').fill('alice');
  await page.getByLabel('Password').fill('s3cret');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByText('Welcome back')).toBeVisible();
});
"""


def test_parses_navigation_fill_click_and_assertion() -> None:
    steps = parse_steps(_SAMPLE_CODEGEN_OUTPUT)
    assert steps == [
        "Navigate to https://example.com/login",
        "Click 'Username'",
        "Fill in 'alice' into 'Username'",
        "Fill in 's3cret' into 'Password'",
        "Click 'Sign in'",
        "Assert 'Welcome back' is visible",
    ]


def test_unrecognized_action_line_gets_generic_fallback() -> None:
    code = "test('t', async ({ page }) => {\n  await page.mouse.move(1, 2);\n});\n"
    assert parse_steps(code) == ["Perform recorded action"]


def test_non_action_lines_are_skipped() -> None:
    code = "import { test, expect } from '@playwright/test';\nconst x = 1;\n"
    assert parse_steps(code) == []


def test_empty_code_produces_no_steps() -> None:
    assert parse_steps("") == []
