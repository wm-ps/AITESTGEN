"""Read-only "viewer" role — enforced server-side.

- `block_viewer_writes` (one app-wide dependency): a viewer gets 403 on every
  POST/PUT/PATCH/DELETE except logout — including actions that start
  background work and the recording-session token the recording WebSocket
  needs — while every read still works.
- The Allure report and the test-suite download are reads a viewer may not
  have (`NotViewerDep`).
- Members and admins are unaffected.
- Change role: admin-only, own Organization, shared role list, never leaves an
  Organization without an admin (row-locked), effective on the next request.

Requires PostgreSQL + Vault + Temporal (creating an Application stores its
credentials and starts discovery), same as test_test_runs.py.
"""

import threading
import uuid

import pytest
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import PlatformUser
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _admin(org_name: str) -> tuple[TestClient, str]:
    init_db()
    email = f"admin-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name=org_name, name="Admin")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client, email


def _invite(
    admin: TestClient, monkeypatch: pytest.MonkeyPatch, role: str
) -> tuple[TestClient, str]:
    captured: list[str] = []
    monkeypatch.setattr("api.main.send_invite_email", lambda _to, token: captured.append(token))
    email = f"{role}-{uuid.uuid4()}@example.com"
    assert admin.post("/invites", json={"email": email, "role": role}).status_code == 201
    client = TestClient(app)
    accepted = client.post(
        "/invites/accept", json={"token": captured[-1], "name": "Teammate", "password": "pw123456"}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == role
    return client, email


def _application(admin: TestClient) -> dict:
    response = admin.post(
        "/applications",
        json={
            "name": f"Viewer App {uuid.uuid4().hex[:6]}",
            "url": "https://staging.example.com",
            "environment": "staging",
            "auth_method": "standard_login",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def org(monkeypatch: pytest.MonkeyPatch) -> dict:
    admin, admin_email = _admin(f"Org Viewer {uuid.uuid4().hex[:6]}")
    viewer, viewer_email = _invite(admin, monkeypatch, "viewer")
    member, member_email = _invite(admin, monkeypatch, "member")
    return {
        "admin": admin,
        "admin_email": admin_email,
        "viewer": viewer,
        "viewer_email": viewer_email,
        "member": member,
        "member_email": member_email,
        "application": _application(admin),
    }


def _writes(app_id: str) -> list[tuple[str, str, dict | None]]:
    """At least one write per area — each would change something or start
    background work if allowed."""
    some = str(uuid.uuid4())
    return [
        ("POST", "/applications", {"name": "x", "url": "https://x.example.com"}),
        ("POST", "/applications/test-connection", {"url": "https://x.example.com"}),
        ("POST", f"/applications/{app_id}/pause-discovery", None),
        ("POST", f"/applications/{app_id}/generate-suite", None),
        ("POST", f"/applications/{app_id}/test-runs", None),
        ("POST", f"/applications/{app_id}/test-runs/{some}/cancel", None),
        ("POST", f"/test-results/{some}/heal", None),
        ("POST", f"/applications/{app_id}/schedules", {"name": "x"}),
        ("POST", f"/schedules/{some}/run-now", None),
        ("PATCH", f"/journeys/{some}", {"name": "x"}),
        ("DELETE", f"/scenarios/{some}", None),
        ("POST", f"/applications/{app_id}/live-test-cases", {"prompt": "x", "journey_name": "x"}),
        # The recording worker's WebSocket only accepts a token minted here.
        (
            "POST",
            f"/applications/{app_id}/recordings/sessions",
            {"auth_mode": "fresh", "name": "x"},
        ),
    ]


def test_viewer_cannot_write_anything(org: dict) -> None:
    app_id = org["application"]["id"]
    for method, path, body in _writes(app_id):
        response = org["viewer"].request(method, path, json=body)
        assert response.status_code == 403, (method, path, response.status_code, response.text)
        assert response.json()["detail"] == "view-only access"


def test_viewer_can_read(org: dict) -> None:
    app_id = org["application"]["id"]
    for path in (
        "/auth/me",
        "/applications",
        f"/applications/{app_id}/journeys",
        f"/applications/{app_id}/scenarios",
        f"/applications/{app_id}/test-runs",
        f"/applications/{app_id}/schedules",
    ):
        response = org["viewer"].get(path)
        assert response.status_code == 200, (path, response.status_code, response.text)


def test_viewer_screenshots_and_traces_are_not_blocked(org: dict) -> None:
    # Unknown result: 404 from the route itself, never a view-only 403.
    response = org["viewer"].get(f"/test-results/{uuid.uuid4()}/artifacts")
    assert response.status_code == 404


def test_viewer_cannot_open_allure_report_or_download_suite(org: dict) -> None:
    app_id = org["application"]["id"]
    for path in (
        f"/applications/{app_id}/test-runs/{uuid.uuid4()}/allure-report",
        f"/applications/{app_id}/test-suites/download",
    ):
        viewer = org["viewer"].get(path)
        assert viewer.status_code == 403, (path, viewer.text)
        # The same request from a member reaches the route (no view-only 403).
        assert org["member"].get(path).status_code != 403, path


def test_viewer_can_log_out(org: dict) -> None:
    assert org["viewer"].post("/auth/logout").status_code in (200, 204)


def test_members_and_admins_still_write(org: dict) -> None:
    app_id = org["application"]["id"]
    # Unknown run -> 404 from the route itself: the guard let them through.
    for client in (org["member"], org["admin"]):
        response = client.post(f"/applications/{app_id}/test-runs/{uuid.uuid4()}/cancel")
        assert response.status_code == 404, response.text


def test_signed_out_writes_still_reach_their_own_auth() -> None:
    response = TestClient(app).post(
        "/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    assert response.status_code == 401


# --- Change role ---------------------------------------------------------------


def test_admin_changes_a_member_to_viewer_and_back(org: dict) -> None:
    path = f"/team/{org['member_email']}/role"

    to_viewer = org["admin"].patch(path, json={"role": "viewer"})
    assert to_viewer.status_code == 200, to_viewer.text
    assert to_viewer.json()["role"] == "viewer"
    to_member = org["admin"].patch(path, json={"role": "member"})
    assert to_member.json()["role"] == "member"


def test_change_role_takes_effect_on_the_next_request(org: dict) -> None:
    app_id = org["application"]["id"]
    cancel = f"/applications/{app_id}/test-runs/{uuid.uuid4()}/cancel"
    assert org["viewer"].post(cancel).status_code == 403

    org["admin"].patch(f"/team/{org['viewer_email']}/role", json={"role": "member"})

    # Same session, no re-login: now reaches the route.
    assert org["viewer"].post(cancel).status_code == 404


def test_change_role_rejections(org: dict) -> None:
    admin = org["admin"]
    assert (
        org["member"].patch(f"/team/{org['viewer_email']}/role", json={"role": "admin"}).status_code
        == 403
    )
    assert (
        org["viewer"]
        .patch(f"/team/{org['member_email']}/role", json={"role": "viewer"})
        .status_code
        == 403
    )
    assert (
        admin.patch(f"/team/{org['admin_email']}/role", json={"role": "member"}).status_code == 422
    )
    assert (
        admin.patch(f"/team/{org['member_email']}/role", json={"role": "owner"}).status_code == 422
    )
    assert (
        admin.patch(
            f"/team/nobody-{uuid.uuid4()}@example.com/role", json={"role": "viewer"}
        ).status_code
        == 404
    )


def test_change_role_is_scoped_to_the_callers_organization(
    org: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_admin, _ = _admin(f"Org Viewer Other {uuid.uuid4().hex[:6]}")

    response = other_admin.patch(f"/team/{org['member_email']}/role", json={"role": "viewer"})

    assert response.status_code == 404
    with Session(engine) as session:
        member = session.exec(
            select(PlatformUser).where(PlatformUser.email == org["member_email"])
        ).one()
    assert member.role == "member"


def _admin_count(admin_email: str) -> int:
    with Session(engine) as session:
        org_id = session.exec(
            select(PlatformUser.organization_id).where(PlatformUser.email == admin_email)
        ).one()
        return len(
            session.exec(
                select(PlatformUser).where(
                    PlatformUser.organization_id == org_id, PlatformUser.role == "admin"
                )
            ).all()
        )


def test_two_admins_demoting_each_other_never_leave_the_org_without_an_admin(
    org: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    second_admin, second_email = _invite(org["admin"], monkeypatch, "admin")
    first_admin, first_email = org["admin"], org["admin_email"]

    # Hold the Organization's admin rows locked, so both requests are
    # in flight together and must queue on the same lock.
    with Session(engine) as blocker:
        org_id = blocker.exec(
            select(PlatformUser.organization_id).where(PlatformUser.email == first_email)
        ).one()
        blocker.exec(
            select(PlatformUser)
            .where(PlatformUser.organization_id == org_id, PlatformUser.role == "admin")
            .with_for_update()
        ).all()
        results: dict[str, int] = {}

        def demote(client: TestClient, target: str, key: str) -> None:
            results[key] = client.patch(f"/team/{target}/role", json={"role": "member"}).status_code

        threads = [
            threading.Thread(target=demote, args=(first_admin, second_email, "first")),
            threading.Thread(target=demote, args=(second_admin, first_email, "second")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=1.5)
        assert all(t.is_alive() for t in threads), "both changes must wait on the admin-row lock"
        blocker.commit()  # release
    for t in threads:
        t.join(timeout=15)

    assert sorted(results.values()) in ([200, 403], [200, 409]), results
    assert _admin_count(first_email) == 1
