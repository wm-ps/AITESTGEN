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
from api import main as api_main
from api.temporal_client import get_temporal_client


@pytest.fixture(autouse=True)
def _terminate_discovery_workflows_started_by_test(monkeypatch: pytest.MonkeyPatch) -> None:
    started_external_ids: list[str] = []
    original_start_discovery_run = api_main.start_discovery_run

    async def _tracked_start_discovery_run(session, application):
        discovery_run = await original_start_discovery_run(session, application)
        started_external_ids.append(str(discovery_run.external_id))
        return discovery_run

    monkeypatch.setattr(api_main, "start_discovery_run", _tracked_start_discovery_run)
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
