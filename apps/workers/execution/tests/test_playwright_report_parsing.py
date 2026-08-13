"""`_parse_playwright_report`/`_find_artifacts` — verified against real
`npx playwright test --reporter=json` output captured from live runs (a
passing test, a failing test with a real assertion error, and a target
test skipped because its `auth.setup.ts` dependency failed first). The
fixtures below are hand-trimmed to that same verified shape, not guessed.
"""

import json

from execution_worker.activities import _find_artifacts, _parse_playwright_report


def _report(suites: list[dict]) -> bytes:
    return json.dumps({"suites": suites}).encode("utf-8")


def _test_entry(status: str, *, results: list[dict] | None = None) -> dict:
    return {
        "projectId": "chromium",
        "projectName": "chromium",
        "status": status,
        "results": results or [],
    }


def test_passed_result_is_extracted() -> None:
    report = _report(
        [
            {
                "file": "smoke/passing.spec.ts",
                "specs": [
                    {
                        "title": "does the thing",
                        "tests": [
                            _test_entry(
                                "expected",
                                results=[{"status": "passed", "duration": 939}],
                            )
                        ],
                    }
                ],
            }
        ]
    )

    result = _parse_playwright_report(report, b"", "tests/smoke/passing.spec.ts")

    assert result["status"] == "passed"
    assert result["duration_ms"] == 939
    assert result["error_message"] is None


def test_failed_result_extracts_error_and_strips_ansi() -> None:
    report = _report(
        [
            {
                "file": "smoke/failing.spec.ts",
                "specs": [
                    {
                        "title": "does the thing",
                        "tests": [
                            _test_entry(
                                "unexpected",
                                results=[
                                    {
                                        "status": "failed",
                                        "duration": 5752,
                                        "error": {
                                            "message": "\x1b[31mExpected pattern\x1b[39m: /x/",
                                            "stack": "Error: boom\n    at file.ts:4:22",
                                        },
                                    }
                                ],
                            )
                        ],
                    }
                ],
            }
        ]
    )

    result = _parse_playwright_report(report, b"", "tests/smoke/failing.spec.ts")

    assert result["status"] == "failed"
    assert result["duration_ms"] == 5752
    assert result["error_message"] == "Expected pattern: /x/"
    assert "\x1b" not in result["error_message"]
    assert result["stack_trace"] == "Error: boom\n    at file.ts:4:22"


def test_timed_out_status_maps_to_timed_out() -> None:
    report = _report(
        [
            {
                "file": "smoke/slow.spec.ts",
                "specs": [
                    {
                        "title": "takes too long",
                        "tests": [
                            _test_entry(
                                "unexpected",
                                results=[{"status": "timedOut", "duration": 30000}],
                            )
                        ],
                    }
                ],
            }
        ]
    )

    result = _parse_playwright_report(report, b"", "tests/smoke/slow.spec.ts")

    assert result["status"] == "timed_out"


def test_target_test_skipped_by_a_failed_setup_dependency_is_errored_not_passed() -> None:
    """Verified live: when auth.setup.ts fails, every project depending on
    it (chromium) shows the target test with empty `results` and top-level
    `status: "skipped"` — this must never be read as a pass, and must never
    accidentally report the *setup* suite's own failure as if it belonged
    to the target test (the real bug this parser was rewritten to fix)."""
    report = _report(
        [
            {
                "file": "auth.setup.ts",
                "specs": [
                    {
                        "title": "authenticate",
                        "tests": [
                            {
                                "projectId": "setup",
                                "projectName": "setup",
                                "status": "unexpected",
                                "results": [
                                    {
                                        "status": "failed",
                                        "duration": 1926,
                                        "error": {"message": "credentials missing"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "file": "smoke/passing.spec.ts",
                "specs": [
                    {
                        "title": "does the thing",
                        "tests": [_test_entry("skipped", results=[])],
                    }
                ],
            },
        ]
    )

    result = _parse_playwright_report(report, b"", "tests/smoke/passing.spec.ts")

    assert result["status"] == "errored"
    assert "credentials missing" not in (result["error_message"] or "")
    assert "skipped" in result["error_message"]


def test_no_matching_suite_is_errored() -> None:
    report = _report([{"file": "smoke/other.spec.ts", "specs": []}])

    result = _parse_playwright_report(report, b"", "tests/smoke/missing.spec.ts")

    assert result["status"] == "errored"
    assert "no suite matching" in result["error_message"]


def test_unparseable_stdout_is_errored() -> None:
    result = _parse_playwright_report(b"not json", b"", "tests/smoke/passing.spec.ts")

    assert result["status"] == "errored"
    assert "no parseable JSON report" in result["error_message"]


def test_find_artifacts_only_matches_png_and_zip(tmp_path) -> None:
    nested = tmp_path / "smoke-failing-test-chromium"
    nested.mkdir()
    (nested / "test-failed-1.png").write_bytes(b"png-bytes")
    (nested / "trace.zip").write_bytes(b"zip-bytes")
    (nested / "error-context.md").write_text("not an artifact we store")

    found = {p.name for p in _find_artifacts(tmp_path)}

    assert found == {"test-failed-1.png", "trace.zip"}


def test_find_artifacts_on_missing_dir_returns_empty(tmp_path) -> None:
    assert _find_artifacts(tmp_path / "does-not-exist") == []
