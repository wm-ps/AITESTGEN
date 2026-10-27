"""The App Summary's 14-day wait ran out (activities.expire_run_activity)."""

import asyncio
import uuid

import pytest
from explorer_worker import activities


class FakeJournal:
    def __init__(self, status: str) -> None:
        self._status, self.changes, self.events = status, {}, []

    def status(self) -> str:
        return self._status

    def event(self, kind: str, title: str, detail: str | None = None) -> None:
        self.events.append(title)

    def update_run(self, **changes: object) -> None:
        self.changes.update(changes)


@pytest.mark.parametrize(
    ("status", "result", "expired"),
    [("awaiting_confirmation", "expired", True), ("stopped", "stopped", False)],
)
def test_only_a_still_waiting_run_expires(
    monkeypatch: pytest.MonkeyPatch, status: str, result: str, expired: bool
) -> None:
    journal = FakeJournal(status)
    monkeypatch.setattr(activities, "Journal", lambda run_id: journal)
    assert asyncio.run(activities.expire_run_activity(str(uuid.uuid4()), 14)) == result
    assert (journal.changes.get("status") == "expired") is expired
    if expired:
        assert journal.changes["headline"] == "Expired: not confirmed within 14 days"
        assert journal.events == ["App Summary expired"]
