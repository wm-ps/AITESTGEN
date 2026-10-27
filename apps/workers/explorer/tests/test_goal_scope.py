"""The run's Goal as a strict scope (explorer_worker.goal): read once after
the App Summary is confirmed, reused after that; an empty goal changes
nothing."""

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from explorer_worker import brain, goal

RUN = uuid.uuid4()


class FakeJournal:
    def __init__(self, brief: dict[str, Any]) -> None:
        self.run_id = RUN
        self.brief = brief
        self.fits: dict[str, str] = {}

    def run_brief(self) -> dict[str, Any]:
        return self.brief

    def update_run(self, **changes: Any) -> None:
        self.brief = changes.get("brief", self.brief)

    def set_goal_fit(self, fits: dict[str, str]) -> None:
        self.fits = fits

    def event(self, *args: object) -> None:
        pass

    def screen_rows(self) -> list[object]:
        names = ["Find your policy", "Policy selection", "Check a claim"]
        return [SimpleNamespace(name=n, entity=None, view_kind="form", purpose=None) for n in names]


@pytest.fixture
def journal(monkeypatch: pytest.MonkeyPatch) -> FakeJournal:
    j = FakeJournal({"focus": "Only the claim reporting flow, up to policy search"})
    monkeypatch.setattr(goal, "Journal", lambda run_id: j)
    return j


def _model(monkeypatch: pytest.MonkeyPatch, fits: dict[str, str]) -> list[str]:
    calls: list[str] = []

    async def read_goal(text: str, screens: list[dict[str, Any]]) -> dict[str, Any]:
        calls.append(text)
        return {"rule": "Only claim reporting, up to Find your policy.", "fits": fits}

    monkeypatch.setattr(brain, "read_goal", read_goal)
    return calls


def test_empty_goal_has_no_scope(monkeypatch: pytest.MonkeyPatch, journal: FakeJournal) -> None:
    journal.brief = {"focus": "  "}
    calls = _model(monkeypatch, {})
    assert asyncio.run(goal.ensure_scope(RUN)) is None
    assert calls == []


def test_scope_is_created_once_and_reused(monkeypatch: pytest.MonkeyPatch, journal: FakeJournal) -> None:
    calls = _model(monkeypatch, {"Find your policy": "inside"})
    first = asyncio.run(goal.ensure_scope(RUN))
    second = asyncio.run(goal.ensure_scope(RUN))
    assert first == second == journal.brief["scope"]
    assert calls == ["Only the claim reporting flow, up to policy search"]


def test_stop_point_matched_by_meaning_is_kept_from_the_model(
    monkeypatch: pytest.MonkeyPatch, journal: FakeJournal
) -> None:
    _model(
        monkeypatch,
        {"Find your policy": "inside", "Policy selection": "past_stop", "Check a claim": "outside", "Bogus": "maybe"},
    )
    scope = asyncio.run(goal.ensure_scope(RUN))
    assert scope is not None
    assert journal.fits == {"Find your policy": "inside", "Policy selection": "past_stop", "Check a claim": "outside"}
    assert scope["rule"] == "Only claim reporting, up to Find your policy."


def test_in_goal_and_stops_walk() -> None:
    assert goal.in_goal(None) and goal.in_goal("inside")
    assert not any(goal.in_goal(f) for f in ("on_the_way", "past_stop", "outside"))
    assert goal.stops_walk("past_stop") and goal.stops_walk("outside")
    assert not goal.stops_walk("on_the_way") and not goal.stops_walk(None)


def test_scope_text_is_strict_only_with_a_goal() -> None:
    text = brain.scope({"focus": "x", "scope": {"rule": "Only claim reporting up to Find your policy."}})
    assert "STRICT" in text and "Only claim reporting up to Find your policy." in text
    assert brain.scope({}) == ""
