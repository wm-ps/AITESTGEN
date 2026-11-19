"""A test that didn't reach its outcome is repaired, not dropped: why is
worked out from the page, the test fixed and tried again — the same test
(title, purpose, expected never change) — up to the retry limit; only the
user knows → asked; the app can't do it → said plainly."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from domain import Application, Organization
from explorer_core import ExplorerRun, ExplorerTestCase
from explorer_worker import tests_stage
from explorer_worker.db import engine
from explorer_worker.journal import Journal
from sqlmodel import Session

FINAL = SimpleNamespace(inventory={"aria": '- textbox "Stage"'}, shot=b"png")
INFO = {"title": "Amount refuses a negative value", "kind": "validation", "expected": "Refused"}


def _test(repairs: list[str] | None = None) -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        app = Application(
            organization_id=org.id, name="x", url="https://x", environment="staging", secret_ref=""
        )
        session.add(app)
        session.flush()
        run = ExplorerRun(application_id=app.id, status="testing")
        session.add(run)
        session.flush()
        test = ExplorerTestCase(
            run_id=run.id,
            kind="validation",
            title=INFO["title"],
            purpose="p",
            steps=["Enter -1 in Amount", "Press Save"],
            expected="Refused",
            trust="confirmed",
            script=[{"how_to_run": "Enter -1 in Amount, save", "repairs": repairs or []}],
            status="building",
        )
        session.add(test)
        session.commit()
        return run.id, test.id


async def _repair(run_id: uuid.UUID, test_id: uuid.UUID) -> tuple[bool, str]:
    with Session(engine) as session:
        meta = session.get(ExplorerTestCase, test_id).script[0]  # type: ignore[union-attr]
    return await tests_stage.repair(
        Journal(run_id), test_id, meta, INFO, FINAL, "Refused for Stage", [], [], lambda: None
    )


def _row(test_id: uuid.UUID) -> ExplorerTestCase:
    with Session(engine) as session:
        row = session.get(ExplorerTestCase, test_id)
        assert row is not None
        return row


def _reply(monkeypatch: pytest.MonkeyPatch, **reply: Any) -> list[int]:
    calls: list[int] = []

    async def repair_test(*_a: Any) -> dict[str, Any]:
        calls.append(1)
        return reply

    monkeypatch.setattr(tests_stage.brain, "repair_test", repair_test)
    return calls


async def test_an_incomplete_setup_is_fixed_and_the_same_test_tried_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reply(
        monkeypatch,
        cause="setup",
        diagnosis="Stage and Owner were left empty",
        how_to_run="Fill Stage and Owner, enter -1 in Amount, save",
        steps=["Fill Stage and Owner", "Enter -1 in Amount", "Press Save"],
    )
    run_id, test_id = _test()
    assert await _repair(run_id, test_id) == (True, "")
    row = _row(test_id)
    assert row.status == "planned" and row.title == INFO["title"] and row.expected == "Refused"
    assert row.steps[0] == "Fill Stage and Owner"
    assert row.script[0]["how_to_run"].startswith("Fill Stage and Owner")
    assert row.script[0]["repairs"] == ["setup: Stage and Owner were left empty"]


async def test_a_route_problem_is_tried_after_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    _reply(monkeypatch, cause="route", diagnosis="New Lead didn't open", how_to_run="Open it")
    run_id, test_id = _test()
    assert await _repair(run_id, test_id) == (True, "")
    assert _row(test_id).script[0]["unreached"] is True


async def test_only_the_user_knows_so_they_are_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    _reply(monkeypatch, cause="needs_user", diagnosis="needs an account", question="Which one?")
    answers = ["Acme"]

    async def ask(*_a: Any, **_k: Any) -> str | None:
        return answers.pop(0) if answers else None

    monkeypatch.setattr(tests_stage, "ask", ask)
    run_id, test_id = _test()
    assert await _repair(run_id, test_id) == (True, "")
    assert _row(test_id).script[0]["how_to_run"].endswith("The user said: Acme")
    run_id, test_id = _test()  # no answer: said plainly, never guessed
    assert await _repair(run_id, test_id) == (False, "Waiting for your answer: Which one?")


async def test_an_app_bug_is_judged_and_an_impossible_test_said_plainly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reply(monkeypatch, cause="app_bug", diagnosis="the save failed with a server error")
    run_id, test_id = _test()
    assert await _repair(run_id, test_id) == (True, "")
    assert "that is the outcome" in _row(test_id).script[0]["how_to_run"]
    _reply(monkeypatch, cause="impossible", diagnosis="there is no Amount field")
    run_id, test_id = _test()
    ok, why = await _repair(run_id, test_id)
    assert not ok and why == "This app has nothing that can carry it out: there is no Amount field"


async def test_repairs_stop_at_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _reply(monkeypatch, cause="setup", diagnosis="x", how_to_run="y")
    run_id, test_id = _test(repairs=["setup: a", "route: b", "step: c"])
    ok, why = await _repair(run_id, test_id)
    assert not ok and why == "Refused for Stage — still after 3 repair(s)"
    assert calls == []  # no model call once the limit is reached


def test_a_loading_text_that_stays_on_loaded_pages_is_never_blamed() -> None:
    from explorer_core import ExplorerScreen
    from explorer_worker.repair import live_state

    run_id, _ = _test()
    with Session(engine) as session:
        session.add(
            ExplorerScreen(
                run_id=run_id,
                signature="form",
                name="Form",
                url="https://x/form",
                url_pattern="/form",
                aria='- textbox "Stage"\n- alert "Loading"',
            )
        )
        session.commit()
    page = '- textbox "Stage"\n- alert "Loading"'
    quiet = live_state({"aria": page, "loading": False}, run_id)
    assert quiet.startswith("Live check: nothing on the page is loading right now")
    assert 'alert "Loading" was also on the pages Explorer saved' in quiet
    busy = live_state({"aria": page, "loading": True}, run_id)
    assert busy.startswith("Live check: the page IS still loading")
    assert live_state({"aria": '- textbox "Stage"'}, run_id) == ""  # nothing measured, nothing said


async def test_the_repair_gets_the_live_page_and_the_values_never_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from explorer_worker import scope

    got: list[tuple[Any, ...]] = []

    async def repair_test(*a: Any) -> dict[str, Any]:
        got.append(a)
        return {"cause": "impossible", "diagnosis": "x"}

    monkeypatch.setattr(tests_stage.brain, "repair_test", repair_test)
    run_id, test_id = _test()
    meta = {"how_to_run": "h", "evidence": [{"value": "Acme 9", "source": scope.UNSEEN}]}
    final = SimpleNamespace(inventory={"aria": '- textbox "Stage"', "loading": False}, shot=b"png")
    await tests_stage.repair(
        Journal(run_id), test_id, meta, INFO, final, "Refused", [], [], lambda: None
    )
    failure, live = got[0][1], got[0][-1]
    assert "Never seen while exploring: Acme 9" in failure
    assert live.startswith("Live check: nothing on the page is loading")
