"""Authoring runs (a user's request, carried out by Explorer): the request is
required, they wait for any active run, and pausing or stopping one never
touches the app's discovery record (that follows Explorer's own runs)."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, DiscoveryRun
from explorer_core import ExplorerRun, ExplorerTestCase, run_workflow_name
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select


def _setup() -> tuple[TestClient, str, uuid.UUID]:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org Authoring", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    created = client.post(
        "/applications",
        json={
            "name": "Authoring App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    ).json()
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(created["id"]))
        ).one()
        for other in session.exec(
            select(ExplorerRun).where(ExplorerRun.application_id == application.id)
        ).all():
            other.status = "tested"
            session.add(other)
        session.commit()
        return client, created["id"], application.id


def _discovery_status(application_id: uuid.UUID) -> str | None:
    with Session(engine) as session:
        record = session.exec(
            select(DiscoveryRun)
            .where(DiscoveryRun.application_id == application_id, DiscoveryRun.source == "crawler")
            .order_by(col(DiscoveryRun.created_at).desc())
        ).first()
        return record.status if record else None


def test_a_request_is_required_and_waits_for_an_active_run() -> None:
    client, app_external, app_id = _setup()
    assert (
        client.post(
            f"/explorer/applications/{app_external}/author", json={"prompt": "  "}
        ).status_code
        == 422
    )
    with Session(engine) as session:
        session.add(ExplorerRun(application_id=app_id, status="exploring"))
        session.commit()
    reply = client.post(
        f"/explorer/applications/{app_external}/author", json={"prompt": "Search policy POL-1"}
    )
    assert reply.status_code == 409


def test_pausing_or_stopping_an_authoring_run_leaves_discovery_alone() -> None:
    client, _, app_id = _setup()
    before = _discovery_status(app_id)
    with Session(engine) as session:
        run = ExplorerRun(application_id=app_id, status="exploring", prompt="Search policy POL-1")
        session.add(run)
        session.commit()
        run_id = run.external_id
        assert run_workflow_name(run) == "AuthoringRunWorkflow"
    assert client.post(f"/explorer/runs/{run_id}/pause").status_code == 200
    assert _discovery_status(app_id) == before
    with Session(engine) as session:
        row = session.exec(select(ExplorerRun).where(ExplorerRun.external_id == run_id)).one()
        row.status = "exploring"
        session.add(row)
        session.commit()
    assert client.post(f"/explorer/runs/{run_id}/stop").status_code == 200
    assert _discovery_status(app_id) == before


def test_an_authoring_run_never_stands_in_for_the_apps_exploration() -> None:
    client, app_external, app_id = _setup()
    with Session(engine) as session:
        for run in session.exec(
            select(ExplorerRun).where(ExplorerRun.application_id == app_id)
        ).all():
            session.delete(run)
        session.add(ExplorerRun(application_id=app_id, status="tested", prompt="Check Brad Smith"))
        session.commit()
    # Authoring alone doesn't make Explorer this app's discovery.
    assert client.get(f"/applications/{app_external}").json()["discovery_engine"] == "crawler"

    with Session(engine) as session:
        explored = ExplorerRun(application_id=app_id, status="tested")
        session.add(explored)
        session.commit()
        explored_id = str(explored.external_id)
        session.add(ExplorerRun(application_id=app_id, status="tested", prompt="Check Eric Lin"))
        session.commit()
    # A finished authoring run doesn't hide the latest exploration…
    assert (
        client.get(f"/explorer/applications/{app_external}/runs/latest").json()["id"] == explored_id
    )
    with Session(engine) as session:
        session.add(ExplorerRun(application_id=app_id, status="paused", prompt="Check Sally"))
        session.commit()
    # …but one that can still be resumed shows.
    assert (
        client.get(f"/explorer/applications/{app_external}/runs/latest").json()["prompt"]
        == "Check Sally"
    )
    # A finished one with a possible bug waiting for your answer shows too
    # (its Scenarios tab is the only place to answer it)…
    with Session(engine) as session:
        waiting = ExplorerRun(application_id=app_id, status="tested", prompt="Check Tom")
        session.add(waiting)
        session.flush()
        bug = ExplorerTestCase(
            run_id=waiting.id,
            kind="validation",
            title="t",
            purpose="p",
            expected="e",
            status="known_bug",
        )
        session.add(bug)
        session.commit()
        bug_id = bug.id
    latest = f"/explorer/applications/{app_external}/runs/latest"
    assert client.get(latest).json()["prompt"] == "Check Tom"
    # …until it is answered.
    with Session(engine) as session:
        answered = session.get(ExplorerTestCase, bug_id)
        assert answered is not None
        answered.status = "dropped"
        session.add(answered)
        session.commit()
    assert client.get(latest).json()["id"] == explored_id


def test_the_journey_choice_is_checked_before_starting() -> None:
    from domain import Journey

    client, app_external, app_id = _setup()
    with Session(engine) as session:
        run = DiscoveryRun(application_id=app_id, status="complete")
        session.add(run)
        session.flush()
        session.add(
            Journey(
                application_id=app_id,
                discovery_run_id=run.id,
                name="Create territory",
                identity_key=f"test:{uuid.uuid4()}",
            )
        )
        session.commit()
    url = f"/explorer/applications/{app_external}/author"
    both = {"prompt": "x", "journey_id": str(uuid.uuid4()), "journey_name": "New"}
    assert client.post(url, json=both).status_code == 422
    unknown = {"prompt": "x", "journey_id": str(uuid.uuid4())}
    assert client.post(url, json=unknown).status_code == 404
    taken = client.post(url, json={"prompt": "x", "journey_name": " create TERRITORY "})
    assert taken.status_code == 409
    assert "already exists" in taken.json()["detail"]


def test_on_an_authoring_run_either_answer_to_a_possible_bug_keeps_the_test(monkeypatch) -> None:
    from api import explorer as api_explorer
    from explorer_core import ExplorerTestCase

    sent: list[list[str]] = []

    class _Temporal:
        async def start_workflow(self, _name, args, **_kw):
            sent.append(args)

    async def _client():
        return _Temporal()

    monkeypatch.setattr(api_explorer, "get_temporal_client", _client)
    client, _, app_id = _setup()

    def _bug(run: ExplorerRun) -> uuid.UUID:
        with Session(engine) as session:
            test = ExplorerTestCase(
                run_id=run.id,
                kind="validation",
                title="Billing City max length",
                purpose="",
                steps=[],
                expected="255 characters are accepted",
                observed="Says 100 characters or fewer",
                trust="confirmed",
                script=[],
                status="known_bug",
                code="test.fixme(true, 'known bug');\nawait page.click('x')\n",
            )
            session.add(test)
            session.commit()
            return test.external_id

    with Session(engine) as session:
        authored = ExplorerRun(application_id=app_id, status="tested", prompt="New account")
        explored = ExplorerRun(application_id=app_id, status="tested")
        session.add_all([authored, explored])
        session.commit()
        session.refresh(authored)
        session.refresh(explored)
    for run, verdict, kept in (
        (authored, "ignore", True),
        (authored, "not_a_bug", True),
        (explored, "ignore", False),
    ):
        test_id = _bug(run)
        reply = client.post(f"/explorer/tests/{test_id}/verdict", json={"verdict": verdict})
        assert reply.status_code == 200
        with Session(engine) as session:
            test = session.exec(
                select(ExplorerTestCase).where(ExplorerTestCase.external_id == test_id)
            ).one()
            assert (test.status == "proven") is kept
            if kept:
                assert "fixme" not in (test.code or "")  # never blocked
                assert sent[-1][1:] == ["send", str(test_id)]
    # Explorer's own "Ignore" still leaves the test out.
    assert sum(isinstance(a, list) and "send" in a for a in sent) == 2


def test_an_authoring_run_tries_each_scenario_once(monkeypatch) -> None:
    """Never replayed and never retried: one try each (Explore keeps both,
    as Settings → Explorer limits say)."""
    from api import authoring as api_authoring

    class _Temporal:
        async def start_workflow(self, *_a, **_kw):
            return None

    async def _client():
        return _Temporal()

    async def _pollers(*_a):
        return True

    monkeypatch.setattr(api_authoring, "get_temporal_client", _client)
    monkeypatch.setattr(api_authoring, "has_pollers", _pollers)
    client, app_external, app_id = _setup()
    reply = client.post(
        f"/explorer/applications/{app_external}/author",
        json={"prompt": "Create an account", "journey_name": f"Accounts {uuid.uuid4()}"},
    )
    assert reply.status_code in (200, 201, 202), reply.text
    with Session(engine) as session:
        run = session.exec(
            select(ExplorerRun)
            .where(ExplorerRun.application_id == app_id, ExplorerRun.prompt == "Create an account")
        ).one()
        assert run.limits["proof_replays"] == 0
        assert "test_retries" not in run.limits  # retried like Explore (worker default)
