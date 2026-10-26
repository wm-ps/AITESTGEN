"""`failure_explainer` — plain-language test failures. Message shapes are
Playwright's real ones, as stored on TestResult.error_message in the dev
database (code frames, call logs and the auth-retry note included)."""

import pytest
from workflows import HEAL_ASSERTION_GUARD_ERROR_PREFIX, HEAL_TYPECHECK_ERROR_PREFIX
from workflows.failure_explainer import (
    UNDETERMINED_TITLE,
    UNKNOWN,
    clean_error,
    describe_element,
    error_fingerprint,
    explain_failure,
    redact_for_llm,
    run_root_cause,
)

AUTH_RETRY_NOTE = (
    "\n\nError: AUTH_SESSION_INVALID: this @auth test failed — retrying once against a freshly "
    "re-established session in case a concurrently-running test logged out.\n\n"
    "   at ..\\support\\fixtures.ts:26\n\n  24 |     await use(page)\n> 26 |       throw new Error(\n"
)

CLICK_TIMEOUT = (
    "TimeoutError: locator.click: Timeout 15000ms exceeded.\n"
    "Call log:\n"
    '  - waiting for locator(\'form button[type="submit"], form input[type="submit"]\').first()\n\n\n'
    "  57 |     timeout: ASSERTION_TIMEOUT_MS,\n"
    "  58 |   });\n"
    "> 59 |   await submitButton.click({\n"
    "     |                      ^\n"
    "    at C:\\tmp\\aitestgen-execution\\22c7\\tests\\view-account-statement\\x.spec.ts:59:22"
    + AUTH_RETRY_NOTE
)

NOT_VISIBLE = (
    "Error: expect(locator).toBeVisible() failed\n\n"
    "Locator: getByRole('link', { name: /Track Service Requests/ })\n"
    "Expected: visible\nTimeout: 30000ms\nError: element(s) not found\n\n"
    "Call log:\n  - Expect \"toBeVisible\" getByRole('link', { name: /Track Service Requests/ }) with timeout 30000ms\n"
)

WRONG_URL = (
    "Error: expect(page).toHaveURL(expected) failed\n\n"
    'Expected: "https://pixiservice.onwavemaker.com/#/RMAEngineerDetails?rmaId=1"\n'
    'Received: "https://pixiservice.onwavemaker.com/#/RMAEngineerDetails?rmaId=39"\n'
    "Timeout:  15000ms\n"
)

WRONG_TEXT_MISSING = (
    "Error: expect(locator).toHaveText(expected) failed\n\n"
    "Locator: getByTestId('claim-status')\nExpected string: \"Submitted\"\nError: element(s) not found\n"
)

WRONG_VALUE = (
    "Error: expect(locator).toHaveValue(expected) failed\n\n"
    "Locator:  locator('[name=\"coverAmount\"]')\n"
    'Expected: "999999.99"\nReceived: "1000000"\nTimeout:  15000ms\n'
)

WRONG_COUNT = "Error: expect(locator).toHaveCount(expected) failed\n\nLocator: getByRole('row')\nExpected: 20\nReceived: 0\n"

PAGE_GOTO = (
    "TimeoutError: page.goto: Timeout 30000ms exceeded.\nCall log:\n"
    '  - navigating to "https://pixiservice.onwavemaker.com/#/Dashboard", waiting until "domcontentloaded"\n'
)

CREDENTIALS = (
    "failed to prepare the test project: None, on get "
    "http://localhost:8200/v1/secret/data/applications/01a0b4f1-b38e-7a5e/298c537a-0af9"
)

AUTH_SETUP = (
    "failed to prepare the test project: auth.setup.ts failed (exit 1):\nstdout: \nRunning 1 test"
)


@pytest.mark.parametrize(
    ("message", "category", "title_part", "detail_part"),
    [
        (CLICK_TIMEOUT, "action_timeout", "Couldn't click the submit button", "waited 15 seconds"),
        (NOT_VISIBLE, "not_visible", 'the "Track Service Requests" link', "couldn't be found"),
        (WRONG_URL, "wrong_page", "wrong page", "rmaId=39"),
        (
            WRONG_TEXT_MISSING,
            "wrong_text",
            "different text",
            'the "claim-status" element to say "Submitted"',
        ),
        (
            WRONG_VALUE,
            "wrong_value",
            "different value",
            'the cover amount field to contain "999999.99"',
        ),
        (WRONG_COUNT, "wrong_value", "different number", "expected 20"),
        (PAGE_GOTO, "page_load", "didn't load", "30 seconds"),
        ("Error: Failed to load page. HTTP status: 500", "page_load", "didn't load", "HTTP 500"),
        (CREDENTIALS, "credentials", "saved login details", "never started"),
        (AUTH_SETUP, "sign_in", "sign in", "saved credentials"),
        (
            "playwright produced no parseable JSON report",
            "internal",
            "problem in Vantage",
            "isn't a problem",
        ),
        (
            "test did not complete (activity failed after retries)",
            "internal",
            "problem in Vantage",
            "",
        ),
        (
            "playwright test exceeded the execution timeout",
            "too_long",
            "took too long",
            "8 minutes",
        ),
        (
            "Error: strict mode violation: getByRole('button', { name: 'Save' }) resolved to 2 elements:",
            "multiple_matches",
            "more than one",
            'matched the "Save" button',
        ),
        ("Error: locator not found", "not_found", "Couldn't find", ""),
        (
            HEAL_TYPECHECK_ERROR_PREFIX + "error TS2304",
            "heal_rejected",
            "Self-healing",
            "original test was kept",
        ),
        (
            HEAL_ASSERTION_GUARD_ERROR_PREFIX + "assertion 1 changed",
            "heal_rejected",
            "Self-healing",
            "",
        ),
    ],
)
def test_known_failures_get_a_plain_explanation(
    message: str, category: str, title_part: str, detail_part: str
) -> None:
    explanation = explain_failure("failed", message)

    assert explanation is not None
    assert explanation.category == category
    assert title_part in explanation.title
    assert detail_part in explanation.detail


def test_explanations_never_leak_internals() -> None:
    explanation = explain_failure("failed", CLICK_TIMEOUT)

    for text in (explanation.title, explanation.detail):
        assert "AUTH_SESSION_INVALID" not in text
        assert "C:\\tmp" not in text
        assert "|" not in text


def test_unknown_errors_carry_their_cleaned_first_line() -> None:
    explanation = explain_failure(
        "failed", "\x1b[31mError: something totally new happened\x1b[0m\n  at x.ts:1"
    )

    assert explanation.category == UNKNOWN
    assert explanation.title == "something totally new happened"


def test_only_failures_are_explained() -> None:
    assert explain_failure("passed", None) is None
    assert explain_failure("pending", None) is None
    assert explain_failure("cancelled", "Run cancelled").category == "cancelled"


def test_the_error_message_is_never_changed() -> None:
    original = CLICK_TIMEOUT
    snapshot = str(original)
    explain_failure("failed", original)
    assert original == snapshot


def test_clean_error_strips_noise() -> None:
    cleaned = clean_error(CLICK_TIMEOUT)

    assert "AUTH_SESSION_INVALID" not in cleaned
    assert "> 59 |" not in cleaned
    assert "C:\\tmp" not in cleaned
    assert cleaned.startswith("TimeoutError: locator.click")


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        ("Locator: getByRole('button', { name: 'Submit' })", 'the "Submit" button'),
        ("Locator: getByRole('textbox', { name: /Email/i })", 'the "Email" field'),
        ("Locator: getByLabel('Amount (USD)', { exact: true })", 'the "Amount (USD)" field'),
        ("Locator: getByPlaceholder('Search')", 'the "Search" field'),
        ("Locator: getByText('Welcome back')", 'the text "Welcome back"'),
        ("Locator: getByTestId('claim-status')", 'the "claim-status" element'),
        ("Locator: getByRole('row')", "a table row"),
        ("Locator: locator('#first-name')", "the first name field"),
        ("Locator: locator('div > span.x')", "an element on the page"),
    ],
)
def test_describe_element(locator: str, expected: str) -> None:
    assert describe_element(locator) == expected


# --- Run-level root cause -------------------------------------------------------


def test_root_cause_when_a_shared_cause_dominates() -> None:
    cause = run_root_cause(["sign_in"] * 38 + ["not_visible", "wrong_text"])

    assert cause is not None
    assert (cause.category, cause.affected, cause.total) == ("sign_in", 38, 40)


@pytest.mark.parametrize(
    "categories",
    [
        ["sign_in", "sign_in", "not_visible"],  # only 2 — under the minimum of 3
        ["page_load"] * 3 + ["not_visible"] * 3,  # 50% — under 60%
        ["not_visible"] * 10,  # test-specific, never a shared cause
        [UNKNOWN] * 10,  # AI-explained, never certain enough
        [],
    ],
)
def test_no_root_cause_unless_clearly_shared(categories: list[str]) -> None:
    assert run_root_cause(categories) is None


# --- Redaction / fingerprint ---------------------------------------------------------


def test_redaction_removes_sensitive_values() -> None:
    text = (
        "Error at fill('hunter2') then type(\"4111111111111111\") and pressSequentially(`s3cret`)\n"
        "user qa-account with password=Pa55word! token: abcd\n"
        "url https://user:pw@app.example.com/login?session=xyz&next=/home\n"
        "Authorization: Bearer abc.def.ghi and jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlX3h4\n"
        "contact jane.doe@example.com account 1234567890 key 9f8e7d6c5b4a39281706f5e4d3c2b1a0\n"
    )

    redacted = redact_for_llm(text, known_secrets=["qa-account", "SuperSecretPw"])

    for secret in (
        "hunter2",
        "4111111111111111",
        "s3cret",
        "qa-account",
        "Pa55word!",
        "abcd",
        "user:pw",
        "session=xyz",
        "abc.def.ghi",
        "eyJhbGciOiJIUzI1NiJ9",
        "jane.doe@example.com",
        "1234567890",
        "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
    ):
        assert secret not in redacted, secret
    assert "fill('[redacted]')" in redacted


def test_redaction_removes_the_apps_own_saved_password_anywhere() -> None:
    redacted = redact_for_llm(
        "login failed for p@ssW0rd-123 on step 2", known_secrets=["p@ssW0rd-123"]
    )
    assert "p@ssW0rd-123" not in redacted


def test_redaction_truncates() -> None:
    assert len(redact_for_llm("x" * 10_000)) == 2000


def test_fingerprint_is_stable_across_incidental_numbers() -> None:
    a = error_fingerprint(redact_for_llm("Error: widget broke after 1234ms on line 59"))
    b = error_fingerprint(redact_for_llm("Error: widget broke after 987ms on line 61"))
    c = error_fingerprint(redact_for_llm("Error: a different thing broke"))

    assert a == b
    assert a != c


def test_undetermined_title_is_plain() -> None:
    assert "couldn't identify" in UNDETERMINED_TITLE
