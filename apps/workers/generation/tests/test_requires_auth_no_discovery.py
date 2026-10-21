"""`resolve_requires_auth` for `discovery_required=false` + `standard_login`
(no captured login page). No DB needed — the login-page lookup is stubbed."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from generation_worker import spec_linter


def _app(**overrides):
    base = {"id": "app-id", "discovery_required": False, "auth_method": "standard_login"}
    return SimpleNamespace(**{**base, **overrides})


@pytest.fixture(autouse=True)
def _no_login_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spec_linter, "_find_login_page_url", lambda s, a: None)


@pytest.mark.parametrize(
    "name",
    ["Locate the target application", "Open the application in WaveMaker Studio", "Preview the application"],
)
def test_post_login_case_requires_auth(name: str) -> None:
    scenario = SimpleNamespace(name=name)
    assert spec_linter.resolve_requires_auth(None, _app(), None, scenario) is True  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["Successful login to the Apps page", "Login with invalid password", "Sign in"])
def test_login_case_stays_public(name: str) -> None:
    scenario = SimpleNamespace(name=name)
    assert spec_linter.resolve_requires_auth(None, _app(), None, scenario) is False  # type: ignore[arg-type]


def test_discovery_required_true_is_unchanged() -> None:
    scenario = SimpleNamespace(name="Locate the target application")
    assert (
        spec_linter.resolve_requires_auth(None, _app(discovery_required=True), None, scenario)  # type: ignore[arg-type]
        is False
    )
