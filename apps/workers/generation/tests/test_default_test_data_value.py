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
