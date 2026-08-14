"""spec_linter — pure regex/logic unit tests (no DB; the DB-touching helpers
`resolve_requires_auth`/`required_fields_for_page` are exercised indirectly
via `test_playwright_generation_activity.py`)."""

from generation_worker.spec_linter import (
    apply_auth_tag,
    extract_locator_usages,
    lint_locator_provenance,
    lint_required_fields,
    lint_sibling_consistency,
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


def test_lint_uses_shared_auth_helper_flags_missing_helper_when_required() -> None:
    warnings = lint_uses_shared_auth_helper("test('x', async ({ page }) => {})", True)
    assert len(warnings) == 1


def test_lint_uses_shared_auth_helper_passes_when_not_required() -> None:
    assert lint_uses_shared_auth_helper("test('x', async ({ page }) => {})", False) == []


def test_lint_uses_shared_auth_helper_passes_when_helper_used() -> None:
    code = (
        "import { fillCredentials } from '../support/auth'\n"
        "test('x', async ({ page }) => { await fillCredentials(page); })\n"
    )
    assert lint_uses_shared_auth_helper(code, True) == []


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
