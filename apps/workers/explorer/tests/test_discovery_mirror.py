"""A run the worker ends without a hand-off (failed, expired) marks the app's
discovery record failed with its reason (journal._fail_discovery)."""

import uuid
from types import SimpleNamespace

from explorer_worker.journal import _fail_discovery


class FakeSession:
    def __init__(self, record: object) -> None:
        self.record, self.added = record, []

    def exec(self, query: object) -> FakeSession:
        return self

    def first(self) -> object:
        return self.record

    def add(self, row: object) -> None:
        self.added.append(row)


def test_running_discovery_becomes_failed_with_the_reason() -> None:
    record = SimpleNamespace(status="running", failure_reason=None)
    _fail_discovery(FakeSession(record), uuid.uuid4(), "Expired: not confirmed within 14 days")  # type: ignore[arg-type]
    assert record.status == "failed"
    assert record.failure_reason == "Expired: not confirmed within 14 days"


def test_a_finished_discovery_is_left_alone() -> None:
    record = SimpleNamespace(status="complete", failure_reason=None)
    session = FakeSession(record)
    _fail_discovery(session, uuid.uuid4(), "boom")  # type: ignore[arg-type]
    assert record.status == "complete" and session.added == []
