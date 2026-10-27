"""Automatic healing is off unless AUTO_HEAL_ENABLED=1; the manual retry still heals."""

import asyncio

import pytest
from execution_worker import activities
from workflows.execution_workflow import HealTestActivityInput


def _input(manual: bool) -> HealTestActivityInput:
    return HealTestActivityInput(
        application_id="a", test_run_id="r", test_result_id="t", triggered_manually=manual
    )


def test_automatic_heal_is_skipped_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activities, "AUTO_HEAL_ENABLED", False)
    claimed: list[str] = []
    monkeypatch.setattr(activities, "_claim_heal_sync", lambda rid: claimed.append(rid) or False)
    asyncio.run(activities.heal_test_activity(_input(manual=False)))
    assert claimed == []  # never even tried to start a heal


def test_manual_heal_still_runs_when_automatic_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(activities, "AUTO_HEAL_ENABLED", False)
    claimed: list[str] = []
    monkeypatch.setattr(activities, "_claim_heal_sync", lambda rid: claimed.append(rid) or False)
    asyncio.run(activities.heal_test_activity(_input(manual=True)))
    assert claimed == ["t"]  # went on to claim it (then stopped: already claimed)
