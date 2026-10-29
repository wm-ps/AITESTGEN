"""Shared fixtures for apps/api/tests.

Every test that POSTs to `/applications` starts a *real* Temporal workflow
against the shared dev server (see `api.discovery.start_discovery_run`) —
there's no worker consuming it during a test run, so it sits `Running`
forever and piles up (this is what caused shopbit's discovery run to starve
behind ~40 leaked workflows). Terminate whatever each test starts, right
after the test, regardless of which file or future test triggers it.
"""

import asyncio

import pytest
from api import discovery as api_discovery
from api import main as api_main
from api.temporal_client import get_temporal_client


class _AlwaysReachableResponse:
    status_code = 200


class _AlwaysReachableAsyncClient:
    """Stubs `httpx.AsyncClient` (FR-31, Story 1.3's rework) as always
    reachable — every test in this package that POSTs to `/applications`
    uses a synthetic `*.example.com` URL that was never meant to really be
    reached. Only `test_onboarding.py`'s own reachability tests need to
    control this behavior directly; they define a more detailed fake client
    and their own same-named fixture, which simply overrides this one for
    that module (standard pytest fixture shadowing)."""

    async def __aenter__(self) -> _AlwaysReachableAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def head(self, url: str) -> _AlwaysReachableResponse:
        return _AlwaysReachableResponse()

    async def get(self, url: str) -> _AlwaysReachableResponse:
        return _AlwaysReachableResponse()


@pytest.fixture(autouse=True)
def _reachable_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.main.httpx.AsyncClient", lambda **kwargs: _AlwaysReachableAsyncClient()
    )


@pytest.fixture(autouse=True)
def _domains_approved_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests onboard synthetic URLs under orgs with an empty domain whitelist;
    only `test_approved_domains.py` exercises the real check (it defines its
    own same-named fixture, which shadows this one)."""
    monkeypatch.setattr(api_main, "require_approved_domain", lambda session, organization_id, url: None)


async def _always_has_pollers(client: object, task_queue: str) -> bool:
    return True


@pytest.fixture(autouse=True)
def _workers_always_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """This suite runs no real discovery/generation/execution worker (see
    the module docstring — nothing consumes the queues these tests start
    workflows on), so the real `has_pollers` would report every queue as
    worker-down and turn every trigger test into a false *_UNAVAILABLE
    failure. A test that wants to exercise the worker-down path itself
    overrides this with its own `monkeypatch.setattr(..., "has_pollers", ...)`
    after this fixture runs."""
    monkeypatch.setattr(api_discovery, "has_pollers", _always_has_pollers)
    monkeypatch.setattr(api_main, "has_pollers", _always_has_pollers)


@pytest.fixture(autouse=True)
def _terminate_discovery_workflows_started_by_test(monkeypatch: pytest.MonkeyPatch) -> None:
    started_external_ids: list[str] = []
    # `api.main.create_application` and `api.discovery.resume_discovery_run`
    # (Story 2.17) each hold their own module-level reference to the real
    # `start_discovery_run` (a plain `from ... import` copies the reference
    # at import time, it isn't a live alias) — both must be patched, or
    # workflows started via the resume-discovery endpoint leak untracked.
    original_start_discovery_run = api_discovery.start_discovery_run

    async def _tracked_start_discovery_run(session, application, **kwargs):
        discovery_run = await original_start_discovery_run(session, application, **kwargs)
        started_external_ids.append(str(discovery_run.external_id))
        return discovery_run

    monkeypatch.setattr(api_main, "start_discovery_run", _tracked_start_discovery_run)
    monkeypatch.setattr(api_discovery, "start_discovery_run", _tracked_start_discovery_run)
    yield
    if not started_external_ids:
        return

    async def _terminate_all() -> None:
        client = await get_temporal_client()
        for external_id in started_external_ids:
            try:
                await client.get_workflow_handle(f"discovery-{external_id}").terminate(
                    reason="pytest cleanup: dev Temporal server is shared, leaked workflows pile up"
                )
            except Exception:
                pass

    asyncio.run(_terminate_all())


@pytest.fixture(autouse=True)
def _terminate_explorer_workflows_started_by_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explorer is the default discovery (`EXPLORER_REPLACES_DISCOVERY`), so
    creating an application in a test starts a real Explorer run. A locally
    running Explorer worker would pick it up and try to sign in to the test's
    fake URL — so test runs go to a task queue no worker polls, and every
    Explorer run a test created (onboarding, Start, Resume all use the run's
    one workflow id) is ended right after it."""
    from datetime import UTC, datetime

    from api import explorer as api_explorer

    monkeypatch.setattr(api_explorer, "EXPLORER_TASK_QUEUE", "pytest-explorer-task-queue")
    monkeypatch.setattr(api_explorer, "has_pollers", _always_has_pollers)

    from api.db import engine
    from explorer_core import ACTIVE_RUN_STATUSES, ExplorerRun, explorer_workflow_id
    from sqlmodel import Session, col, select

    started = datetime.now(UTC)
    yield

    async def _terminate_all() -> None:
        with Session(engine) as session:
            runs = session.exec(
                select(ExplorerRun).where(col(ExplorerRun.created_at) >= started)
            ).all()
            ids = [run.external_id for run in runs]
            for run in runs:  # nothing will ever finish them: don't leave them "running"
                if run.status in ACTIVE_RUN_STATUSES:
                    run.status, run.headline = "stopped", "Stopped (pytest cleanup)"
                    session.add(run)
            session.commit()
        if not ids:
            return
        client = await get_temporal_client()
        for external_id in ids:
            try:
                await client.get_workflow_handle(explorer_workflow_id(external_id)).terminate(
                    reason="pytest cleanup: a test's Explorer run must not reach a real worker"
                )
            except Exception:
                pass

    asyncio.run(_terminate_all())
