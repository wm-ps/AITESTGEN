"""When the model plans no missions, the run ends as a visible failure
(missions.plan_missions) instead of showing "exploring" forever."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from explorer_worker import missions


class FakeSession:
    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, model: object, run_id: object) -> SimpleNamespace:
        return SimpleNamespace(status="confirmed", brief={}, branch_points=[], notes=None)

    def add(self, row: object) -> None:
        raise AssertionError("no missions should be saved")

    def commit(self) -> None:
        pass


class FakeJournal:
    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.changes: dict[str, object] = {}

    def update_run(self, **changes: object) -> None:
        self.changes.update(changes)
        if "status" in changes:
            self.statuses.append(str(changes["status"]))

    def event(self, kind: str, title: str, detail: str | None = None) -> None:
        pass

    def screen_rows(self) -> list[object]:
        return []


def test_no_missions_fails_the_run_so_it_can_be_resumed(monkeypatch: pytest.MonkeyPatch) -> None:
    journal = FakeJournal()

    async def no_missions(*args: object) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr(missions, "Journal", lambda run_id: journal)
    monkeypatch.setattr(missions, "Session", lambda engine: FakeSession())
    monkeypatch.setattr(missions.brain, "plan_missions", no_missions)

    assert asyncio.run(missions.plan_missions(uuid.uuid4())) == 0
    assert journal.statuses == ["planning", "failed"]  # never left on "exploring"
    assert journal.changes["error"] == "Couldn't plan any missions from the App Summary"
