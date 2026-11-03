"""Application environments — extra deployments the same test cases run
against: add / edit / remove, the "mirror the default app's login details"
rules, who may do what, the delete guards, and the run / schedule / reveal
surfaces that take an environment id.

Needs PostgreSQL + Vault + Temporal (creating an Application stores its
credentials and creates its default schedules), same as test_test_runs.py.
"""

import io
import json
import uuid
import zipfile

import pytest
from api.auth import hash_password
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import (
    Application,
    ApplicationEnvironment,
    DiscoveryRun,
    Journey,
    PlatformUser,
    Scenario,
    Schedule,
    TestAsset,
    TestRun,
    TestSuite,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from secrets_client import SecretRef, VaultSecretsClient
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
    not _db_available(), reason="requires PostgreSQL + Vault + Temporal — start docker compose"
)


@pytest.fixture(autouse=True)
def _domain_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest only stubs the copy `api.main` imported; environments.py has its own.
    monkeypatch.setattr("api.environments.require_approved_domain", lambda *args: None)


def _admin(org_name: str) -> tuple[TestClient, uuid.UUID]:
    init_db()
    email = f"admin-{uuid.uuid4()}@example.com"
    user = seed(email=email, password="pw", org_name=org_name, name="Admin")
    client = TestClient(app)
    assert client.post("/auth/login", json={"email": email, "password": "pw"}).status_code == 200
    return client, user.organization_id


def _user_in_org(organization_id: uuid.UUID, role: str) -> TestClient:
    email = f"{role}-{uuid.uuid4()}@example.com"
    with Session(engine) as session:
        session.add(
            PlatformUser(
                organization_id=organization_id,
                email=email,
                name=role.title(),
                hashed_password=hash_password("pw"),
                role=role,
            )
        )
        session.commit()
    client = TestClient(app)
    assert client.post("/auth/login", json={"email": email, "password": "pw"}).status_code == 200
    return client


def _create_application(client: TestClient, name: str = "Env App", **extra) -> dict:
    payload = {
        "name": name,
        "url": "https://prod.example.com",
        "environment": "production",
        "discovery_required": False,
        "auth_method": "standard_login",
        "username": "qa-account",
        "password": "prod-secret",
        **extra,
    }
    response = client.post("/applications", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _env_body(**overrides) -> dict:
    return {
        "name": "UAT",
        "url": "https://uat.example.com",
        "username": "uat-account",
        "password": "uat-secret",
        **overrides,
    }


def _add_env(client: TestClient, application: dict, **overrides) -> dict:
    response = client.post(f"/applications/{application['id']}/environments", json=_env_body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _row(application: dict, name: str) -> ApplicationEnvironment:
    with Session(engine) as session:
        return session.exec(
            select(ApplicationEnvironment)
            .join(Application, Application.id == ApplicationEnvironment.application_id)  # type: ignore[arg-type]
            .where(
                Application.external_id == uuid.UUID(application["id"]),
                ApplicationEnvironment.name == name,
            )
        ).one()


def _secret(ref: str) -> dict:
    return json.loads(VaultSecretsClient().resolve(SecretRef(path=ref)))


def _seed_run(application: dict, environment_id: uuid.UUID | None, status: str) -> None:
    with Session(engine) as session:
        application_row = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(application["id"]))
        ).one()
        session.add(
            TestRun(
                application_id=application_row.id,
                run_number=int(uuid.uuid4().int % 10_000_000),
                status=status,
                environment_snapshot="UAT",
                target_base_url_snapshot="https://uat.example.com/",
                environment_id=environment_id,
            )
        )
        session.commit()


def test_add_environment_lists_it_after_the_default_and_never_returns_the_password() -> None:
    admin, _ = _admin("Org Env Add")
    application = _create_application(admin)

    created = _add_env(admin, application, login_url="https://uat.example.com/signin")
    assert created["name"] == "UAT"
    assert created["is_default"] is False
    assert created["login_url"] == "https://uat.example.com/signin"

    listed = admin.get(f"/applications/{application['id']}/environments").json()
    assert [e["is_default"] for e in listed] == [True, False]
    assert listed[0]["name"] == "production"
    assert listed[0]["id"] is None
    assert listed[0]["username"] == "qa-account"
    assert listed[1]["username"] == "uat-account"
    assert "uat-secret" not in json.dumps(listed)

    # The URL is normalized like the default's, and the credentials sit in Vault.
    row = _row(application, "UAT")
    assert row.url == "https://uat.example.com"
    assert _secret(row.secret_ref) == {"username": "uat-account", "password": "uat-secret"}


@pytest.mark.parametrize("missing", ["username", "password", "name"])
def test_a_standard_login_default_requires_the_same_details(missing: str) -> None:
    admin, _ = _admin(f"Org Env Required {missing}")
    application = _create_application(admin)
    body = _env_body()
    body.pop(missing)
    response = admin.post(f"/applications/{application['id']}/environments", json=body)
    assert response.status_code == 422
    assert admin.get(f"/applications/{application['id']}/environments").json()[1:] == []


def test_login_url_is_required_exactly_when_the_default_has_one() -> None:
    admin, _ = _admin("Org Env Login URL")
    with_login_url = _create_application(admin, "With login URL", login_url="https://prod.example.com/signin")
    without = _create_application(admin, "Without login URL")

    assert (
        admin.post(f"/applications/{with_login_url['id']}/environments", json=_env_body()).status_code
        == 422
    )
    _add_env(admin, with_login_url, login_url="https://uat.example.com/signin")
    _add_env(admin, without)  # no login URL on either side


def test_a_no_sign_in_default_takes_no_credentials() -> None:
    admin, _ = _admin("Org Env No Login")
    application = _create_application(admin, auth_method="none", username=None, password=None)

    created = _add_env(admin, application, username=None, password=None)
    assert created["auth_method"] == "none"
    row = _row(application, "UAT")
    assert _secret(row.secret_ref) == {"cookies": [], "origins": []}
    assert row.requires_login is False


def test_names_are_unique_per_application_ignoring_case_and_never_the_defaults() -> None:
    admin, _ = _admin("Org Env Names")
    application = _create_application(admin)
    other = _create_application(admin, "Other App")
    _add_env(admin, application)

    for name in ("uat", " UAT ", "Production"):
        response = admin.post(
            f"/applications/{application['id']}/environments", json=_env_body(name=name)
        )
        assert response.status_code == 409, name
        assert response.json()["detail"] == "ENVIRONMENT_NAME_TAKEN"
    # Another application may reuse the name.
    _add_env(admin, other)


def test_an_unreachable_url_or_unapproved_domain_saves_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    admin, _ = _admin("Org Env Validation")
    application = _create_application(admin)

    async def _down(client: object, url: str) -> None:
        raise HTTPException(status_code=422, detail="Base URL did not respond")

    monkeypatch.setattr("api.main._check_reachable", _down)
    response = admin.post(f"/applications/{application['id']}/environments", json=_env_body())
    assert response.status_code == 422

    def _blocked(*args: object) -> None:
        raise HTTPException(status_code=422, detail="DOMAIN_NOT_APPROVED")

    monkeypatch.setattr("api.environments.require_approved_domain", _blocked)
    response = admin.post(f"/applications/{application['id']}/environments", json=_env_body())
    assert response.json()["detail"] == "DOMAIN_NOT_APPROVED"
    assert admin.get(f"/applications/{application['id']}/environments").json()[1:] == []


def test_edit_changes_every_field_and_a_blank_password_keeps_the_current_one() -> None:
    admin, _ = _admin("Org Env Edit")
    application = _create_application(admin)
    _add_env(admin, application)
    environment_id = _row(application, "UAT").external_id

    response = admin.patch(
        f"/applications/{application['id']}/environments/{environment_id}",
        json={
            "name": "UAT-2",
            "url": "https://uat2.example.com",
            "login_url": "https://uat2.example.com/signin",
            "username": "new-user",
            "password": "",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "UAT-2"
    row = _row(application, "UAT-2")
    assert (row.url, row.login_url) == ("https://uat2.example.com", "https://uat2.example.com/signin")
    assert _secret(row.secret_ref) == {"username": "new-user", "password": "uat-secret"}

    rotated = admin.patch(
        f"/applications/{application['id']}/environments/{environment_id}",
        json={"password": "rotated"},
    )
    assert rotated.status_code == 200
    assert _secret(row.secret_ref)["password"] == "rotated"


def test_edit_cannot_blank_a_required_field_or_take_an_existing_name() -> None:
    admin, _ = _admin("Org Env Edit Rules")
    application = _create_application(admin, login_url="https://prod.example.com/signin")
    _add_env(admin, application, login_url="https://uat.example.com/signin")
    _add_env(admin, application, name="QA", login_url="https://qa.example.com/signin")
    uat_id = _row(application, "UAT").external_id
    url = f"/applications/{application['id']}/environments/{uat_id}"

    assert admin.patch(url, json={"login_url": ""}).status_code == 422
    assert admin.patch(url, json={"username": ""}).status_code == 422
    assert admin.patch(url, json={"name": "qa"}).status_code == 409


def test_an_environment_with_a_run_in_progress_cannot_be_edited() -> None:
    admin, _ = _admin("Org Env Edit Running")
    application = _create_application(admin)
    _add_env(admin, application)
    row = _row(application, "UAT")
    _seed_run(application, row.id, "running")

    response = admin.patch(
        f"/applications/{application['id']}/environments/{row.external_id}", json={"name": "Renamed"}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "ENVIRONMENT_RUNNING"


def test_delete_removes_an_unused_environment_and_its_secret() -> None:
    admin, _ = _admin("Org Env Delete")
    application = _create_application(admin)
    _add_env(admin, application)
    row = _row(application, "UAT")

    response = admin.delete(f"/applications/{application['id']}/environments/{row.external_id}")
    assert response.status_code == 204
    assert admin.get(f"/applications/{application['id']}/environments").json()[1:] == []
    with pytest.raises(Exception):  # noqa: B017 — Vault raises its own InvalidPath
        _secret(row.secret_ref)


def test_delete_is_refused_while_any_run_uses_the_environment() -> None:
    admin, _ = _admin("Org Env Delete Runs")
    application = _create_application(admin)
    _add_env(admin, application)
    row = _row(application, "UAT")
    _seed_run(application, row.id, "completed")

    response = admin.delete(f"/applications/{application['id']}/environments/{row.external_id}")
    assert response.status_code == 409
    assert response.json()["detail"] == "ENVIRONMENT_IN_USE"
    assert len(admin.get(f"/applications/{application['id']}/environments").json()) == 2


def test_delete_is_refused_for_a_live_schedule_but_not_a_soft_deleted_one() -> None:
    admin, _ = _admin("Org Env Delete Schedules")
    application = _create_application(admin)
    _add_env(admin, application)
    row = _row(application, "UAT")
    schedule = admin.post(
        f"/applications/{application['id']}/schedules",
        json={
            "name": "UAT nightly",
            "cadence_type": "daily",
            "hour": 3,
            "minute": 0,
            "environment_id": str(row.external_id),
        },
    )
    assert schedule.status_code == 201, schedule.text
    assert schedule.json()["environment_name"] == "UAT"
    assert (
        admin.delete(f"/applications/{application['id']}/environments/{row.external_id}").status_code
        == 409
    )

    assert admin.delete(f"/schedules/{schedule.json()['id']}").status_code == 204
    assert (
        admin.delete(f"/applications/{application['id']}/environments/{row.external_id}").status_code
        == 204
    )
    with Session(engine) as session:
        deleted = session.exec(
            select(Schedule).where(Schedule.external_id == uuid.UUID(schedule.json()["id"]))
        ).one()
        assert deleted.environment_id is None


def test_a_schedule_can_move_between_an_environment_and_the_default() -> None:
    admin, _ = _admin("Org Env Schedule Move")
    application = _create_application(admin)
    _add_env(admin, application)
    env_id = str(_row(application, "UAT").external_id)
    created = admin.post(
        f"/applications/{application['id']}/schedules",
        json={"name": "Move me", "cadence_type": "daily", "hour": 4, "minute": 0},
    ).json()
    assert created["environment_id"] is None
    assert created["environment_name"] == "production"

    moved = admin.patch(f"/schedules/{created['id']}", json={"environment_id": env_id})
    assert moved.status_code == 200, moved.text
    assert (moved.json()["environment_id"], moved.json()["environment_name"]) == (env_id, "UAT")

    back = admin.patch(f"/schedules/{created['id']}", json={"environment_id": None})
    assert (back.json()["environment_id"], back.json()["environment_name"]) == (None, "production")
    # A PATCH that doesn't mention it leaves it alone.
    admin.patch(f"/schedules/{created['id']}", json={"environment_id": env_id})
    assert admin.patch(f"/schedules/{created['id']}", json={"name": "Renamed"}).json()[
        "environment_name"
    ] == "UAT"


def test_a_schedule_rejects_an_environment_of_another_application() -> None:
    admin, _ = _admin("Org Env Schedule Foreign")
    first = _create_application(admin, "First")
    second = _create_application(admin, "Second")
    _add_env(admin, first)
    foreign = str(_row(first, "UAT").external_id)

    response = admin.post(
        f"/applications/{second['id']}/schedules",
        json={"name": "Nope", "cadence_type": "daily", "hour": 1, "minute": 0, "environment_id": foreign},
    )
    assert response.status_code == 404


def test_members_can_manage_environments_and_viewers_can_only_read() -> None:
    admin, organization_id = _admin("Org Env Roles")
    application = _create_application(admin)
    member = _user_in_org(organization_id, "member")
    viewer = _user_in_org(organization_id, "viewer")

    created = _add_env(member, application)
    env_url = f"/applications/{application['id']}/environments/{created['id']}"
    assert member.patch(env_url, json={"name": "UAT-M"}).status_code == 200

    assert viewer.post(
        f"/applications/{application['id']}/environments", json=_env_body(name="Nope")
    ).status_code == 403
    assert viewer.patch(env_url, json={"name": "Nope"}).status_code == 403
    assert viewer.delete(env_url).status_code == 403

    seen = viewer.get(f"/applications/{application['id']}/environments").json()
    assert [e["name"] for e in seen] == ["production", "UAT-M"]
    assert all(e["username"] is None for e in seen)  # credentials stay hidden from viewers

    assert member.delete(env_url).status_code == 204


def test_members_can_edit_the_default_credentials_but_viewers_cannot() -> None:
    admin, organization_id = _admin("Org Env Default Creds")
    application = _create_application(admin)
    member = _user_in_org(organization_id, "member")
    viewer = _user_in_org(organization_id, "viewer")
    url = f"/applications/{application['id']}/credentials"

    assert member.patch(url, json={"username": "m", "password": "p"}).status_code == 200
    assert viewer.patch(url, json={"username": "v", "password": "p"}).status_code == 403


def test_reveal_returns_the_password_to_members_and_not_to_viewers() -> None:
    admin, organization_id = _admin("Org Env Reveal")
    application = _create_application(admin)
    _add_env(admin, application)
    env_id = _row(application, "UAT").external_id
    member = _user_in_org(organization_id, "member")
    viewer = _user_in_org(organization_id, "viewer")

    default_url = f"/applications/{application['id']}/credentials/reveal"
    env_url = f"/applications/{application['id']}/environments/{env_id}/reveal"
    assert member.post(default_url).json() == {"password": "prod-secret"}
    assert member.post(env_url).json() == {"password": "uat-secret"}
    assert viewer.post(default_url).status_code == 403
    assert viewer.post(env_url).status_code == 403


def test_environments_are_scoped_to_their_application_and_organization() -> None:
    admin, _ = _admin("Org Env Scope A")
    other_admin, _ = _admin("Org Env Scope B")
    first = _create_application(admin, "First")
    second = _create_application(admin, "Second")
    _add_env(admin, first)
    env_id = _row(first, "UAT").external_id

    # Right environment id, wrong application.
    assert admin.patch(
        f"/applications/{second['id']}/environments/{env_id}", json={"name": "X"}
    ).status_code == 404
    assert admin.delete(f"/applications/{second['id']}/environments/{env_id}").status_code == 404
    assert admin.post(f"/applications/{second['id']}/environments/{env_id}/reveal").status_code == 404
    # Another organization sees nothing.
    assert other_admin.get(f"/applications/{first['id']}/environments").status_code == 404
    assert other_admin.delete(f"/applications/{first['id']}/environments/{env_id}").status_code == 404


def test_triggering_a_run_rejects_an_unknown_environment() -> None:
    admin, _ = _admin("Org Env Trigger")
    application = _create_application(admin)

    response = admin.post(
        f"/applications/{application['id']}/test-runs", json={"environment_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


CART_SPEC = "await page.goto('https://prod.example.com/cart');"


def _add_suite(application: dict, code: str) -> None:
    """One current journey -> suite -> test asset, so the download has something."""
    with Session(engine) as session:
        application_row = session.exec(
            select(Application).where(Application.external_id == uuid.UUID(application["id"]))
        ).one()
        discovery_run = DiscoveryRun(application_id=application_row.id, status="complete")
        session.add(discovery_run)
        session.flush()
        journey = Journey(
            application_id=application_row.id,
            discovery_run_id=discovery_run.id,
            name="Checkout",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="Guest checkout",
            steps=["Add item to cart"],
            expected_result="Order confirmed",
            test_data=[],
            generation_run_id=journey.attempt,
        )
        session.add(scenario)
        session.flush()
        suite = TestSuite(
            journey_id=journey.id, name="Checkout Test Suite", generation_run_id=journey.attempt
        )
        session.add(suite)
        session.flush()
        session.add(TestAsset(scenario_id=scenario.id, test_suite_id=suite.id, code=code))
        session.commit()


def _zip_files(content: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return {name: zf.read(name).decode("utf-8") for name in zf.namelist()}


def test_download_for_an_environment_targets_it_and_never_contains_credentials() -> None:
    admin, _ = _admin("Org Env Download")
    application = _create_application(admin)
    _add_env(admin, application)
    env_id = _row(application, "UAT").external_id
    _add_suite(application, CART_SPEC)

    response = admin.get(
        f"/applications/{application['id']}/test-suites/download", params={"environment_id": str(env_id)}
    )

    assert response.status_code == 200
    assert 'filename="Env App-uat.zip"' in response.headers["content-disposition"]
    files = _zip_files(response.content)
    assert "https://uat.example.com" in files["playwright.config.ts"]
    assert "prod.example.com" not in files["playwright.config.ts"]
    spec = next(content for name, content in files.items() if name.endswith(".spec.ts"))
    assert "https://uat.example.com/cart" in spec
    assert "**UAT** environment" in files["README.md"]
    everything = " ".join(files.values())
    assert "uat-secret" not in everything and "prod-secret" not in everything


def test_download_without_an_environment_is_the_default_project() -> None:
    admin, _ = _admin("Org Env Download Default")
    application = _create_application(admin)
    _add_env(admin, application)
    _add_suite(application, CART_SPEC)

    response = admin.get(f"/applications/{application['id']}/test-suites/download")

    assert 'filename="Env App.zip"' in response.headers["content-disposition"]
    files = _zip_files(response.content)
    assert "https://prod.example.com" in files["playwright.config.ts"]
    assert "Environment" not in files["README.md"]
    spec = next(content for name, content in files.items() if name.endswith(".spec.ts"))
    assert "https://prod.example.com/cart" in spec


def test_download_rejects_an_unknown_or_foreign_environment() -> None:
    admin, _ = _admin("Org Env Download Foreign")
    first = _create_application(admin, "First")
    second = _create_application(admin, "Second")
    _add_env(admin, first)
    _add_suite(second, CART_SPEC)
    foreign = _row(first, "UAT").external_id

    for environment_id in (uuid.uuid4(), foreign):
        response = admin.get(
            f"/applications/{second['id']}/test-suites/download",
            params={"environment_id": str(environment_id)},
        )
        assert response.status_code == 404
