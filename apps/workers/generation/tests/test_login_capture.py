"""Login-form capture for `discovery_required=false` apps (`login_capture` +
`bootstrap_storage_state`). No DB / browser / Vault — all collaborators stubbed."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from discovery_worker.crawler import CapturedForm, CapturedFormField, CapturedPage
from generation_worker import spec_linter
from generation_worker.live_exploration import auth_bootstrap, login_capture
from temporalio.exceptions import ApplicationError
from workflows.live_exploration_workflow import LOGIN_FAILED_ERROR_TYPE


def _app(**overrides):
    base = {
        "id": uuid.uuid4(),
        "discovery_required": False,
        "auth_method": "standard_login",
        "secret_ref": "ref",
        "url": "https://app.example/",
        "login_url": None,
    }
    return SimpleNamespace(**{**base, **overrides})


def _stub_login_page_url(monkeypatch: pytest.MonkeyPatch, url: str | None) -> None:
    monkeypatch.setattr(spec_linter, "_find_login_page_url", lambda s, a: url)


@pytest.mark.parametrize(
    ("overrides", "login_url", "expected"),
    [
        ({}, None, True),
        ({}, "https://app.example/login", False),
        ({"discovery_required": True}, None, False),
        ({"auth_method": "sso_session_reuse"}, None, False),
    ],
)
def test_needs_login_capture(
    monkeypatch: pytest.MonkeyPatch, overrides: dict, login_url: str | None, expected: bool
) -> None:
    _stub_login_page_url(monkeypatch, login_url)
    assert login_capture.needs_login_capture(_app(**overrides)) is expected  # type: ignore[arg-type]


def test_capture_kwargs_collect_into_the_given_list() -> None:
    captured: list = []
    kwargs = login_capture.login_capture_kwargs(captured)
    kwargs["on_capture"]("item")
    assert captured == ["item"]
    assert kwargs["object_store"].put(b"", kwargs["discovery_run_id"]) is None


class _FakeContext:
    async def storage_state(self) -> dict:
        return {"cookies": []}


class _FakeBrowser:
    async def close(self) -> None:
        pass


class _FakePlaywright:
    class chromium:  # noqa: N801 — mirrors the Playwright attribute name
        @staticmethod
        async def launch(headless: bool) -> _FakeBrowser:
            return _FakeBrowser()


class _FakePlaywrightManager:
    async def __aenter__(self) -> _FakePlaywright:
        return _FakePlaywright()

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def bootstrap(monkeypatch: pytest.MonkeyPatch):
    """Runs `bootstrap_storage_state` against stubs; returns the kwargs
    `establish_session` received and the items handed to the persister."""
    calls: dict = {"persisted": []}

    class _Vault:
        def resolve(self, ref):
            return b"credential"

    async def fake_establish_session(browser, **kwargs):
        calls["kwargs"] = kwargs
        if "on_capture" in kwargs:
            kwargs["on_capture"](CapturedPage(url="https://app.example/login", title="Login"))
            kwargs["on_capture"](
                CapturedForm(
                    page_url="https://app.example/login",
                    action_url="https://app.example/login",
                    method="POST",
                    fields=[
                        CapturedFormField(
                            name="pw",
                            input_type="password",
                            required=True,
                            default_value=None,
                            captured_selector="#pw",
                        )
                    ],
                )
            )
        return _FakeContext()

    monkeypatch.setattr(auth_bootstrap, "VaultSecretsClient", _Vault)
    monkeypatch.setattr(auth_bootstrap, "async_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(auth_bootstrap, "establish_session", fake_establish_session)
    monkeypatch.setattr(
        auth_bootstrap,
        "persist_login_capture",
        lambda app_id, items: calls["persisted"].extend(items),
    )

    async def logged_in(context, url):
        return calls.get("still_on_login", False)

    monkeypatch.setattr(auth_bootstrap, "_still_on_login_form", logged_in)
    return calls


async def test_bootstrap_fails_fast_when_login_is_rejected(
    monkeypatch: pytest.MonkeyPatch, bootstrap: dict
) -> None:
    _stub_login_page_url(monkeypatch, "https://app.example/login")
    bootstrap["still_on_login"] = True
    with pytest.raises(ApplicationError) as excinfo:
        await auth_bootstrap.bootstrap_storage_state(_app())  # type: ignore[arg-type]
    assert excinfo.value.type == LOGIN_FAILED_ERROR_TYPE
    assert excinfo.value.non_retryable


async def test_bootstrap_captures_and_persists_for_no_discovery_app(
    monkeypatch: pytest.MonkeyPatch, bootstrap: dict
) -> None:
    _stub_login_page_url(monkeypatch, None)
    path = await auth_bootstrap.bootstrap_storage_state(_app())  # type: ignore[arg-type]
    path.unlink()
    assert {"object_store", "discovery_run_id", "on_capture"} <= bootstrap["kwargs"].keys()
    assert [type(item) for item in bootstrap["persisted"]] == [CapturedPage, CapturedForm]


async def test_bootstrap_is_unchanged_for_discovery_required_app(
    monkeypatch: pytest.MonkeyPatch, bootstrap: dict
) -> None:
    _stub_login_page_url(monkeypatch, None)
    path = await auth_bootstrap.bootstrap_storage_state(_app(discovery_required=True))  # type: ignore[arg-type]
    path.unlink()
    assert bootstrap["kwargs"].keys() == {"auth_method", "credential", "base_url", "login_url"}
    assert bootstrap["persisted"] == []


async def test_bootstrap_does_not_recapture_once_login_form_exists(
    monkeypatch: pytest.MonkeyPatch, bootstrap: dict
) -> None:
    _stub_login_page_url(monkeypatch, "https://app.example/login")
    path = await auth_bootstrap.bootstrap_storage_state(_app())  # type: ignore[arg-type]
    path.unlink()
    assert "on_capture" not in bootstrap["kwargs"]
    assert bootstrap["persisted"] == []
