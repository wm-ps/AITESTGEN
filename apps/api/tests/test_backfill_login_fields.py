"""The login-field backfill only ever adds `"login": true` — values, names
and order stay as stored."""

from api.backfill_login_fields import marked_fields

_LOGIN_CODE = (
    "test('t', { tag: '@public' }, async ({ page }) => {\n"
    "  await page.getByLabel('Email').fill('me@corp.test');\n"
    "  await page.getByLabel('Password').fill('pw');\n"
    "  await page.getByRole('button', { name: 'Sign in' }).click();\n"
    "  await page.getByLabel('Amount').fill('5');\n"
    "});\n"
)


def _kwargs(**overrides):
    base = {
        "source": "discovery",
        "is_explorer": False,
        "name": "x",
        "steps": [],
        "expected_result": "",
        "code": None,
    }
    return {**base, **overrides}


def test_recorded_marks_login_and_keeps_stored_values() -> None:
    stored = [
        {"name": "Email", "mandatory": True, "value": "edited@corp.test"},
        {"name": "Amount", "mandatory": True, "value": "9"},
    ]
    after = marked_fields(stored, **_kwargs(source="recorded", code=_LOGIN_CODE))
    assert after == [{**stored[0], "login": True}, stored[1]]


def test_recorded_out_of_step_with_code_is_skipped() -> None:
    stored = [{"name": "Memo", "mandatory": True, "value": "x"}]
    assert marked_fields(stored, **_kwargs(source="recorded", code=_LOGIN_CODE)) is None


def test_explorer_marks_only_saved_credential_placeholders() -> None:
    stored = [
        {"name": "Username", "mandatory": True, "value": "{{username}}"},
        {"name": "Search", "mandatory": True, "value": "invoices"},
    ]
    after = marked_fields(stored, **_kwargs(is_explorer=True))
    assert [f.get("login") for f in after or []] == [True, None]


def test_generated_login_scenario_marks_email_but_signup_does_not() -> None:
    stored = [{"name": "Email", "mandatory": True, "value": None}]
    login = marked_fields(stored, **_kwargs(name="Login with valid credentials"))
    signup = marked_fields(stored, **_kwargs(name="Sign up with a new account"))
    assert login == [{**stored[0], "login": True}]
    assert signup == stored
