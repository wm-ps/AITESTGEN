"""Test Suite Export — thin re-export shim (Story 4.3; Run All Tests feature).

The actual assembly logic moved to `packages/test_suite_assembler` so the
downloaded ZIP and the project the execution worker runs are built by the
exact same code — see that package's `assembler.py` module docstring. This
module stays in place purely so `api.main`'s existing imports (and this
package's existing tests) don't need to change.
"""

from test_suite_assembler import (
    LoginPageEvidence,
    TestSuiteExportError,
    assemble_test_suite_project,
    dedupe_slugs,
    find_login_page_evidence,
    sanitize_slug,
)

__all__ = [
    "LoginPageEvidence",
    "TestSuiteExportError",
    "assemble_test_suite_project",
    "dedupe_slugs",
    "find_login_page_evidence",
    "sanitize_slug",
]
