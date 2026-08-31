"""`_rebuild_project_dir_sync` — the recovery path `_ensure_project_dir`
takes when a TestRun's assembled project directory was evicted from local
disk (worker restart, disk cleanup) and needs reassembling from scratch.
Used by both `ExecuteTestActivity` and `HealTestActivity`.

Must recreate `.auth/state.json` too when the app needs one — the same
condition `PrepareTestRunActivity`'s own initial assembly already uses.
Before this fix, a rebuild always skipped that step entirely (only
`_prepare_test_run_sync` ever called `_run_auth_setup_once`), so any
`@auth` test executed after such an eviction failed with a storage-state
ENOENT no matter how many heal/execute attempts remained — observed live
via a manual "Retry with self-heal" against a TestRun whose project cache
had been cleared.
"""

import uuid
from unittest.mock import MagicMock

import execution_worker.activities as activities_module
import pytest
from domain import Application, DiscoveryRun, Form, FormField, Organization, Page
from execution_worker.db import engine, init_db
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            from sqlalchemy import text

            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _seed_application_with_login_form() -> Application:
    """A standard_login app with a captured password field — the exact
    shape `find_login_page_evidence` treats as a real login form."""
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Rebuild Auth Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.flush()
        discovery_run = DiscoveryRun(application_id=application.id, status="complete")
        session.add(discovery_run)
        session.flush()
        page = Page(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            url="https://app.example.com/login",
            title="Login",
        )
        session.add(page)
        session.flush()
        form = Form(
            application_id=application.id,
            discovery_run_id=discovery_run.id,
            page_id=page.id,
            action_url="https://app.example.com/login",
            method="POST",
        )
        session.add(form)
        session.flush()
        session.add(FormField(form_id=form.id, name="password", input_type="password"))
        session.commit()
        session.refresh(application)
        return application


def _seed_application_without_login_form() -> Application:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        application = Application(
            organization_id=org.id,
            name="Rebuild No-Auth Test App",
            url="https://app.example.com",
            environment="staging",
            auth_method="standard_login",
            secret_ref="applications/irrelevant/secret",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application


@pytest.fixture(autouse=True)
def _mock_run_auth_setup_once(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(activities_module, "assemble_test_suite_project_to_dir", MagicMock())
    monkeypatch.setattr(activities_module, "_install_project", MagicMock())
    run_auth_setup_mock = MagicMock()
    monkeypatch.setattr(activities_module, "_run_auth_setup_once", run_auth_setup_mock)
    return run_auth_setup_mock


def test_rebuild_reruns_auth_setup_when_app_has_login_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path, _mock_run_auth_setup_once: MagicMock
) -> None:
    init_db()
    application = _seed_application_with_login_form()
    monkeypatch.setattr(activities_module, "project_dir_for", lambda test_run_id: tmp_path)

    activities_module._rebuild_project_dir_sync(uuid.uuid4(), application.external_id)

    _mock_run_auth_setup_once.assert_called_once()
    assert _mock_run_auth_setup_once.call_args.args[0] == tmp_path
    assert _mock_run_auth_setup_once.call_args.args[1].id == application.id


def test_rebuild_skips_auth_setup_when_app_has_no_login_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path, _mock_run_auth_setup_once: MagicMock
) -> None:
    init_db()
    application = _seed_application_without_login_form()
    monkeypatch.setattr(activities_module, "project_dir_for", lambda test_run_id: tmp_path)

    activities_module._rebuild_project_dir_sync(uuid.uuid4(), application.external_id)

    _mock_run_auth_setup_once.assert_not_called()


def test_rebuild_is_a_no_op_when_package_json_already_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path, _mock_run_auth_setup_once: MagicMock
) -> None:
    """Already-present project dir (the common case) must not re-run auth
    setup on every single call — only a genuine rebuild does."""
    init_db()
    application = _seed_application_with_login_form()
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(activities_module, "project_dir_for", lambda test_run_id: tmp_path)

    activities_module._rebuild_project_dir_sync(uuid.uuid4(), application.external_id)

    _mock_run_auth_setup_once.assert_not_called()
