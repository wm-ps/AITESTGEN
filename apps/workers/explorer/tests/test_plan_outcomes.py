"""Explore's planning keeps every planned scenario: what is tried, and what
isn't with why (a duplicate, over the run's limit) — none silently gone."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from domain import Application, Organization
from explorer_core import ExplorerRun, ExplorerScreen, ExplorerTestCase
from explorer_worker import tests_stage
from explorer_worker.db import engine
from sqlmodel import Session, select


def _run() -> uuid.UUID:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        app = Application(
            organization_id=org.id, name="x", url="https://x", environment="staging", secret_ref=""
        )
        session.add(app)
        session.flush()
        run = ExplorerRun(application_id=app.id, status="exploring", limits={"max_scenarios": 10})
        session.add(run)
        session.flush()
        session.add(
            ExplorerScreen(
                run_id=run.id,
                signature="form",
                name="Form",
                view_kind="form",
                url="https://x/form",
                url_pattern="/form",
                aria='- button "Save"\n- button "Cancel"',
            )
        )
        session.commit()
        return run.id


async def test_over_the_limit_and_duplicates_are_kept_with_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def planned(i: int) -> dict[str, Any]:
        return {
            "kind": "form_submission",
            "title": f"Check {i}",
            "expected": "x",
            "start_screen": "Form",
            "coverage": f"X-{i}",
            "category": "happy",
            "path": [{"screen": "Form", "element": 'button "Save"'}],
        }

    async def plan(*_a: Any, **_k: Any) -> list[dict[str, Any]]:
        return [planned(i) for i in range(12)] + [{**planned(0), "title": "Check 0 again"}]

    async def nothing(*_a: Any, **_k: Any) -> Any:
        return []

    async def scope_ok(*_a: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        return [], {}

    async def no_map(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"aim": "", "items": [], "not_applicable": []}

    monkeypatch.setattr(tests_stage.brain, "plan_tests", plan)
    monkeypatch.setattr(tests_stage.brain, "coverage_map", no_map)
    monkeypatch.setattr(tests_stage.brain, "review_plan", nothing)
    monkeypatch.setattr(tests_stage.scope, "check_scope", scope_ok)
    monkeypatch.setattr(tests_stage, "ensure_scope", nothing)
    target = SimpleNamespace(notes=None, non_production=True, requires_login=False)
    monkeypatch.setattr(tests_stage, "load_target", lambda _r: target)
    run_id = _run()
    await tests_stage.plan_tests(run_id)
    with Session(engine) as session:
        rows = session.exec(
            select(ExplorerTestCase).where(
                ExplorerTestCase.run_id == run_id, ExplorerTestCase.kind != "page_quality"
            )
        ).all()
    assert len(rows) == 13  # every planned scenario has a row
    tried = [r for r in rows if r.status == "planned"]
    assert len(tried) == 10
    assert all(r.script[0]["path"] and r.script[0]["category"] == "happy" for r in rows)
    why = sorted(r.drop_reason or "" for r in rows if r.status == "dropped")
    assert why == [
        "Left out before trying: the same check as “Check 0”",
        "Not tried: over the limit of 10 scenarios (Settings → Explorer limits)",
        "Not tried: over the limit of 10 scenarios (Settings → Explorer limits)",
    ]


async def test_explore_decides_the_coverage_map_first_and_follows_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def decide(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "aim": "Every screen as the checklist applies",
            "items": [
                {"screen": "Form", "id": "E-01", "what": "Cancel", "evidence": 'button "Cancel"'}
            ],
            "not_applicable": [{"screen": "Form", "id": "L-01", "why": "not a list"}],
        }

    told: list[str] = []

    async def plan(*a: Any, **_k: Any) -> list[dict[str, Any]]:
        told.append(a[5] or "")
        return []

    async def nothing(*_a: Any, **_k: Any) -> Any:
        return []

    async def scope_ok(*_a: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        return [], {}

    monkeypatch.setattr(tests_stage.brain, "coverage_map", decide)
    monkeypatch.setattr(tests_stage.brain, "plan_tests", plan)
    monkeypatch.setattr(tests_stage.brain, "review_plan", nothing)
    monkeypatch.setattr(tests_stage.scope, "check_scope", scope_ok)
    monkeypatch.setattr(tests_stage, "ensure_scope", nothing)
    target = SimpleNamespace(notes=None, non_production=True, requires_login=False)
    monkeypatch.setattr(tests_stage, "load_target", lambda _r: target)
    run_id = _run()
    await tests_stage.plan_tests(run_id)
    assert "Write exactly one test for each item" in told[0] and '"E-01"' in told[0]
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        assert run is not None
        assert [i["id"] for i in run.insights["coverage_map"]["items"]] == ["E-01"]
