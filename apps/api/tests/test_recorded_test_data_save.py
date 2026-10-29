"""Edit Test Data for a recorded test — saved inline by the API as a direct
literal swap (`domain.recorded_test_data.apply_recorded_test_data`): no AI,
no Temporal, so it works with no generation worker running. Each test
makes Temporal unreachable once its fixtures exist, to prove it.
"""

import uuid

import hvac
import pytest
from api import main as api_main
from api.db import engine, init_db
from api.main import app
from api.scripts.seed_dev_data import seed
from domain import Application, DiscoveryRun, Journey, Scenario, TestAsset, TestSuite
from fastapi.testclient import TestClient
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN
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


def _vault_available() -> bool:
    try:
        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except VaultError, OSError:
        return False


pytestmark = pytest.mark.skipif(
    not (_db_available() and _vault_available()),
    reason="requires PostgreSQL + Vault reachable — start docker compose",
)

_RECORDED_CODE = (
    "import { test, expect } from '@playwright/test';\n\n"
    "test('transfer', { tag: '@auth' }, async ({ page }) => {\n"
    "  await page.goto('/');\n"
    "  await page.getByRole('textbox', { name: 'User Name' }).fill('someone');\n"
    "  await page.getByRole('textbox', { name: 'Password' }).fill('s3cret-pw');\n"
    "  await page.getByRole('spinbutton', { name: 'Amount (USD)' }).fill('25');\n"
    "  await page.getByRole('button', { name: 'Transfer' }).click();\n"
    "});\n"
)
_RECORDED_STEPS = [
    "Navigate to /",
    "Fill in 'someone' into 'User Name'",
    "Fill in 's3cret-pw' into 'Password'",
    "Fill in '25' into 'Amount (USD)'",
    "Click 'Transfer'",
]
_RECORDED_FIELDS = [
    {"name": "User Name", "mandatory": True, "value": "someone"},
    {"name": "Amount (USD)", "mandatory": True, "value": "25"},
]


def _block_temporal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Applied after setup — creating the test Application itself seeds
    Temporal schedules."""

    async def _unreachable() -> None:
        raise AssertionError("a recorded save must never touch Temporal")

    monkeypatch.setattr(api_main, "get_temporal_client", _unreachable)


def _signed_in_client() -> TestClient:
    init_db()
    email = f"user-{uuid.uuid4()}@example.com"
    seed(email=email, password="pw", org_name="Org Recorded Test Data", name="Tester")
    client = TestClient(app)
    client.post("/auth/login", json={"email": email, "password": "pw"})
    return client


def _recorded_test(
    client: TestClient, *, fields: list[dict] | None = None
) -> tuple[str, TestAsset]:
    response = client.post(
        "/applications",
        json={
            "name": "Recorded Save App",
            "url": "https://staging.example.com",
            "environment": "staging",
            "username": "qa-test-account",
            "password": "irrelevant",
        },
    )
    assert response.status_code == 201
    application = response.json()
    with Session(engine) as session:
        discovery_run = session.exec(
            select(DiscoveryRun).where(
                DiscoveryRun.external_id == uuid.UUID(application["discovery_run_id"])
            )
        ).one()
        journey = Journey(
            application_id=discovery_run.application_id,
            discovery_run_id=discovery_run.id,
            name="Recorded tests",
            identity_key=f"identity-{uuid.uuid4()}",
        )
        session.add(journey)
        session.flush()
        scenario = Scenario(
            journey_id=journey.id,
            type="happy",
            name="transfer",
            steps=list(_RECORDED_STEPS),
            test_data=fields if fields is not None else [dict(f) for f in _RECORDED_FIELDS],
            generation_run_id=journey.attempt,
            source="recorded",
        )
        session.add(scenario)
        session.flush()
        suite = TestSuite(
            journey_id=journey.id,
            name="Recorded tests Test Suite",
            generation_run_id=journey.attempt,
            current=True,
        )
        session.add(suite)
        session.flush()
        asset = TestAsset(
            scenario_id=scenario.id,
            test_suite_id=suite.id,
            code=_RECORDED_CODE,
            current=True,
            requires_auth=True,
            status="ready",
        )
        session.add(asset)
        session.commit()
        session.refresh(scenario)
        session.refresh(asset)
        return str(scenario.external_id), asset


def _recorded_test_with_login(client: TestClient) -> tuple[str, TestAsset, str]:
    """The same recording with its username marked as a login field;
    returns the Application's external id too."""
    fields = [{**_RECORDED_FIELDS[0], "login": True}, dict(_RECORDED_FIELDS[1])]
    scenario_id, asset = _recorded_test(client, fields=fields)
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_id))
        ).one()
        journey = session.get(Journey, scenario.journey_id)
        assert journey is not None
        application = session.get(Application, journey.application_id)
        assert application is not None
        return scenario_id, asset, str(application.external_id)


def _assets(prior: TestAsset) -> list[TestAsset]:
    with Session(engine) as session:
        return list(
            session.exec(
                select(TestAsset)
                .where(TestAsset.scenario_id == prior.scenario_id)
                .order_by(TestAsset.created_at)  # type: ignore[arg-type]
            ).all()
        )


def _save(client: TestClient, scenario_id: str, name: str, value: str):
    patched = client.patch(
        f"/scenarios/{scenario_id}/test-data", json={"name": name, "value": value}
    )
    assert patched.status_code == 200, patched.text
    return client.post(f"/scenarios/{scenario_id}/test-data/regenerate")


def test_recorded_save_swaps_the_value_with_no_generation_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in_client()
    scenario_id, prior = _recorded_test(client)
    _block_temporal(monkeypatch)

    response = _save(client, scenario_id, "Amount (USD)", "500")
    assert response.status_code == 202, response.text
    assert response.json() == {"started": True}

    [old, new] = _assets(prior)
    assert old.current is False and new.current is True
    assert new.code == _RECORDED_CODE.replace("fill('25')", "fill('500')")
    # The recording's own auth tag and status stay — never recomputed.
    assert new.requires_auth is True and "{ tag: '@auth' }" in new.code
    assert new.status == "ready"

    status = client.get(f"/scenarios/{scenario_id}/test-data/regenerate")
    assert status.status_code == 200
    assert status.json() == {
        "status": "complete",
        "test_asset_id": str(new.external_id),
        "error_message": None,
    }
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_id))
        ).one()
        assert scenario.steps[3] == "Fill in '500' into 'Amount (USD)'"


def test_recorded_username_save_never_touches_the_password(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _signed_in_client()
    scenario_id, prior = _recorded_test(client)
    _block_temporal(monkeypatch)

    assert _save(client, scenario_id, "User Name", "other-user").status_code == 202

    new = _assets(prior)[-1]
    assert new.code == _RECORDED_CODE.replace("fill('someone')", "fill('other-user')")
    assert "fill('s3cret-pw')" in new.code


def test_recorded_save_with_no_change_creates_no_new_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in_client()
    scenario_id, prior = _recorded_test(client)
    _block_temporal(monkeypatch)

    response = client.post(f"/scenarios/{scenario_id}/test-data/regenerate")

    assert response.status_code == 202
    assert [a.id for a in _assets(prior)] == [prior.id]


def test_recorded_fields_out_of_step_with_code_are_refused_with_nothing_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in_client()
    scenario_id, prior = _recorded_test(
        client, fields=[*_RECORDED_FIELDS, {"name": "Memo", "mandatory": True, "value": "rent"}]
    )
    _block_temporal(monkeypatch)

    response = client.post(f"/scenarios/{scenario_id}/test-data/regenerate")

    assert response.status_code == 409
    assert "changed since it was recorded" in response.json()["detail"]
    assert [(a.id, a.current, a.code) for a in _assets(prior)] == [(prior.id, True, _RECORDED_CODE)]


def test_login_field_is_hidden_from_the_scenario_read(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _signed_in_client()
    scenario_id, _, application_id = _recorded_test_with_login(client)

    listed = client.get(f"/applications/{application_id}/scenarios")
    assert listed.status_code == 200, listed.text
    [read] = [s for s in listed.json() if s["id"] == scenario_id]
    assert [f["name"] for f in read["test_data"]] == ["Amount (USD)"]
    assert read["has_login_fields"] is True
    assert read["test_data_complete"] is True


def test_login_field_cannot_be_edited(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _signed_in_client()
    scenario_id, prior, _ = _recorded_test_with_login(client)
    _block_temporal(monkeypatch)

    patched = client.patch(
        f"/scenarios/{scenario_id}/test-data", json={"name": "User Name", "value": "other-user"}
    )

    assert patched.status_code == 422
    with Session(engine) as session:
        scenario = session.exec(
            select(Scenario).where(Scenario.external_id == uuid.UUID(scenario_id))
        ).one()
        assert scenario.test_data[0]["value"] == "someone"
    assert [a.id for a in _assets(prior)] == [prior.id]


def test_marked_login_field_keeps_the_recorded_order_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _signed_in_client()
    scenario_id, prior, _ = _recorded_test_with_login(client)
    _block_temporal(monkeypatch)

    assert _save(client, scenario_id, "Amount (USD)", "500").status_code == 202

    new = _assets(prior)[-1]
    assert new.code == _RECORDED_CODE.replace("fill('25')", "fill('500')")
