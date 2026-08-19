"""Checklist rule 6 (test-data distinctness): `_default_test_data_value` must
never hand out the same placeholder twice within one scenario — a
confirm-mismatch/before-after scenario needs genuinely distinct literals, not
one canonical placeholder reused for every same-shaped field. Pure logic, no
DB needed.
"""

from generation_worker.activities import (
    _default_test_data_value,
    _is_existing_credential_field,
    _scenario_intent_default_value,
)


def test_second_password_field_gets_a_distinct_value() -> None:
    used: set[str] = set()
    password = _default_test_data_value("password", used)
    used.add(password)
    confirm_password = _default_test_data_value("confirmPassword", used)

    assert confirm_password != password


def test_third_password_field_still_gets_a_distinct_value() -> None:
    used: set[str] = set()
    for field_name in ("password", "confirmPassword", "newPassword"):
        value = _default_test_data_value(field_name, used)
        assert value not in used
        used.add(value)


def test_unrelated_field_names_are_unaffected() -> None:
    used: set[str] = set()
    assert _default_test_data_value("comment", used) == "Test value"
    assert _default_test_data_value("email", used) == "test@example.com"


def test_number_input_type_gets_a_numeric_default_even_with_an_unmatched_name() -> None:
    used: set[str] = set()
    assert _default_test_data_value("age", used, "number") == "1"


def test_date_input_type_gets_a_date_like_default() -> None:
    used: set[str] = set()
    assert _default_test_data_value("dob", used, "date") == "2026-01-01"


def test_tel_input_type_gets_a_phone_like_default() -> None:
    used: set[str] = set()
    assert _default_test_data_value("contact", used, "tel") == "555-0100"


def test_name_pattern_still_takes_precedence_over_input_type() -> None:
    used: set[str] = set()
    assert _default_test_data_value("password", used, "number") == "Password1$"


def test_second_number_field_gets_a_distinct_numeric_value() -> None:
    used: set[str] = set()
    first = _default_test_data_value("age", used, "number")
    used.add(first)
    second = _default_test_data_value("weight", used, "number")
    assert second != first
    assert second == "2"


def test_unrecognized_input_type_falls_back_to_generic_placeholder() -> None:
    used: set[str] = set()
    assert _default_test_data_value("notes", used, "textarea") == "Test value"


def test_quantity_named_field_gets_a_numeric_default_even_with_text_input_type() -> None:
    used: set[str] = set()
    assert _default_test_data_value("Amount", used) == "1"


def test_scenario_intent_below_minimum_amount() -> None:
    used: set[str] = set()
    assert _scenario_intent_default_value("Transfer amount below the minimum", "Amount", used) == "0.00"


def test_scenario_intent_at_minimum_amount() -> None:
    used: set[str] = set()
    assert (
        _scenario_intent_default_value("Transfer the minimum permitted amount", "Amount", used)
        == "0.01"
    )


def test_scenario_intent_at_maximum_amount() -> None:
    used: set[str] = set()
    assert (
        _scenario_intent_default_value("Policy at the maximum cover boundary", "coverage", used)
        == "999999.99"
    )


def test_scenario_intent_decimal_precision() -> None:
    used: set[str] = set()
    assert (
        _scenario_intent_default_value(
            "Loan application with supported decimal precision", "principal", used
        )
        == "10000.50"
    )


def test_scenario_intent_unicode_name_field() -> None:
    used: set[str] = set()
    assert (
        _scenario_intent_default_value("Multilingual legal name", "legalName", used)
        == "José García"
    )


def test_scenario_intent_emoji_subject() -> None:
    used: set[str] = set()
    assert _scenario_intent_default_value("Emoji subject", "subject", used) == "🚀😊"


def test_scenario_intent_markup_special_characters() -> None:
    used: set[str] = set()
    assert (
        _scenario_intent_default_value("Subject with markup-like characters", "subject", used)
        == "<test>&\"'</test>"
    )


def test_scenario_intent_password_unicode() -> None:
    used: set[str] = set()
    assert (
        _scenario_intent_default_value("Sign in with a Unicode password", "password", used)
        == "Pässwörd123$"
    )


def test_scenario_intent_password_maximum_length_regardless_of_word_order() -> None:
    used: set[str] = set()
    value = _scenario_intent_default_value(
        "Password at the maximum permitted length", "password", used
    )
    assert value is not None and len(value) > 100


def test_scenario_intent_password_minimum_length() -> None:
    used: set[str] = set()
    value = _scenario_intent_default_value("Minimum-length password", "password", used)
    assert value == "Pw1$"


def test_scenario_intent_generic_length_boundary_does_not_leak_into_numeric_check() -> None:
    used: set[str] = set()
    value = _scenario_intent_default_value(
        "Maximum supported profile name length", "profileName", used
    )
    assert value is not None and len(value) > 100


def test_scenario_intent_returns_none_for_unrelated_scenario() -> None:
    used: set[str] = set()
    assert _scenario_intent_default_value("Update profile name", "name", used) is None


def test_scenario_intent_does_not_apply_numeric_categories_to_password_fields() -> None:
    # "maximum" alone (no password-specific category matched) must not leak
    # the generic numeric-boundary value onto a password field.
    used: set[str] = set()
    assert _scenario_intent_default_value("Account with a maximum balance", "password", used) is None


def test_scenario_intent_skips_card_and_email_fields() -> None:
    used: set[str] = set()
    assert _scenario_intent_default_value("Unicode legal name", "email", used) is None
    assert _scenario_intent_default_value("Unicode legal name", "cardNumber", used) is None


def test_scenario_intent_change_password_boundary_keeps_current_password_standard() -> None:
    scenario_name = "Password at the configured maximum length"
    used: set[str] = set()
    current = _scenario_intent_default_value(scenario_name, "current password", used)
    assert current is None  # falls through to the standard default, unaffected


def test_scenario_intent_change_password_boundary_new_and_confirm_match_exactly() -> None:
    scenario_name = "Password at the configured maximum length"
    used: set[str] = set()
    new_value = _scenario_intent_default_value(
        scenario_name, "new password at maximum allowed length", used
    )
    used.add(new_value)
    confirm_value = _scenario_intent_default_value(scenario_name, "confirm new password", used)
    assert new_value == confirm_value
    assert len(new_value) > 100


def test_scenario_intent_genuine_mismatch_scenario_is_unaffected() -> None:
    # No length/unicode keyword in the name -> falls through to the
    # existing, intentionally-distinct default behavior (Checklist rule 6).
    used: set[str] = set()
    assert (
        _scenario_intent_default_value("Change password with mismatched confirmation", "password", used)
        is None
    )


def test_is_existing_credential_field_flags_bare_password() -> None:
    assert _is_existing_credential_field("password") is True


def test_is_existing_credential_field_flags_bare_username() -> None:
    assert _is_existing_credential_field("username") is True


def test_is_existing_credential_field_flags_current_password() -> None:
    assert _is_existing_credential_field("current password") is True
    assert _is_existing_credential_field("Existing Password") is True


def test_is_existing_credential_field_spares_new_password() -> None:
    assert _is_existing_credential_field("new password") is False


def test_is_existing_credential_field_spares_confirm_password() -> None:
    assert _is_existing_credential_field("confirm password") is False
    assert _is_existing_credential_field("confirmPassword") is False


def test_is_existing_credential_field_spares_unrelated_fields() -> None:
    assert _is_existing_credential_field("email") is False
    assert _is_existing_credential_field("promo_code") is False
