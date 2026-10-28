import pytest
from domain.recorded_test_data import (
    RecordedFieldsChanged,
    extract_recorded_test_data,
    find_recorded_inputs,
    swap_recorded_values,
    update_recorded_steps,
)

# A logged-out recording, as Codegen writes it: username, password, then an
# amount typed twice (Codegen records a correction as a second fill).
PUBLIC_LOGIN = """import { test, expect } from '@playwright/test';

test('transfer', { tag: '@public' }, async ({ page }) => {
  await page.goto('https://app.example.com/Login');
  await page.getByRole('textbox', { name: 'User Name' }).fill('someone');
  await page.getByRole('textbox', { name: 'Password' }).fill('s3cret-pw');
  await page.getByRole('button', { name: 'Login' }).click();
  await page.getByRole('spinbutton', { name: 'Amount (USD)' }).fill('0.01');
  await page.getByRole('spinbutton', { name: 'Amount (USD)' }).fill('11111');
  await page.getByLabel('From account').selectOption('2cd420ff-b31d-4a1b-a378-08a5487c47fe');
});
"""

# The same kind of flow after a heal rewrote it: locators in variables,
# calls split across lines, a password held in a variable defined earlier.
HEALED = """import { test, expect } from '@playwright/test';
import { ensureVisible } from '../../support/interactions';

test('healed', { tag: '@public' }, async ({ page }) => {
  const userField = page.getByRole('textbox', {
    name: 'User Name',
    exact: true,
  });
  const pw = page.getByLabel('Password');
  const amountInput = await ensureVisible(
    page.getByRole('spinbutton', { name: 'Amount (USD)' }),
  );
  await userField.fill('someone');
  await pw.fill('s3cret-pw');
  await amountInput
    .fill('500');
  await page.locator('#txtPassword').fill('again-secret');
  await page.locator('#cover-amount').fill('20000');
});
"""


def _password_literal(code: str) -> str:
    start = code.index("'s3cret-pw'")
    return code[start : start + len("'s3cret-pw'")]


class TestExtract:
    def test_fields_in_code_order_with_deduped_names_and_no_password(self) -> None:
        assert extract_recorded_test_data(PUBLIC_LOGIN) == [
            {"name": "User Name", "mandatory": True, "value": "someone"},
            {"name": "Amount (USD)", "mandatory": True, "value": "0.01"},
            {"name": "Amount (USD) (2)", "mandatory": True, "value": "11111"},
        ]

    def test_select_option_is_not_a_field(self) -> None:
        names = [f["name"] for f in extract_recorded_test_data(PUBLIC_LOGIN)]
        assert "From account" not in names

    def test_healed_code_variables_and_split_calls(self) -> None:
        assert extract_recorded_test_data(HEALED) == [
            {"name": "User Name", "mandatory": True, "value": "someone"},
            {"name": "Amount (USD)", "mandatory": True, "value": "500"},
            {"name": "Cover amount", "mandatory": True, "value": "20000"},
        ]
        passwords = [i.value for i in find_recorded_inputs(HEALED) if i.is_password]
        assert passwords == ["s3cret-pw", "again-secret"]

    @pytest.mark.parametrize(
        "locator",
        [
            "page.getByLabel('Passcode')",
            "page.getByRole('textbox', { name: 'PIN' })",
            "page.locator('[name=\"passwd\"]')",
            "page.getByPlaceholder('Enter your password')",
        ],
    )
    def test_password_like_fields_are_skipped(self, locator: str) -> None:
        code = f"test('t', async ({{ page }}) => {{\n  await {locator}.fill('x1');\n}});\n"
        assert extract_recorded_test_data(code) == []

    def test_spinbutton_is_not_a_pin_and_typed_password_word_stays_editable(self) -> None:
        code = (
            "test('t', async ({ page }) => {\n"
            "  await page.getByRole('spinbutton', { name: 'Qty' }).fill('2');\n"
            "  await page.getByRole('searchbox', { name: 'Search' }).fill('password reset');\n"
            "});\n"
        )
        assert [f["value"] for f in extract_recorded_test_data(code)] == ["2", "password reset"]

    def test_empty_fill_is_an_optional_field_and_non_literals_are_not_fields(self) -> None:
        code = (
            "test('t', async ({ page }) => {\n"
            "  await page.getByLabel('Note').fill('');\n"
            "  await page.getByLabel('Ref').fill(`ref-${Date.now()}`);\n"
            "  await page.getByLabel('Code').fill('A' + suffix);\n"
            "  await page.getByLabel('City').type('Paris');\n"
            "  await page.getByLabel('Town').pressSequentially('Lyon');\n"
            "});\n"
        )
        assert extract_recorded_test_data(code) == [
            {"name": "Note", "mandatory": False, "value": ""},
            {"name": "City", "mandatory": True, "value": "Paris"},
            {"name": "Town", "mandatory": True, "value": "Lyon"},
        ]

    def test_escaped_literal_is_decoded(self) -> None:
        code = "test('t', async ({ page }) => {\n  await page.getByLabel('Name').fill('O\\'Brien');\n});\n"
        assert extract_recorded_test_data(code)[0]["value"] == "O'Brien"

    def test_clicks_only_yields_no_fields(self) -> None:
        code = (
            "test('t', { tag: '@auth' }, async ({ page }) => {\n"
            "  await page.getByRole('link', { name: 'Job Requests' }).click();\n"
            "  await expect(page.getByRole('heading', { name: 'Job Requests' })).toBeVisible();\n"
            "});\n"
        )
        assert extract_recorded_test_data(code) == []


class TestSwap:
    def test_only_the_targeted_literal_changes(self) -> None:
        fields = extract_recorded_test_data(PUBLIC_LOGIN)
        fields[2]["value"] = "500"

        new_code, changes = swap_recorded_values(PUBLIC_LOGIN, fields)

        assert new_code == PUBLIC_LOGIN.replace("fill('11111')", "fill('500')")
        assert changes == [("11111", "500")]

    def test_editing_username_or_amount_never_touches_the_password(self) -> None:
        for index in (0, 1):
            fields = extract_recorded_test_data(PUBLIC_LOGIN)
            fields[index]["value"] = "changed"

            new_code, _ = swap_recorded_values(PUBLIC_LOGIN, fields)

            assert _password_literal(new_code) == "'s3cret-pw'"
            assert new_code.count("fill('s3cret-pw')") == 1
            assert new_code.count("'changed'") == 1

    def test_healed_code_swaps_by_order_and_keeps_passwords(self) -> None:
        fields = extract_recorded_test_data(HEALED)
        fields[0]["value"] = "other-user"
        fields[1]["value"] = "750"

        new_code, changes = swap_recorded_values(HEALED, fields)

        assert "userField.fill('other-user')" in new_code
        assert ".fill('750')" in new_code
        assert "pw.fill('s3cret-pw')" in new_code
        assert "fill('again-secret')" in new_code
        assert changes == [("someone", "other-user"), ("500", "750")]

    def test_quotes_and_backslashes_round_trip(self) -> None:
        fields = extract_recorded_test_data(PUBLIC_LOGIN)
        fields[0]["value"] = "O'Brien \\ co\nline"

        new_code, _ = swap_recorded_values(PUBLIC_LOGIN, fields)

        assert extract_recorded_test_data(new_code)[0]["value"] == "O'Brien \\ co\nline"

    def test_unchanged_values_return_identical_code(self) -> None:
        new_code, changes = swap_recorded_values(
            PUBLIC_LOGIN, extract_recorded_test_data(PUBLIC_LOGIN)
        )
        assert new_code == PUBLIC_LOGIN
        assert changes == []

    def test_cleared_value_keeps_the_mapping_stable(self) -> None:
        fields = extract_recorded_test_data(PUBLIC_LOGIN)
        fields[1]["value"] = ""
        cleared, _ = swap_recorded_values(PUBLIC_LOGIN, fields)

        fields[2]["value"] = "9"
        again, _ = swap_recorded_values(cleared, fields)

        assert "fill('')" in again and "fill('9')" in again

    def test_changed_typed_call_count_raises(self) -> None:
        fields = extract_recorded_test_data(PUBLIC_LOGIN)
        healed_away = PUBLIC_LOGIN.replace(
            "  await page.getByRole('spinbutton', { name: 'Amount (USD)' }).fill('0.01');\n", ""
        )
        with pytest.raises(RecordedFieldsChanged):
            swap_recorded_values(healed_away, fields)


def test_update_recorded_steps_rewrites_changed_fill_chips_in_order() -> None:
    steps = [
        "Navigate to https://app.example.com",
        "Fill in '1' into 'Qty'",
        "Click 'Add'",
        "Fill in '1' into 'Qty'",
    ]
    assert update_recorded_steps(steps, [("1", "5")]) == [
        "Navigate to https://app.example.com",
        "Fill in '5' into 'Qty'",
        "Click 'Add'",
        "Fill in '1' into 'Qty'",
    ]
    assert update_recorded_steps(steps, [("1", "5"), ("1", "6")])[3] == "Fill in '6' into 'Qty'"
    assert update_recorded_steps(steps, [("missing", "x")]) == steps
