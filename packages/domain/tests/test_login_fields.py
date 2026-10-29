import pytest
from domain.login_fields import (
    is_generated_login_field,
    is_login_scenario,
    is_password_name,
    is_saved_credential_value,
    visible_fields,
)


@pytest.mark.parametrize(
    "scenario_name",
    [
        "Login with valid credentials",
        "Sign in as an existing user",
        "Log in and open the dashboard",
    ],
)
def test_login_scenario_email_is_a_login_field(scenario_name: str) -> None:
    assert is_generated_login_field("Email", scenario_name, [scenario_name])
    assert is_generated_login_field("User ID", scenario_name, [scenario_name])


@pytest.mark.parametrize(
    "scenario_name",
    [
        "Register a new account",
        "Sign up with a valid email",
        "Submit the contact form",
        "Reset password from the login page",
        "Forgot password sends a reset link",
        "Update profile email",
    ],
)
def test_signup_contact_reset_and_profile_email_stay_editable(scenario_name: str) -> None:
    assert not is_generated_login_field("Email", scenario_name, [scenario_name])


@pytest.mark.parametrize(
    "scenario_name",
    [
        "Login with an invalid email format",
        "Login with an unregistered email",
        "Sign in with a wrong email",
        "Login with an empty email",
    ],
)
def test_negative_login_values_stay_editable(scenario_name: str) -> None:
    assert not is_generated_login_field("Email", scenario_name, [scenario_name])


def test_negative_wording_about_a_sibling_field_does_not_spare_this_one() -> None:
    segments = ["Login with a wrong password", "Enter the Email", "Enter a wrong password"]
    assert is_generated_login_field("Email", "Login with a wrong password", segments)


def test_new_and_confirm_fields_are_never_login_fields() -> None:
    assert not is_generated_login_field("New email", "Login after changing email", ["x"])
    assert not is_generated_login_field("Confirm email", "Sign in", ["Sign in"])


def test_login_scenario_non_identity_field_stays_editable() -> None:
    assert not is_generated_login_field("Amount", "Login and transfer funds", ["x"])


def test_login_scenario_words() -> None:
    assert is_login_scenario("Authenticate with SSO")
    assert is_login_scenario("Sign-in with saved credentials")
    assert not is_login_scenario("Create an account")
    assert not is_login_scenario("View the dashboard")


def test_password_name_is_not_passport_or_spinbutton() -> None:
    assert is_password_name("Password")
    assert is_password_name("Passcode")
    assert is_password_name("PIN")
    assert not is_password_name("Passport number")
    assert not is_password_name("spinbutton")


def test_saved_credential_placeholders() -> None:
    assert is_saved_credential_value("{{username}}")
    assert is_saved_credential_value("{{password}}")
    assert not is_saved_credential_value("someone@example.com")
    assert not is_saved_credential_value(None)


def test_visible_fields_drop_only_marked_fields() -> None:
    fields = [
        {"name": "Email", "mandatory": True, "value": "a", "login": True},
        {"name": "Amount", "mandatory": True, "value": "5"},
    ]
    assert visible_fields(fields) == [fields[1]]


@pytest.mark.parametrize(
    "label",
    [
        "Email",
        "E-mail address",
        "Username",
        "User Name",
        "User ID",
        "Login",
        "Login ID",
        "Email or username",
        "user_name",
        "Your email",
    ],
)
def test_identity_labels(label: str) -> None:
    from domain.login_fields import is_login_identity_name

    assert is_login_identity_name(label)


@pytest.mark.parametrize(
    "label",
    [
        "expired or unauthenticated login-status response",
        "Email subject",
        "Login attempts",
        "Amount",
        "Recipient email list",
    ],
)
def test_labels_that_only_mention_login_or_email(label: str) -> None:
    from domain.login_fields import is_login_identity_name

    assert not is_login_identity_name(label)
