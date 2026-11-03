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


def _label_of(record: logging.LogRecord) -> str:
    activity_logging._AppLabel().filter(record)
    return record.app  # type: ignore[attr-defined]


def test_lines_name_the_app_the_activity_loaded(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="activity")
    class _LoadsAnApp(_Next):
        async def execute_activity(self, input: ExecuteActivityInput) -> Any:
            # Loaded in a worker thread, as most activities do it.
            await asyncio.to_thread(activity_logging.label_app, "Denali", "3f9a1c2b-0000")
            logging.getLogger("x").warning("inside")
            return 1

    records: list[logging.LogRecord] = []

    class _Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)
            _label_of(record)

    handler = _Keep()
    logging.getLogger().addHandler(handler)
    try:
        hook = activity_logging._LogEachActivity(_LoadsAnApp(False))  # type: ignore[arg-type]
        asyncio.run(hook.execute_activity(ExecuteActivityInput(lambda: None, ["r"], None, {})))
    finally:
        logging.getLogger().removeHandler(handler)
    labels = {r.getMessage().split()[0]: r.app for r in records}  # type: ignore[attr-defined]
    assert labels["start"] == "-"
    assert labels["inside"] == "Denali#3f9a1c2b"
    assert labels["done"] == "Denali#3f9a1c2b"


def test_each_activity_starts_unlabelled_and_mixed_apps_say_so() -> None:
    activity_logging.start_log_scope()
    activity_logging.label_app("Denali", "3f9a1c2b")
    activity_logging.label_app("Denali", "3f9a1c2b")
    assert _label_of(logging.LogRecord("x", 20, "", 0, "m", None, None)) == "Denali#3f9a1c2b"
    activity_logging.label_app("FNOL", "11112222")
    assert _label_of(logging.LogRecord("x", 20, "", 0, "m", None, None)) == "several apps"
    activity_logging.start_log_scope()
    assert _label_of(logging.LogRecord("x", 20, "", 0, "m", None, None)) == "-"


def test_loading_an_application_labels_the_lines() -> None:
    from domain import Application
    from sqlalchemy import event

    activity_logging.configure_logging()
    activity_logging.configure_logging()  # twice: still one hook
    assert event.contains(Application, "load", activity_logging._on_app_load)
