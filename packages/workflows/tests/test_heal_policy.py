"""`heal_eligibility` — the one exclusion: a failure raised inside an
`expect(...)` assertion is never healed. Every other failure stays eligible
exactly as before. Message shapes are Playwright's real ones, as stored on
TestResult.error_message (code frame and call log included)."""

import pytest
from workflows import (
    HEAL_ASSERTION_GUARD_ERROR_PREFIX,
    HEAL_TYPECHECK_ERROR_PREFIX,
    heal_eligibility,
    is_assertion_failure,
    is_locator_failure,
)
from workflows.heal_policy import ASSERTION_FAILURE_REASON

# --- Missing elements inside assertions: never healed ----------------------

ASSERTION_ELEMENT_NOT_FOUND = {
    "toBeVisible": (
        "Error: expect(locator).toBeVisible() failed\n\n"
        "Locator: getByRole('link', { name: /Home Loan/ })\n"
        "Expected: visible\nTimeout: 30000ms\nError: element(s) not found\n\n"
        "Call log:\n"
        "  - Expect \"toBeVisible\" getByRole('link', { name: /Home Loan/ }) with timeout 30000ms\n"
        "  - waiting for getByRole('link', { name: /Home Loan/ })\n"
    ),
    "toBeVisible (older timeout wording)": (
        "Timed out 15000ms waiting for expect(locator).toBeVisible()\n\n"
        "Locator: getByRole('heading', { name: 'Dashboard' })\n"
        "Expected: visible\nReceived: <element(s) not found>\n"
        "Call log:\n"
        "  - expect.toBeVisible with timeout 15000ms\n"
        "  - waiting for locator('h1')\n"
    ),
    "toHaveText": (
        "Error: expect(locator).toHaveText(expected) failed\n\n"
        "Locator: getByTestId('claim-status')\n"
        'Expected string: "Submitted"\nTimeout: 15000ms\nError: element(s) not found\n\n'
        "Call log:\n"
        "  - Expect \"toHaveText\" getByTestId('claim-status') with timeout 15000ms\n"
        "  - waiting for getByTestId('claim-status')\n"
    ),
    "toHaveValue": (
        "Error: expect(locator).toHaveValue(expected) failed\n\n"
        "Locator: getByLabel('Amount')\nExpected string: \"120\"\nTimeout: 15000ms\n"
        "Error: element(s) not found\n\n"
        "Call log:\n"
        "  - Expect \"toHaveValue\" getByLabel('Amount') with timeout 15000ms\n"
        "  - waiting for getByLabel('Amount')\n"
    ),
    "toBeEnabled": (
        "Error: expect(locator).toBeEnabled() failed\n\n"
        "Locator: locator('button[type=\"submit\"]')\nExpected: enabled\nTimeout: 15000ms\n"
        "Error: element(s) not found\n\n"
        "Call log:\n"
        '  - Expect "toBeEnabled" locator(\'button[type="submit"]\') with timeout 15000ms\n'
        "  - waiting for locator('button[type=\"submit\"]')\n"
    ),
    "toHaveCount": (
        "Error: expect(locator).toHaveCount(expected) failed\n\n"
        "Locator: getByRole('row')\nExpected: 20\nReceived: 0\nTimeout: 30000ms\n\n"
        "Call log:\n"
        "  - Expect \"toHaveCount\" getByRole('row') with timeout 30000ms\n"
        "  - waiting for getByRole('row')\n"
    ),
    "strict-mode violation inside an assertion": (
        "Error: expect(locator).toBeVisible() failed\n\n"
        "Locator: getByText('Action Taken')\nExpected: visible\n"
        "Error: strict mode violation: getByText('Action Taken') resolved to 2 elements\n\n"
        "Call log:\n"
        "  - Expect \"toBeVisible\" getByText('Action Taken') with timeout 15000ms\n"
    ),
    "expect.soft": (
        "Error: expect.soft(locator).toBeVisible() failed\n\n"
        "Locator: getByText('Welcome')\nExpected: visible\nError: element(s) not found\n"
    ),
}

VALUE_ASSERTIONS = {
    "toHaveURL": (
        "Error: expect(page).toHaveURL(expected) failed\n\n"
        'Expected: "https://app.example.com/#/details?id=1"\n'
        'Received: "https://app.example.com/#/details?id=10"\nTimeout: 15000ms\n\n'
        'Call log:\n  - Expect "toHaveURL" with timeout 15000ms\n'
    ),
    "toBe": "Error: expect(received).toBe(expected) // Object.is equality\n\nExpected: 3\nReceived: 2",
    "not.toHaveURL": 'Error: expect(page).not.toHaveURL(expected) failed\n\nExpected: not "x"',
}


@pytest.mark.parametrize(
    "message", ASSERTION_ELEMENT_NOT_FOUND.values(), ids=ASSERTION_ELEMENT_NOT_FOUND
)
@pytest.mark.parametrize("status", ["failed", "timed_out", "errored"])
def test_missing_element_inside_an_assertion_is_never_healed(status, message):
    assert is_assertion_failure(message)
    assert heal_eligibility(status, message) == ASSERTION_FAILURE_REASON


@pytest.mark.parametrize("message", VALUE_ASSERTIONS.values(), ids=VALUE_ASSERTIONS)
def test_value_assertion_mismatch_is_never_healed(message):
    assert heal_eligibility("failed", message) == ASSERTION_FAILURE_REASON


# --- Broken locators in normal actions: still healed ----------------------

ACTION_LOCATOR_FAILURES = {
    "click": (
        "TimeoutError: locator.click: Timeout 15000ms exceeded.\n"
        "Call log:\n"
        "  - waiting for getByRole('button', { name: 'Close Ticket', exact: true })\n\n"
        "  57 |     timeout: ASSERTION_TIMEOUT_MS,\n"
        "  58 |   });\n"
        "> 59 |   await closeButton.click();\n"
        "     |                     ^\n"
        "  60 |   await expect(page.getByText('Closed')).toBeVisible();\n"
    ),
    "fill": (
        "TimeoutError: locator.fill: Timeout 15000ms exceeded.\n"
        "Call log:\n  - waiting for getByLabel('Amount', { exact: true })\n"
    ),
    "selectOption": (
        "TimeoutError: locator.selectOption: Timeout 15000ms exceeded.\n"
        "Call log:\n  - waiting for locator('select[name=\"country\"]')\n"
    ),
    "page.fill": (
        "TimeoutError: page.fill: Timeout 15000ms exceeded.\n"
        "Call log:\n  - waiting for locator('#amount')\n"
    ),
    "strict-mode violation in an action": (
        "Error: locator.waitFor: Error: strict mode violation: getByText('Action Taken', "
        "{ exact: true }) resolved to 2 elements:\n"
    ),
    "detached element": "Error: locator.click: Element is not attached to the DOM",
    "ensureVisible helper": (
        "Error: Element matched by locator getByRole('button', { name: /submit/i }) is not visible "
        "even after waiting and scrolling into view — the locator may be wrong, or the element "
        "requires a prior action (opening a menu/accordion/tab, waiting for content to load) to "
        "become visible.\n    at ..\\support\\interactions.ts:31:11"
    ),
}


@pytest.mark.parametrize("message", ACTION_LOCATOR_FAILURES.values(), ids=ACTION_LOCATOR_FAILURES)
def test_broken_locator_in_an_action_is_still_healed(message):
    assert not is_assertion_failure(message)
    assert heal_eligibility("failed", message) is None


@pytest.mark.parametrize(
    "key", ["selectOption", "page.fill", "strict-mode violation in an action", "detached element"]
)
def test_live_inspection_trigger_is_the_original_classifier(key):
    """`is_locator_failure` only decides whether diagnosis opens the live
    page — moved here unchanged, so it matches exactly what it matched
    before (these four hit its original patterns)."""
    assert is_locator_failure("failed", ACTION_LOCATOR_FAILURES[key])


def test_expect_in_an_action_failures_code_frame_does_not_block_it():
    """The click failure above carries a code frame showing a neighbouring
    `expect(` line — only the error's own first line and call log count."""
    message = ACTION_LOCATOR_FAILURES["click"]
    assert "expect(" in message
    assert heal_eligibility("failed", message) is None


# --- Every other failure: still healed, exactly as before -----------------


@pytest.mark.parametrize(
    "message",
    [
        'TimeoutError: page.goto: Timeout 30000ms exceeded.\nCall log:\n  - navigating to "https://x"',
        "TimeoutError: page.waitForLoadState: Timeout 30000ms exceeded.",
        "Error: Failed to load page. HTTP status: 404",
        "Error: Failed to load page. HTTP status: undefined",
        "failed to prepare the test project: auth.setup.ts failed (exit 1)",
        "Error: worker process exited unexpectedly (code=134, signal=null)",
        "TypeError: Cannot read properties of undefined (reading 'click')",
        "Error: Could not identify the closed RMA linked to rmaId=1.",
    ],
)
def test_non_assertion_failures_stay_eligible(message):
    assert not is_assertion_failure(message)
    assert heal_eligibility("failed", message) is None


def test_infra_failure_stays_eligible_for_its_same_code_rerun():
    assert heal_eligibility("errored", "playwright produced no parseable JSON report") is None
    assert heal_eligibility("errored", None) is None


@pytest.mark.parametrize(
    "message",
    [
        HEAL_TYPECHECK_ERROR_PREFIX + "error TS2304: Cannot find name 'foo'.",
        HEAL_ASSERTION_GUARD_ERROR_PREFIX + "assertion 1 changed: expect(a).toBeVisible() → …",
    ],
)
def test_a_heal_already_under_way_stays_eligible(message):
    assert heal_eligibility("failed", message) is None


def test_no_message_on_a_failed_test_stays_eligible():
    assert heal_eligibility("failed", None) is None
