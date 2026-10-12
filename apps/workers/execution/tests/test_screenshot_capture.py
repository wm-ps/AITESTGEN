"""`_keep_artifact` — which artifacts a finished TestResult keeps under each
Screenshot capture setting."""

from execution_worker.activities import _keep_artifact


def test_keep_artifact_per_screenshot_capture_setting() -> None:
    cases = {
        # (artifact_type, status, setting): kept
        ("screenshot", "failed", "failed"): True,
        ("screenshot", "timed_out", "failed"): True,
        ("screenshot", "passed", "failed"): False,
        ("screenshot", "passed", "passed"): True,
        ("screenshot", "errored", "passed"): False,
        ("screenshot", "passed", "all"): True,
        ("screenshot", "failed", "all"): True,
        ("trace", "failed", "passed"): True,
        ("trace", "passed", "all"): False,
    }
    for (artifact_type, status, setting), expected in cases.items():
        assert _keep_artifact(artifact_type, status, setting) is expected, (artifact_type, status, setting)
