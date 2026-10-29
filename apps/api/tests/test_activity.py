"""Admin Activity page — GET /activity.

Requires a live PostgreSQL (same convention as test_team.py).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from api.activity import _collect
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import ActivityEvent, Application, PlatformUser, TestRun
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="no PostgreSQL reachable at DATABASE_URL — start docker compose to run this test",
)


def _admin_client(org_name: str) -> tuple[TestClient, uuid.UUID]:
    init_db()
    email = f"admin-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Activity Admin")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    with Session(engine) as session:
        user = session.exec(select(PlatformUser).where(PlatformUser.email == email)).one()
        return client, user.organization_id


def _add_member(admin: TestClient, monkeypatch: pytest.MonkeyPatch, role: str) -> TestClient:
    captured: list[str] = []
    monkeypatch.setattr("api.main.send_invite_email", lambda _email, token: captured.append(token))
    email = f"{role}-{uuid.uuid4()}@example.com"
    admin.post("/invites", json={"email": email, "role": role})
    TestClient(app).post(
        "/invites/accept", json={"token": captured[-1], "name": "Teammate", "password": "Vantage-test-pw-k7q2x"}
    )
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "Vantage-test-pw-k7q2x"})
    return client


def _application_with_run(organization_id: uuid.UUID, **counts: int) -> str:
    with Session(engine) as session:
        application = Application(
            organization_id=organization_id,
            name=f"Activity App {uuid.uuid4().hex[:6]}",
            url="https://example.com/",
            environment="staging",
            auth_method="standard_login",
            secret_ref="unused",
        )
        session.add(application)
        session.flush()
        session.add(
            TestRun(
                application_id=application.id,
                run_number=1,
                status="completed",
                environment_snapshot="staging",
                target_base_url_snapshot="https://example.com/",
                triggered_by_name="Ravi",
                **counts,
            )
        )
        session.commit()
        return application.name


def test_activity_is_admin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, _ = _admin_client("Org Activity Admin Only")
    member = _add_member(admin, monkeypatch, "member")
    viewer = _add_member(admin, monkeypatch, "viewer")

    assert admin.get("/activity").status_code == 200
    assert member.get("/activity").status_code == 403
    assert viewer.get("/activity").status_code == 403


def test_settings_change_shows_before_and_after() -> None:
    admin, _ = _admin_client("Org Activity Settings")
    original = admin.get("/settings").json()["max_heal_attempts"]
    try:
        admin.patch("/settings", json={"max_heal_attempts": original + 1})
        items = admin.get("/activity", params={"category": "settings"}).json()["items"]
    finally:
        admin.patch("/settings", json={"max_heal_attempts": original})

    row = items[0]
    assert row["summary"] == f"Changed max heal attempts from {original} to {original + 1}"
    assert row["actor"] == "Activity Admin"
    assert row["outcome"] == "changed"
    assert row["details"]["changes"] == [
        {"field": "max heal attempts", "before": str(original), "after": str(original + 1)}
    ]


def test_team_changes_are_recorded_and_scoped_to_the_org(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, _ = _admin_client("Org Activity Team")
    _add_member(admin, monkeypatch, "viewer")
    other_admin, _ = _admin_client("Org Activity Other")

    summaries = [i["summary"] for i in admin.get("/activity").json()["items"]]
    assert any(s.startswith("Invited ") and s.endswith(" as viewer") for s in summaries)
    assert any("joined as viewer" in s for s in summaries)
    assert other_admin.get("/activity").json()["items"] == []


def test_failed_test_run_appears_with_its_counts_and_the_failures_filter() -> None:
    admin, organization_id = _admin_client("Org Activity Runs")
    app_name = _application_with_run(organization_id, total_count=5, passed_count=3, failed_count=2)

    page = admin.get("/activity", params={"outcome": "failed"}).json()
    [row] = page["items"]
    assert row["summary"] == f"Test run #1 on {app_name} — 3 passed, 2 failed"
    assert row["reason"] == "2 of 5 tests failed"
    assert row["actor"] == "Ravi"
    assert row["target_tab"] == "runs"
    assert page["facets"]["outcome"] == {"failed": 1}
    assert page["facets"]["category"] == {"test_runs": 1}
    assert admin.get("/activity", params={"outcome": "done"}).json()["items"] == []


def test_paging_never_skips_rows_in_either_direction() -> None:
    _, organization_id = _admin_client("Org Activity Paging")
    now = datetime.now(UTC)
    with Session(engine) as session:
        for minutes in (1, 2, 3):
            session.add(
                ActivityEvent(
                    organization_id=organization_id,
                    actor_name="A",
                    category="settings",
                    outcome="changed",
                    summary=f"event {minutes}",
                    created_at=now - timedelta(minutes=minutes),
                )
            )
        session.commit()

        def walk(oldest_first: bool) -> list[str]:
            seen: list[str] = []
            cursor = None
            for _ in range(5):
                items, cursor = _collect(
                    session,
                    organization_id,
                    since=now - timedelta(days=1),
                    cursor=cursor,
                    limit=2,
                    oldest_first=oldest_first,
                )
                seen += [i.summary for i in items]
                if cursor is None:
                    break
            return seen

        assert walk(oldest_first=False) == ["event 1", "event 2", "event 3"]
        assert walk(oldest_first=True) == ["event 3", "event 2", "event 1"]


def test_sign_ins_and_failed_sign_ins_are_recorded() -> None:
    admin, _ = _admin_client("Org Activity Sign-ins")
    email = admin.get("/auth/me").json()["email"]
    assert TestClient(app).post("/auth/login", json={"email": email, "password": "nope"}).status_code == 401

    rows = admin.get("/activity", params={"category": "account"}).json()["items"]
    assert [(r["summary"], r["outcome"]) for r in rows[:2]] == [
        (f"Failed sign-in for {email} (wrong password)", "failed"),
        ("Activity Admin signed in", "done"),
    ]
