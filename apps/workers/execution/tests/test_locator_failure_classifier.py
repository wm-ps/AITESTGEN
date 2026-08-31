"""`_is_locator_failure` — self-healing's deterministic trigger for
targeted live Playwright inspection (live_inspection.py). Only ever
checked after `_is_infra_failure` has already had first say inside
`heal_test_activity`'s loop (activities.py) — an infra-classified failure
must never also trigger a live-browser inspection over the same root
cause, so this file also verifies the two classifiers never agree on the
same input.
"""

from execution_worker.activities import (
    _INFRA_ERROR_SIGNATURES,
    _is_infra_failure,
    _is_locator_failure,
)

_REAL_ASSERTION_ERROR = (
    "Timed out 15000ms waiting for expect(locator).toBeVisible()\n\n"
    "Locator: getByRole('heading', { name: 'Dashboard' })\n"
    "Expected: visible\nReceived: <element(s) not found>"
)


def test_timeout_waiting_for_locator_is_a_locator_failure() -> None:
    assert _is_locator_failure(
        "timed_out", "TimeoutError: waiting for locator('button[name=\"submit\"]')"
    )


def test_timeout_waiting_for_selector_is_a_locator_failure() -> None:
    assert _is_locator_failure("timed_out", "Timeout 30000ms exceeded while waiting for selector")


def test_strict_mode_violation_is_a_locator_failure() -> None:
    assert _is_locator_failure(
        "failed",
        "strict mode violation: locator('.item') resolved to 3 elements",
    )


def test_element_not_attached_to_dom_is_a_locator_failure() -> None:
    assert _is_locator_failure("failed", "Error: element is not attached to the DOM")


def test_element_not_found_is_a_locator_failure() -> None:
    assert _is_locator_failure("failed", "no elements found for selector '#missing'")


def test_unrelated_assertion_failure_is_not_a_locator_failure() -> None:
    assert not _is_locator_failure(
        "failed",
        "expect(received).toHaveText(expected) — received: 'Welcome', expected: 'Dashboard'",
    )


def test_no_error_message_is_not_a_locator_failure() -> None:
    assert not _is_locator_failure("errored", None)


def test_matching_is_case_insensitive() -> None:
    assert _is_locator_failure("timed_out", "WAITING FOR LOCATOR('#save')")


def test_playwright_assertion_timeout_is_not_a_locator_failure() -> None:
    """A real, healable `expect(...).toBeVisible()` timeout is a genuine
    assertion failure, not a locator problem — must not false-positive."""
    assert not _is_locator_failure("timed_out", _REAL_ASSERTION_ERROR)


# --- infra/locator classifiers must never agree on the same input --------


def test_infra_signatures_never_also_classify_as_locator_failures() -> None:
    """Every fixed infra signature must classify as infra, and must NOT
    also trigger the locator classifier — an infra failure short-circuits
    the loop before _is_locator_failure is ever reached, but this proves
    there's no accidental overlap even if that ordering were ever
    violated."""
    for signature in _INFRA_ERROR_SIGNATURES:
        assert _is_infra_failure("errored", signature), signature
        assert not _is_locator_failure("errored", signature), signature


def test_process_timeout_infra_signature_is_not_a_locator_failure() -> None:
    assert _is_infra_failure("timed_out", "playwright test exceeded the execution timeout")
    assert not _is_locator_failure("timed_out", "playwright test exceeded the execution timeout")
