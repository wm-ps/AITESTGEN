"""A run whose test planning crashed stays failed (tests_stage.finish_testing)."""

import uuid

import pytest
from explorer_worker import tests_stage


class FakeJournal:
    def __init__(self, status: str) -> None:
        self._status, self.changes = status, {}

    def status(self) -> str:
        return self._status

    def update_run(self, **changes: object) -> None:
        self.changes.update(changes)


@pytest.mark.parametrize("status", ["failed", "stopped", "paused"])
def test_a_failed_or_halted_run_is_not_marked_tested(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    journal = FakeJournal(status)
    monkeypatch.setattr(tests_stage, "Journal", lambda run_id: journal)
    tests_stage.finish_testing(uuid.uuid4())
    assert journal.changes == {}  # status (and the error it shows) left alone
