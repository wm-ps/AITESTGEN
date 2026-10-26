"""POST/GET /applications/verify-credentials — the "Start discovery" login
pre-check (start + poll, run by the discovery worker).

Temporal, Vault and auth are all faked: this verifies the route's own logic
(503 when no worker, temp-secret lifecycle, org-scoped workflow id, status
mapping) without needing PostgreSQL/Vault/Temporal running or a discovery
worker to process anything.
"""

import uuid
from types import SimpleNamespace

import pytest
from api import main
from api.auth import block_viewer_writes, current_org_id
from fastapi.testclient import TestClient
from temporalio.client import WorkflowExecutionStatus
from workflows import DISCOVERY_TASK_QUEUE, VerifyCredentialsResult

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()
PAYLOAD = {
    "url": "https://staging.example.com/app",
    "login_url": "https://staging.example.com/login",
    "username": "qa-account",
    "password": "qa-password",
}


class FakeVault:
    stored: list[tuple[uuid.UUID, bytes]] = []
    deleted: list[str] = []

    def store(self, organization_id, secret):
        FakeVault.stored.append((organization_id, secret))
        return SimpleNamespace(path=f"applications/{organization_id}/temp-1")

    def delete(self, ref):
        FakeVault.deleted.append(ref.path)


class FakeHandle:
    def __init__(self, status, result=None, missing=False):
        self._status = status
        self._result = result
        self._missing = missing

    async def describe(self):
        if self._missing:
            raise RuntimeError("workflow not found")
        return SimpleNamespace(status=self._status)

    async def result(self):
        return self._result


class FakeTemporal:
    def __init__(self, handle=None, start_error=None):
        self.handle = handle
        self.start_error = start_error
        self.started: list[dict] = []
        self.requested_ids: list[str] = []

    async def start_workflow(self, run, workflow_input, *, id, task_queue):
        if self.start_error:
            raise self.start_error
        self.started.append({"input": workflow_input, "id": id, "task_queue": task_queue})

    def get_workflow_handle_for(self, run, workflow_id):
        self.requested_ids.append(workflow_id)
        return self.handle


@pytest.fixture
def client(monkeypatch):
    FakeVault.stored, FakeVault.deleted = [], []
    monkeypatch.setattr(main, "VaultSecretsClient", FakeVault)
    main.app.dependency_overrides[current_org_id] = lambda: ORG_ID
    main.app.dependency_overrides[block_viewer_writes] = lambda: None
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def _use_temporal(monkeypatch, temporal, *, pollers=True):
    async def _get_client():
        return temporal

    async def _has_pollers(_client, _queue):
        return pollers

    monkeypatch.setattr(main, "get_temporal_client", _get_client)
    monkeypatch.setattr(main, "has_pollers", _has_pollers)


def test_start_stores_a_temporary_secret_and_starts_an_org_scoped_workflow(client, monkeypatch):
    temporal = FakeTemporal()
    _use_temporal(monkeypatch, temporal)

    response = client.post("/applications/verify-credentials", json=PAYLOAD)

    assert response.status_code == 202
    check_id = response.json()["check_id"]
    started = temporal.started[0]
    assert started["id"] == f"verify-credentials-{ORG_ID}-{check_id}"
    assert started["task_queue"] == DISCOVERY_TASK_QUEUE
    # Only the temp secret's path is workflow input — never the password.
    assert started["input"].secret_ref == f"applications/{ORG_ID}/temp-1"
    assert "qa-password" not in repr(started["input"])
    assert started["input"].login_url == "https://staging.example.com/login"
    assert b"qa-password" in FakeVault.stored[0][1]
    # On the happy path the worker activity deletes it, not the route.
    assert FakeVault.deleted == []


def test_start_returns_503_discovery_unavailable_when_no_worker_is_polling(client, monkeypatch):
    temporal = FakeTemporal()
    _use_temporal(monkeypatch, temporal, pollers=False)

    response = client.post("/applications/verify-credentials", json=PAYLOAD)

    assert response.status_code == 503
    assert response.json()["detail"] == "DISCOVERY_UNAVAILABLE"
    assert FakeVault.stored == []
    assert temporal.started == []


def test_start_deletes_the_temporary_secret_when_the_workflow_fails_to_start(monkeypatch):
    FakeVault.stored, FakeVault.deleted = [], []
    monkeypatch.setattr(main, "VaultSecretsClient", FakeVault)
    main.app.dependency_overrides[current_org_id] = lambda: ORG_ID
    main.app.dependency_overrides[block_viewer_writes] = lambda: None
    try:
        _use_temporal(monkeypatch, FakeTemporal(start_error=RuntimeError("temporal down")))
        # raise_server_exceptions=False: assert on the 500, not a re-raised error.
        response = TestClient(main.app, raise_server_exceptions=False).post(
            "/applications/verify-credentials", json=PAYLOAD
        )
    finally:
        main.app.dependency_overrides.clear()

    assert response.status_code == 500
    assert FakeVault.deleted == [f"applications/{ORG_ID}/temp-1"]


def test_blank_login_url_is_sent_as_none(client, monkeypatch):
    temporal = FakeTemporal()
    _use_temporal(monkeypatch, temporal)

    client.post("/applications/verify-credentials", json={**PAYLOAD, "login_url": ""})

    assert temporal.started[0]["input"].login_url is None


def test_status_is_running_while_the_workflow_is_running(client, monkeypatch):
    temporal = FakeTemporal(handle=FakeHandle(WorkflowExecutionStatus.RUNNING))
    _use_temporal(monkeypatch, temporal)
    check_id = uuid.uuid4()

    response = client.get(f"/applications/verify-credentials/{check_id}")

    assert response.json() == {"status": "running", "detail": None}
    # Rebuilt from the caller's own org — another org's id can never match.
    assert temporal.requested_ids == [f"verify-credentials-{ORG_ID}-{check_id}"]
    assert str(OTHER_ORG_ID) not in temporal.requested_ids[0]


@pytest.mark.parametrize("status", ["valid", "invalid", "uncertain"])
def test_status_returns_the_workflow_verdict_once_completed(client, monkeypatch, status):
    handle = FakeHandle(
        WorkflowExecutionStatus.COMPLETED,
        result=VerifyCredentialsResult(status=status, detail="why"),
    )
    _use_temporal(monkeypatch, FakeTemporal(handle=handle))

    response = client.get(f"/applications/verify-credentials/{uuid.uuid4()}")

    assert response.json() == {"status": status, "detail": "why"}


def test_status_is_uncertain_when_the_workflow_did_not_complete_normally(client, monkeypatch):
    _use_temporal(monkeypatch, FakeTemporal(handle=FakeHandle(WorkflowExecutionStatus.FAILED)))

    response = client.get(f"/applications/verify-credentials/{uuid.uuid4()}")

    assert response.json()["status"] == "uncertain"


def test_status_is_404_for_an_unknown_check(client, monkeypatch):
    _use_temporal(monkeypatch, FakeTemporal(handle=FakeHandle(None, missing=True)))

    response = client.get(f"/applications/verify-credentials/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "CREDENTIAL_CHECK_NOT_FOUND"
