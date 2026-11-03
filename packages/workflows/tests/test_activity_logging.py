"""Every activity logs when it starts and when it ends, with its duration —
a failure too — and never logs an input object (it may carry logins)."""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from temporalio.worker import ExecuteActivityInput
from workflows import activity_logging


class _Next:
    def __init__(self, fail: bool) -> None:
        self.fail = fail

    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        if self.fail:
            raise RuntimeError("Couldn't sign in\nmore detail")
        return 7


def _run(fail: bool, args: list[Any]) -> Any:
    hook = activity_logging._LogEachActivity(_Next(fail))  # type: ignore[arg-type]
    return asyncio.run(hook.execute_activity(ExecuteActivityInput(lambda: None, args, None, {})))


@pytest.fixture(autouse=True)
def _info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        activity_logging.activity,
        "info",
        lambda: SimpleNamespace(
            activity_type="ExplorerUnderstand", workflow_id="explorer-x", attempt=1
        ),
    )


def test_start_and_done_with_duration(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="activity"):
        assert _run(False, ["run-123"]) == 7
    lines = [r.getMessage() for r in caplog.records]
    assert lines[0] == "start ExplorerUnderstand workflow=explorer-x id=run-123"
    assert lines[1].startswith("done ExplorerUnderstand workflow=explorer-x id=run-123 in ")


def test_failure_is_logged_with_its_reason(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="activity"), pytest.raises(RuntimeError):
        _run(True, ["run-123"])
    failed = caplog.records[-1]
    assert failed.levelno == logging.WARNING
    assert "failed ExplorerUnderstand" in failed.getMessage()
    assert failed.getMessage().endswith("RuntimeError: Couldn't sign in")


def test_input_objects_are_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="activity"):
        _run(False, [SimpleNamespace(password="secret")])
    assert all(
        "secret" not in r.getMessage() and "id=" not in r.getMessage() for r in caplog.records
    )
