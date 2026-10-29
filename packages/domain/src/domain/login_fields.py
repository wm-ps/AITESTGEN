"""Which `Scenario.test_data` fields are the account's own login details.

Login credentials come from the Application's settings (Vault, via
`CREDENTIALS`/`fillCredentials`), never from a test's own test data — so a
login field is kept in storage (recorded tests map fields to code by
order) but marked `"login": True`, and the API never shows, accepts, or
hands it to the AI. Each source decides *which* fields are login fields from
its own context (recorded: the form the password is on; generated: a login
Scenario; Explorer: the saved-credential placeholders) — this module holds
the shared vocabulary so all three use the same words.
"""

import re
from typing import Any

# "spinbutton" must not read as a PIN field, so `pin` is whole-word only;
# "passport"/"passenger" must not read as a password, so no bare `pass`.
_PASSWORD_NAME_RE = re.compile(r"passw(?:or)?d|passcode|\bpin\b", re.IGNORECASE)
# The whole label, not a word in it — "login-status response" or "email
# subject" is something else that merely mentions login/email.
_LOGIN_IDENTITY_NAME_RE = re.compile(
    r"(?:your\s+|account\s+|work\s+)?"
    r"(?:user\s*name|user\s*id|e-?mail(?:\s+address)?|log\s*-?\s*in(?:\s+(?:id|name|e-?mail))?"
    r"|sign[\s-]?in\s+(?:id|name|e-?mail))"
    r"(?:\s+or\s+(?:user\s*name|e-?mail(?:\s+address)?))?",
    re.IGNORECASE,
)
_NEW_OR_CONFIRM_RE = re.compile(r"\bnew\b|\bconfirm|\bre-?enter|\brepeat\b", re.IGNORECASE)
# A value the test deliberately crafts (a malformed or boundary credential)
# is the thing under test, not the account's login — it stays editable.
_VALUE_UNDER_TEST_RE = re.compile(
    r"\b(containing|contains|begins?\s+(or\s+ends?\s+)?with|ends?\s+with|"
    r"exceeding|exceeds|too\s+(long|short)|malformed|invalid(\s+format)?|unicode|"
    r"special\s+character|whitespace|case-sensitiv\w*|leading\s+or\s+trailing|boundary)\b",
    re.IGNORECASE,
)
# Negative-login wording: the test signs in with a deliberately wrong value.
_NEGATIVE_LOGIN_RE = re.compile(
    r"\b(wrong|incorrect|unregistered|non-?existent|unknown|empty|blank|missing|"
    r"locked|disabled|deactivated|expired)\b",
    re.IGNORECASE,
)
_LOGIN_SCENARIO_RE = re.compile(
    r"\b(log[\s-]?in|sign[\s-]?in|login|credentials?|authenticat\w*)\b", re.IGNORECASE
)
# A login page also hosts these flows, whose email is the value under test.
_NOT_LOGIN_FLOW_RE = re.compile(
    r"\b(forgot|reset|recover\w*|register\w*|registration|sign[\s-]?up|create\s+(an\s+)?account)\b",
    re.IGNORECASE,
)
SAVED_CREDENTIAL_PLACEHOLDERS = ("{{username}}", "{{password}}")


def is_password_name(name: str) -> bool:
    return bool(_PASSWORD_NAME_RE.search(name))


def is_login_identity_name(name: str) -> bool:
    label = re.sub(r"[\s*:_]+", " ", name).strip()
    return bool(_LOGIN_IDENTITY_NAME_RE.fullmatch(label))


def is_new_or_confirm(name: str) -> bool:
    return bool(_NEW_OR_CONFIRM_RE.search(name))


def is_value_under_test(text: str) -> bool:
    return bool(_VALUE_UNDER_TEST_RE.search(text))


def is_login_scenario(name: str) -> bool:
    """A Scenario that signs in as its own subject — not a password reset
    or registration that merely starts from the login page."""
    return bool(_LOGIN_SCENARIO_RE.search(name)) and not _NOT_LOGIN_FLOW_RE.search(name)


def is_generated_login_field(
    field_name: str, scenario_name: str, intent_segments: list[str]
) -> bool:
    """A generated login Scenario's own username/email field — unless the
    sentence that mentions it makes its value the thing under test."""
    if not is_login_scenario(scenario_name) or not is_login_identity_name(field_name):
        return False
    if is_new_or_confirm(field_name):
        return False
    field_lower = field_name.lower()
    for segment in intent_segments:
        if field_lower in segment.lower() and (
            is_value_under_test(segment) or _NEGATIVE_LOGIN_RE.search(segment)
        ):
            return False
    return True


def is_saved_credential_value(value: Any) -> bool:
    return isinstance(value, str) and any(p in value for p in SAVED_CREDENTIAL_PLACEHOLDERS)


def is_login_field(field: dict[str, Any]) -> bool:
    return field.get("login") is True


def visible_fields(test_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The fields a user sees, edits, and the AI is given."""
    return [field for field in test_data if not is_login_field(field)]
