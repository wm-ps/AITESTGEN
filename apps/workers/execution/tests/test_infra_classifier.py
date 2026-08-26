"""`_is_infra_failure`/`_normalize_failure_signature` — self-healing's
classifier between a real code/test defect (healable) and an environment
problem (never healable, never counted against the shared attempt budget).
Verified against the exact signature strings `_parse_playwright_report`/
`_run_playwright_test` actually produce (see test_playwright_report_parsing.py
for where those strings come from), plus one real Playwright
assertion-failure message that must NOT classify as infra.
"""

from execution_worker.activities import _is_infra_failure, _normalize_failure_signature

_REAL_ASSERTION_ERROR = (
    "Timed out 15000ms waiting for expect(locator).toBeVisible()\n\n"
    "Locator: getByRole('heading', { name: 'Dashboard' })\n"
    "Expected: visible\nReceived: <element(s) not found>"
)


def test_no_parseable_json_report_is_infra() -> None:
    assert _is_infra_failure("errored", "playwright produced no parseable JSON report")


def test_setup_dependency_failed_is_infra() -> None:
    assert _is_infra_failure(
        "errored",
        "test was never executed (top-level status 'skipped') — its setup dependency likely failed",
    )


def test_no_matching_suite_is_infra() -> None:
    assert _is_infra_failure("errored", "playwright report contained no suite matching 'x.spec.ts'")


def test_process_timeout_is_infra() -> None:
    assert _is_infra_failure("timed_out", "playwright test exceeded the execution timeout")


def test_real_assertion_failure_is_not_infra() -> None:
    assert not _is_infra_failure("failed", _REAL_ASSERTION_ERROR)


def test_playwrights_own_per_test_timeout_is_not_infra() -> None:
    # Playwright's own `timedOut` result (a real, healable locator/assertion
    # timeout) carries a specific, different error_message than the whole
    # subprocess having been killed — only the latter's exact fixed string
    # means infra.
    assert not _is_infra_failure("timed_out", _REAL_ASSERTION_ERROR)


def test_passed_status_is_never_infra() -> None:
    assert not _is_infra_failure("passed", "playwright produced no parseable JSON report")


def test_failed_status_with_no_error_message_is_not_infra() -> None:
    # Only errored/timed_out with no message default to infra (an activity
    # that genuinely couldn't produce a result at all) — a plain `failed`
    # with no message is not, by definition, one of the infra states.
    assert not _is_infra_failure("failed", None)


def test_errored_status_with_no_error_message_is_infra() -> None:
    assert _is_infra_failure("errored", None)


def test_infra_signature_matching_is_case_insensitive() -> None:
    assert _is_infra_failure("errored", "PLAYWRIGHT PRODUCED NO PARSEABLE JSON REPORT")


def test_normalize_strips_digits_so_incidental_noise_compares_equal() -> None:
    a = "Timed out 15000ms waiting for expect(locator).toBeVisible() at line 42"
    b = "Timed out 18342ms waiting for expect(locator).toBeVisible() at line 42"
    assert _normalize_failure_signature(a) == _normalize_failure_signature(b)


def test_normalize_distinguishes_genuinely_different_errors() -> None:
    a = "Timed out waiting for expect(locator).toBeVisible()"
    b = "expect(received).toHaveText(expected) — received: 'Welcome', expected: 'Dashboard'"
    assert _normalize_failure_signature(a) != _normalize_failure_signature(b)


def test_normalize_none_is_empty_string() -> None:
    assert _normalize_failure_signature(None) == ""
