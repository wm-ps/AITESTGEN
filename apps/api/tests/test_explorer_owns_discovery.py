"""Start discovery runs Explorer (api.discovery.start_discovery_run); the
classic crawler's Pause/Resume Discovery must never run against an app
Explorer discovers — resuming would start the crawler instead."""

import uuid
from types import SimpleNamespace

import pytest
from api import discovery
from api.main import _require_crawler_discovery
from fastapi import HTTPException


class _Session:
    def __init__(self, explorer_run: object | None) -> None:
        self.found = explorer_run

    def exec(self, _query: object) -> SimpleNamespace:
        return SimpleNamespace(first=lambda: self.found)


APP = SimpleNamespace(id=uuid.uuid4())


def test_start_discovery_runs_explorer_by_default() -> None:
    assert discovery.EXPLORER_REPLACES_DISCOVERY


def test_pause_and_resume_discovery_refuse_an_explorer_app() -> None:
    with pytest.raises(HTTPException) as refused:
        _require_crawler_discovery(_Session(uuid.uuid4()), APP)  # type: ignore[arg-type]
    assert refused.value.status_code == 409
    assert "Explorer tab" in refused.value.detail


def test_an_app_the_crawler_discovered_keeps_its_pause_and_resume() -> None:
    _require_crawler_discovery(_Session(None), APP)  # type: ignore[arg-type]
