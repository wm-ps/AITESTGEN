"""`find_login_page_evidence`'s synthetic fallback for an Application created
with `discovery_required=false` (no Discovery, so no captured login form).
No DB needed — the captured-evidence lookup is stubbed out."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_suite_assembler import assembler
from test_suite_assembler.assembler import LoginPageEvidence, find_login_page_evidence


def _app(**overrides):
    base = {
        "discovery_required": False,
        "auth_method": "standard_login",
        "url": "https://app.example/",
        "login_url": None,
    }
    return SimpleNamespace(**{**base, **overrides})


@pytest.fixture(autouse=True)
def _no_captured_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assembler, "_find_captured_login_page_evidence", lambda s, a: None)


def test_fallback_uses_application_url_when_no_login_url() -> None:
    evidence = find_login_page_evidence(None, _app())  # type: ignore[arg-type]
    assert evidence is not None
    assert evidence.url == "https://app.example/"
    assert evidence.username_locator is None


def test_fallback_prefers_login_url() -> None:
    evidence = find_login_page_evidence(None, _app(login_url="https://app.example/login"))  # type: ignore[arg-type]
    assert evidence is not None and evidence.url == "https://app.example/login"


def test_fallback_setup_script_uses_the_slow_app_goto_budget() -> None:
    evidence = find_login_page_evidence(None, _app())  # type: ignore[arg-type]
    script = assembler._build_auth_setup_script("standard_login", evidence)
    assert ".goto(loginUrl, { timeout: 30000, waitUntil: 'domcontentloaded' })" in script


def test_captured_evidence_setup_script_goto_is_unchanged() -> None:
    evidence = LoginPageEvidence(url="https://x/login", username_locator=None, password_locator="p")
    script = assembler._build_auth_setup_script("standard_login", evidence)
    assert ".goto(loginUrl, { timeout: 10000 })" in script
    assert assembler._build_auth_setup_script("standard_login", None).count("{ timeout: 10000 }") == 1


def test_discovery_required_true_is_unchanged() -> None:
    assert find_login_page_evidence(None, _app(discovery_required=True)) is None  # type: ignore[arg-type]


def test_non_standard_login_is_unchanged() -> None:
    assert find_login_page_evidence(None, _app(auth_method="sso_session_reuse")) is None  # type: ignore[arg-type]


def test_captured_evidence_for_no_discovery_app_gets_the_slow_app_goto_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = LoginPageEvidence(url="https://x/login", username_locator="u", password_locator="p")
    monkeypatch.setattr(assembler, "_find_captured_login_page_evidence", lambda s, a: captured)
    evidence = find_login_page_evidence(None, _app())  # type: ignore[arg-type]
    assert evidence is not None
    assert (evidence.url, evidence.username_locator, evidence.password_locator) == (
        "https://x/login",
        "u",
        "p",
    )
    assert (evidence.goto_timeout_ms, evidence.goto_wait_until) == (30000, "domcontentloaded")


def test_captured_evidence_for_discovery_app_is_returned_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = LoginPageEvidence(url="https://x/login", username_locator="u", password_locator="p")
    monkeypatch.setattr(assembler, "_find_captured_login_page_evidence", lambda s, a: captured)
    assert find_login_page_evidence(None, _app(discovery_required=True)) is captured  # type: ignore[arg-type]


def test_no_discovery_login_gets_a_longer_setup_project_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(assembler, "_find_captured_login_page_evidence", lambda s, a: None)
    evidence = find_login_page_evidence(None, _app())  # type: ignore[arg-type]
    assert evidence is not None and evidence.setup_timeout_ms == 120000
    config = assembler._build_playwright_config(
        "https://x/", has_login=True, setup_timeout_ms=evidence.setup_timeout_ms
    )
    assert "timeout: 120000," in config


def test_default_setup_project_timeout_is_unchanged() -> None:
    assert "timeout: 60000," in assembler._build_playwright_config("https://x/", has_login=True)
    assert LoginPageEvidence(url="u", username_locator=None, password_locator="p").setup_timeout_ms == 60000
