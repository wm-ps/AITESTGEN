"""Explorer "Things that look wrong" → False alarm: the finding leaves the
list, its open bug question closes, and the app's behaviour is remembered."""

import uuid

from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application
from explorer_core import (
    ExplorerHealthIssue,
    ExplorerKnowledge,
    ExplorerQuestion,
    ExplorerRun,
)
from fastapi.testclient import TestClient
from sqlmodel import Session, select


def _signed_in_client(org_name: str) -> TestClient:
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def test_false_alarm_closes_the_finding_and_is_organization_scoped() -> None:
    init_db()
    client = _signed_in_client("Org False Alarm")
    other = _signed_in_client("Org False Alarm Other")
    created = client.post(
        "/applications",
        json={
            "name": "False Alarm App",
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
        run = ExplorerRun(application_id=application.id, status="tested")
        session.add(run)
        session.flush()
        issue = ExplorerHealthIssue(
            run_id=run.id, kind="looks_wrong", severity="medium", title="Odd date", url="/x"
        )
        session.add(issue)
        session.flush()
        question = ExplorerQuestion(
            run_id=run.id, kind="rule", question="Is that right?", issue_id=issue.id, options=[]
        )
        session.add(question)
        session.commit()
        issue_id, question_id, app_id = issue.id, question.id, application.id

    assert other.post(f"/explorer/health/{issue_id}/false-alarm").status_code == 404
    assert client.post(f"/explorer/health/{issue_id}/false-alarm").status_code == 204

    with Session(engine) as session:
        assert session.get(ExplorerHealthIssue, issue_id).kind == "false_alarm"
        assert session.get(ExplorerQuestion, question_id).status == "dismissed"
        facts = session.exec(
            select(ExplorerKnowledge.text).where(ExplorerKnowledge.application_id == app_id)
        ).all()
        assert any("Odd date" in f for f in facts)
