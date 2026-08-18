"""Checklist rule 6 (test-data distinctness): `_default_test_data_value` must
never hand out the same placeholder twice within one scenario — a
confirm-mismatch/before-after scenario needs genuinely distinct literals, not
one canonical placeholder reused for every same-shaped field. Pure logic, no
DB needed.
"""

from generation_worker.activities import _default_test_data_value


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
