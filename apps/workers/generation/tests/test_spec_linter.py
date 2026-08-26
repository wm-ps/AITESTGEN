"""spec_linter — pure regex/logic unit tests (no DB; the DB-touching helpers
`resolve_requires_auth`/`required_fields_for_pages` are exercised indirectly
via `test_playwright_generation_activity.py`)."""

from generation_worker.spec_linter import (
    apply_auth_tag,
    extract_locator_usages,
    lint_asserted_data_not_entered,
    lint_locator_provenance,
    lint_password_boundary_ignored,
    lint_required_fields,
    lint_scenario_data_intent,
    lint_shared_state_contradiction,
    lint_sibling_consistency,
    lint_tautological_assertion,
    lint_ungrounded_error_container_assertion,
    lint_uses_shared_auth_helper,
)


def test_extract_locator_usages_covers_every_call_type() -> None:
    code = (
        "await page.getByRole('button', { name: 'Sign In' }).click();\n"
        "await page.getByLabel('Email').fill('x');\n"
        "await page.locator('#save-btn').click();\n"
    )
    usages = extract_locator_usages(code)
    assert ("getByRole:button", "Sign In") in {(u.call, u.value) for u in usages}
    assert ("getByLabel", "Email") in {(u.call, u.value) for u in usages}
    assert ("locator", "#save-btn") in {(u.call, u.value) for u in usages}


def test_extract_locator_usages_skips_regex_arguments() -> None:
    code = "await page.getByRole('link', { name: /Health Plan/ }).click();\n"
    assert extract_locator_usages(code) == []


def test_lint_locator_provenance_flags_unmatched_accessible_name() -> None:
    known_locators = [
        {"strategy": "aria", "selector": 'role=button[name="Sign In"]'},
    ]
    code = "await page.getByRole('button', { name: 'Log In' }).click();\n"
    warnings = lint_locator_provenance(code, known_locators)
    assert len(warnings) == 1
    assert "Log In" in warnings[0]


def test_lint_locator_provenance_passes_when_name_matches() -> None:
    known_locators = [{"strategy": "label", "selector": "Email"}]
    code = "await page.getByLabel('Email').fill('x');\n"
    assert lint_locator_provenance(code, known_locators) == []


def test_lint_locator_provenance_skips_raw_locator_calls() -> None:
    known_locators = [{"strategy": "aria", "selector": 'role=button[name="Sign In"]'}]
    code = "await page.locator('input[name=\"password\"]').fill('x');\n"
    assert lint_locator_provenance(code, known_locators) == []


def test_lint_required_fields_flags_a_missing_required_field() -> None:
    code = "await page.locator('#username').fill('x');\n"
    warnings = lint_required_fields(code, {"username": True, "password": True})
    assert len(warnings) == 1
    assert "password" in warnings[0]


def test_lint_required_fields_ignores_optional_fields() -> None:
    code = "await page.locator('#username').fill('x');\n"
    assert lint_required_fields(code, {"username": True, "promo_code": False}) == []


def test_lint_uses_shared_auth_helper_passes_when_not_called_and_required() -> None:
    # requires_auth=True means storageState already authenticates this spec
    # before its body runs — the correct spec never touches fillCredentials.
    assert lint_uses_shared_auth_helper("test('x', async ({ page }) => {})", True) == []


def test_lint_uses_shared_auth_helper_passes_when_not_required_and_not_called() -> None:
    assert lint_uses_shared_auth_helper("test('x', async ({ page }) => {})", False) == []


def test_lint_uses_shared_auth_helper_passes_when_helper_used_and_not_required() -> None:
    # A spec that IS itself testing the login form (requires_auth=False,
    # since its primary page is the login page) may legitimately call the
    # helper.
    code = (
        "import { fillCredentials } from '../../support/auth'\n"
        "test('x', async ({ page }) => { await fillCredentials(page); })\n"
    )
    assert lint_uses_shared_auth_helper(code, False) == []


def test_lint_uses_shared_auth_helper_flags_redundant_helper_when_already_authenticated() -> None:
    code = (
        "import { fillCredentials } from '../../support/auth'\n"
        "test('x', async ({ page }) => { await fillCredentials(page); })\n"
    )
    warnings = lint_uses_shared_auth_helper(code, True)
    assert len(warnings) == 1
    assert "fillCredentials" in warnings[0]


def test_lint_sibling_consistency_flags_a_missing_locator() -> None:
    new_code = "await page.getByLabel('Email').fill('x');\n"
    sibling_code = (
        "await page.getByLabel('Email').fill('x');\n"
        "await page.getByLabel('Password').fill('y');\n"
    )
    warnings = lint_sibling_consistency(new_code, sibling_code)
    assert len(warnings) == 1
    assert "password" in warnings[0].lower()


def test_lint_sibling_consistency_flags_a_differing_strategy() -> None:
    new_code = "await page.getByRole('button', { name: 'Sign In' }).click();\n"
    sibling_code = "await page.getByLabel('Sign In').click();\n"
    # Different call type ("getByLabel" vs "getByRole:button") for text that
    # is only equal after lowercasing ("Sign In" both) — same value, split call type.
    warnings = lint_sibling_consistency(new_code, sibling_code)
    assert any("locator strategy" in w for w in warnings)


def test_lint_sibling_consistency_passes_when_identical() -> None:
    code = "await page.getByLabel('Email').fill('x');\n"
    assert lint_sibling_consistency(code, code) == []


def test_apply_auth_tag_inserts_tag_into_test_call() -> None:
    code = "test('login', async ({ page }) => {})\n"
    tagged = apply_auth_tag(code, True)
    assert "{ tag: '@auth' }" in tagged
    assert "test('login', { tag: '@auth' }, async" in tagged


def test_apply_auth_tag_uses_public_tag_when_not_required() -> None:
    tagged = apply_auth_tag("test('x', async ({ page }) => {})\n", False)
    assert "{ tag: '@public' }" in tagged


def test_apply_auth_tag_overrides_an_existing_tag() -> None:
    code = "test('x', { tag: '@public' }, async ({ page }) => {})\n"
    tagged = apply_auth_tag(code, True)
    assert "@auth" in tagged


def test_apply_auth_tag_is_a_noop_when_no_test_call_found() -> None:
    code = "// no test call here\n"
    assert apply_auth_tag(code, True) == code


def test_apply_auth_tag_strips_an_llm_baked_in_tag_from_the_name() -> None:
    code = "test('Session expires while opening accounts @auth', async ({ page }) => {})\n"
    tagged = apply_auth_tag(code, False)
    assert "{ tag: '@public' }" in tagged
    assert "@auth" not in tagged
    assert "test('Session expires while opening accounts', { tag: '@public' }, async" in tagged


def test_lint_scenario_data_intent_flags_unicode_scenario_with_ascii_only_data() -> None:
    warnings = lint_scenario_data_intent(
        "Sign in with a Unicode password",
        ["Enter username", "Enter password", "Submit"],
        [
            {"name": "username", "value": "bob"},
            {"name": "password", "value": "Password123"},
        ],
    )
    assert len(warnings) == 1
    assert "Unicode" in warnings[0]


def test_lint_scenario_data_intent_passes_when_unicode_actually_present() -> None:
    warnings = lint_scenario_data_intent(
        "Sign in with a Unicode password",
        ["Enter username", "Enter password"],
        [
            {"name": "username", "value": "bob"},
            {"name": "password", "value": "Pässwörd☺123"},
        ],
    )
    assert warnings == []


def test_lint_scenario_data_intent_ignores_scenarios_with_no_fields() -> None:
    # A read-only scenario whose name happens to mention "date" but has no
    # test_data to validate must not be flagged.
    assert lint_scenario_data_intent("Verify transaction date is displayed", [], []) == []


def test_lint_scenario_data_intent_flags_numeric_scenario_with_placeholder_value() -> None:
    warnings = lint_scenario_data_intent(
        "Enter a numeric quantity",
        ["Enter quantity"],
        [{"name": "quantity", "value": "Test value"}],
    )
    assert len(warnings) == 1
    assert "numeric" in warnings[0]


def test_lint_scenario_data_intent_passes_for_unrelated_scenario() -> None:
    warnings = lint_scenario_data_intent(
        "Update profile name",
        ["Enter name", "Save"],
        [{"name": "name", "value": "Test value"}],
    )
    assert warnings == []


def test_lint_scenario_data_intent_does_not_treat_boundary_length_as_numeric() -> None:
    # "boundary-length" is a string-length property, not a numeric one —
    # a bare "boundary" trigger previously false-positived on this even
    # though no field here needs to be numeric at all.
    warnings = lint_scenario_data_intent(
        "Profile containing boundary-length and Unicode details",
        [],
        [
            {"name": "maximum-length profile values", "value": "x" * 128},
            {"name": "Unicode profile values", "value": "こんにちは 你好"},
        ],
    )
    assert not any("numeric" in w for w in warnings)


def test_lint_tautological_assertion_flags_not_toBe_fallback() -> None:
    code = (
        "if (before !== after) {\n"
        "  expect(before).not.toBe(after);\n"
        "}\n"
    )
    warnings = lint_tautological_assertion(code)
    assert len(warnings) == 1
    assert "tautological" in warnings[0]


def test_lint_tautological_assertion_flags_toBe_mirror() -> None:
    code = "if (a === b) { expect(a).toBe(b); }\n"
    warnings = lint_tautological_assertion(code)
    assert len(warnings) == 1


def test_lint_tautological_assertion_passes_for_real_assertions() -> None:
    code = "await expect(page.locator('#balance')).toHaveText('$100.00');\n"
    assert lint_tautological_assertion(code) == []


def test_lint_shared_state_contradiction_flags_differing_counts_same_locator() -> None:
    code = "await expect(page.locator('.deposit-row')).toHaveCount(1);\n"
    sibling_code = "await expect(page.locator('.deposit-row')).toHaveCount(0);\n"
    warnings = lint_shared_state_contradiction(code, sibling_code)
    assert len(warnings) == 1
    assert "'.deposit-row'" in warnings[0]


def test_lint_shared_state_contradiction_passes_when_counts_agree() -> None:
    code = "await expect(page.locator('.deposit-row')).toHaveCount(1);\n"
    assert lint_shared_state_contradiction(code, code) == []


def test_lint_shared_state_contradiction_ignores_unrelated_locators() -> None:
    code = "await expect(page.locator('.deposit-row')).toHaveCount(1);\n"
    sibling_code = "await expect(page.locator('.withdrawal-row')).toHaveCount(0);\n"
    assert lint_shared_state_contradiction(code, sibling_code) == []


def test_lint_scenario_data_intent_flags_markup_scenario_with_plain_text() -> None:
    warnings = lint_scenario_data_intent(
        "Subject with markup-like characters",
        ["Enter subject"],
        [{"name": "subject", "value": "Test value"}],
    )
    assert len(warnings) == 1
    assert "markup" in warnings[0]


def test_lint_scenario_data_intent_passes_markup_scenario_with_markup_chars() -> None:
    warnings = lint_scenario_data_intent(
        "Subject with markup-like characters",
        ["Enter subject"],
        [{"name": "subject", "value": "<test>&\"'</test>"}],
    )
    assert warnings == []


def test_lint_scenario_data_intent_does_not_falsely_flag_ascii_markup_as_missing_unicode() -> None:
    # "special character" used to also trigger the unicode check, which
    # would false-positive on a correct, pure-ASCII markup value.
    warnings = lint_scenario_data_intent(
        "Special character handling",
        [],
        [{"name": "comment", "value": "<div>&\"'</div>"}],
    )
    assert warnings == []


def test_lint_password_boundary_ignored_flags_bare_fill_credentials() -> None:
    warnings = lint_password_boundary_ignored(
        "Sign in with a Unicode password",
        ["Enter credentials"],
        [{"name": "password", "value": "Pässwörd123$"}],
        "await fillCredentials(page);",
    )
    assert len(warnings) == 1
    assert "fillCredentials(page)" in warnings[0]


def test_lint_password_boundary_ignored_passes_when_value_is_passed_explicitly() -> None:
    warnings = lint_password_boundary_ignored(
        "Sign in with a Unicode password",
        ["Enter credentials"],
        [{"name": "password", "value": "Pässwörd123$"}],
        "await fillCredentials(page, CREDENTIALS.username, 'Pässwörd123$');",
    )
    assert warnings == []


def test_lint_password_boundary_ignored_ignores_unrelated_scenarios() -> None:
    warnings = lint_password_boundary_ignored(
        "Sign in with valid credentials",
        ["Enter credentials"],
        [{"name": "password", "value": "Password1$"}],
        "await fillCredentials(page);",
    )
    assert warnings == []


def test_lint_password_boundary_ignored_skips_when_no_password_value_present() -> None:
    warnings = lint_password_boundary_ignored(
        "Maximum-length password",
        [],
        [{"name": "password", "value": None}],
        "await fillCredentials(page);",
    )
    assert warnings == []


def test_lint_asserted_data_not_entered_flags_a_never_filled_card_number() -> None:
    code = (
        "test('Review card details', async ({ page }) => {\n"
        "  await expect(page.getByText('4111111111111111')).toBeVisible();\n"
        "});\n"
    )
    warnings = lint_asserted_data_not_entered(
        code, [{"name": "cardNumber", "value": "4111111111111111", "mandatory": True}]
    )
    assert len(warnings) == 1
    assert "4111111111111111" in warnings[0]


def test_lint_asserted_data_not_entered_passes_when_value_was_filled_first() -> None:
    code = (
        "test('Update nickname', async ({ page }) => {\n"
        "  await page.locator('#nickname').fill('MyTravelCard');\n"
        "  await expect(page.getByText('MyTravelCard')).toBeVisible();\n"
        "});\n"
    )
    warnings = lint_asserted_data_not_entered(
        code, [{"name": "nickname", "value": "MyTravelCard", "mandatory": True}]
    )
    assert warnings == []


def test_lint_asserted_data_not_entered_ignores_values_never_asserted() -> None:
    code = "test('Fill form', async ({ page }) => {\n  await page.locator('#x').fill('abc123');\n});\n"
    warnings = lint_asserted_data_not_entered(
        code, [{"name": "field", "value": "abc123", "mandatory": True}]
    )
    assert warnings == []


def test_lint_asserted_data_not_entered_ignores_scenarios_with_no_test_data() -> None:
    code = "await expect(page.getByText('4111111111111111')).toBeVisible();\n"
    assert lint_asserted_data_not_entered(code, []) == []


def test_lint_ungrounded_error_container_assertion_flags_hard_toBeVisible() -> None:
    code = (
        "const errorOrNotification = page.locator(\n"
        "  '[role=\"alert\"]:visible, .error:visible, [aria-live]:visible',\n"
        ").first();\n"
        "await expect(errorOrNotification).toBeVisible({ timeout: ASSERTION_TIMEOUT_MS });\n"
    )
    warnings = lint_ungrounded_error_container_assertion(code)
    assert len(warnings) == 1
    assert "errorOrNotification" in warnings[0]


def test_lint_ungrounded_error_container_assertion_flags_joined_array_variant() -> None:
    code = (
        "const errorState = page\n"
        "  .locator(\n"
        "    [\n"
        "      '[role=\"alert\"]',\n"
        "      '[aria-live=\"assertive\"]',\n"
        "    ].join(', '),\n"
        "  )\n"
        "  .locator(':visible')\n"
        "  .first();\n"
        "await expect(errorState).toBeVisible({ timeout: ASSERTION_TIMEOUT_MS });\n"
    )
    warnings = lint_ungrounded_error_container_assertion(code)
    assert len(warnings) == 1
    assert "errorState" in warnings[0]


def test_lint_ungrounded_error_container_assertion_passes_for_soft_check() -> None:
    code = (
        "const errorContainer = page.locator('[role=\"alert\"], .error, [aria-live]').first();\n"
        "if (await errorContainer.count() === 0) {\n"
        "  console.warn('No generic error container found.');\n"
        "}\n"
    )
    assert lint_ungrounded_error_container_assertion(code) == []


def test_lint_ungrounded_error_container_assertion_ignores_unrelated_locators() -> None:
    code = (
        "const saveButton = page.locator('button[type=\"submit\"]');\n"
        "await expect(saveButton).toBeVisible({ timeout: ASSERTION_TIMEOUT_MS });\n"
    )
    assert lint_ungrounded_error_container_assertion(code) == []
