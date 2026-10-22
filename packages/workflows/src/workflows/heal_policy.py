"""Which failures AI self-healing may act on — shared by the execution
worker's HealTestActivity, the generation worker's LiveHealActivity, and the
API's manual-retry endpoint, so all three apply one rule:

    a failure raised inside an `expect(...)` assertion is never healed.

Every other failure is eligible exactly as before — this module only adds
the assertion exclusion. The infra and live-inspection classifiers below are
the originals, moved here unchanged from execution_worker/activities.py.

Pure string/regex logic, no I/O, so it is safe to import from workflow code.
"""

import re

# Prefixes HealTestActivity writes over `TestResult.error_message` when one
# of its own attempts is rejected (see execution_worker/activities.py). Such
# a message only exists because a heal was already under way, so it must
# never read as an assertion failure and end that heal's loop or block a
# manual retry.
HEAL_TYPECHECK_ERROR_PREFIX = "generated fix failed typecheck: "
HEAL_ASSERTION_GUARD_ERROR_PREFIX = "generated fix changed assertions: "
_HEAL_ATTEMPT_PREFIXES = (HEAL_TYPECHECK_ERROR_PREFIX, HEAL_ASSERTION_GUARD_ERROR_PREFIX)

ASSERTION_FAILURE_REASON = "Assertion failures aren't self-healed."

_INFRA_ERROR_SIGNATURES = (
    "playwright produced no parseable json report",  # _parse_playwright_report — process/report itself broke
    "its setup dependency likely failed",  # auth.setup.ts (login) failed, not this test's code
    "playwright report contained no suite matching",  # assembly/config issue
    "playwright test exceeded the execution timeout",  # _run_playwright_test — the WHOLE process was killed after
    # PLAYWRIGHT_RUN_TIMEOUT_SECONDS; distinct from Playwright's own
    # per-test `timedOut` result (a real, healable locator/assertion
    # timeout with its own, different error_message) — only this exact
    # fixed string means the whole browser/subprocess hung, an environment
    # problem, not this test's own logic.
)


def is_infra_failure(status: str, error_message: str | None) -> bool:
    if status not in ("errored", "timed_out"):
        return False
    if not error_message:
        return True
    lowered = error_message.lower()
    return any(sig in lowered for sig in _INFRA_ERROR_SIGNATURES)


# Deterministic trigger for live inspection (heal_test_activity's loop in
# execution_worker/activities.py) — mirrors is_infra_failure's style. Only
# ever checked AFTER is_infra_failure has already had first say (the loop's own infra break
# runs before this), so an infra-classified failure never reaches this
# classifier at all: infra failures must never consume a heal attempt OR
# trigger a live-browser inspection over the same root cause. These five
# patterns map to the five categories a stale/broken locator actually shows
# up as: a locator Playwright waited for and never found, a locator that now
# matches more than one element (UI changed shape), an element that's been
# removed from the DOM since the test was written, a plain not-found/no-match
# message for dynamic content that hasn't rendered (yet, or ever, if the app
# changed), and the shared `ensureVisible` helper's own custom error (a
# locator that resolved but never became visible even after an explicit
# scroll-into-view — the same stale/wrong-locator or changed-UI root cause
# as the other four, just worded by this project's own helper instead of by
# Playwright itself).
_LOCATOR_FAILURE_PATTERNS = (
    re.compile(r"waiting for (?:locator|selector)", re.IGNORECASE),
    re.compile(r"strict mode violation.*resolved to \d+ elements", re.IGNORECASE),
    re.compile(r"element is not attached to (?:the )?dom", re.IGNORECASE),
    re.compile(r"no elements? found for selector|element(?:s)? not found", re.IGNORECASE),
    re.compile(r"is not visible even after scrolling", re.IGNORECASE),
)


def is_locator_failure(status: str, error_message: str | None) -> bool:
    """Deterministic — never left to AI judgment alone. True only for a
    failure that looks like a stale/invalid locator, changed UI, a missing
    element, or unrendered dynamic content; used to gate whether
    heal_test_activity's loop launches a live Playwright inspection before
    asking the AI for a fix."""
    if not error_message:
        return False
    return any(pattern.search(error_message) for pattern in _LOCATOR_FAILURE_PATTERNS)


# Raised by `expect(...)`. Only the error's own first line and Playwright's
# assertion call-log entry are checked, never the whole message: a stored
# message also carries a source code frame, and a non-assertion failure's
# frame can show a neighbouring `expect(` line that has nothing to do with it.
#   first line: `Error: expect(locator).toBeVisible() failed`,
#               `Timed out 15000ms waiting for expect(locator).toBeVisible()`,
#               `Error: expect(received).toBe(expected) // Object.is equality`
#   call log:   `- Expect "toBeVisible" getByRole(...) with timeout 30000ms`
_ASSERTION_FIRST_LINE_RE = re.compile(r"\bexpect(?:\.\w+)*\(")
_ASSERTION_CALL_LOG_RE = re.compile(r'^\s*-\s*Expect "\w+"', re.MULTILINE)


def is_assertion_failure(error_message: str | None) -> bool:
    if not error_message:
        return False
    first_line = next((line for line in error_message.splitlines() if line.strip()), "")
    return bool(
        _ASSERTION_FIRST_LINE_RE.search(first_line) or _ASSERTION_CALL_LOG_RE.search(error_message)
    )


def heal_eligibility(status: str, error_message: str | None) -> str | None:
    """None when AI self-healing may act on this failure; otherwise the
    reason it may not, worded for the person looking at the run. The only
    exclusion is a failure raised inside an assertion — status gating
    (`HEALABLE_STATUSES`), infra reruns and attempt budgets stay with the
    callers, exactly as before."""
    if error_message and error_message.startswith(_HEAL_ATTEMPT_PREFIXES):
        return None
    if is_assertion_failure(error_message):
        return ASSERTION_FAILURE_REASON
    return None
