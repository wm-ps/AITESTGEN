"""Signing in once (session.open_signed_in): later browsers start from the
session saved right after the real sign-in — as exported tests start from
auth.setup's saved state — and sign in for real again only when it stopped
working."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from explorer_worker import session

APP = "https://shop.example/app/"
TARGET = session.Target("Shop", APP, None, "standard_login", "secret/shop", None)


class FakeEyes:
    made: list[FakeEyes] = []
    session_works = True

    def __init__(self, base_url: str) -> None:
        self.entry_urls = {base_url}
        self.opened_with: Any = "not opened"
        self.signed_in = False
        self.closed = False
        context = SimpleNamespace(storage_state=self._state)
        self.page = SimpleNamespace(url=APP, context=context)
        FakeEyes.made.append(self)

    async def _state(self) -> dict[str, Any]:
        return {"cookies": [{"name": "sid", "value": "1"}], "origins": []}

    async def open(self, storage_state: Any = None, record_dir: Any = None) -> None:
        self.opened_with = storage_state

    def remember_login(self, *login: str) -> None:
        pass

    async def goto(self, url: str) -> tuple[None, int]:
        return None, 0

    async def on_sign_in_screen(self) -> bool:
        return not FakeEyes.session_works

    async def sign_in(self, *login: str) -> bool:
        self.signed_in = True
        self.page.url = APP + "#/Home"
        return True

    def remember_entry(self) -> None:
        self.entry_urls.add(self.page.url)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeEyes.made, FakeEyes.session_works = [], True
    session._SESSIONS.clear()
    monkeypatch.setattr(session, "Eyes", FakeEyes)
    vault = SimpleNamespace(resolve=lambda ref: json.dumps({"username": "u", "password": "p"}))
    monkeypatch.setattr(session, "VaultSecretsClient", lambda: vault)


def _open() -> FakeEyes:
    return asyncio.run(session.open_signed_in(TARGET, None))  # type: ignore[arg-type,return-value]


def test_signs_in_once_then_reuses_the_session() -> None:
    first = _open()
    assert first.signed_in and first.opened_with is None

    second = _open()
    assert not second.signed_in  # no second sign-in
    assert second.opened_with == {"cookies": [{"name": "sid", "value": "1"}], "origins": []}
    # Routes recorded from where the real sign-in landed still count as entries.
    assert APP + "#/Home" in second.entry_urls


def test_a_session_that_stopped_working_signs_in_for_real() -> None:
    _open()
    FakeEyes.session_works = False
    eyes = _open()
    reused, fresh = FakeEyes.made[1], FakeEyes.made[2]
    assert reused.closed and fresh is eyes
    assert eyes.signed_in and eyes.opened_with is None


def test_an_old_session_is_not_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    _open()
    clock = session.time.monotonic() + session.SESSION_REUSE_SECONDS + 1
    monkeypatch.setattr(session.time, "monotonic", lambda: clock)
    assert _open().signed_in


def test_an_app_with_no_login_is_opened_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_vault() -> None:
        raise AssertionError("an app with no login never needs its saved login")

    monkeypatch.setattr(session, "VaultSecretsClient", no_vault)
    public = session.Target(
        "Shop", APP, None, "standard_login", "secret/shop", None, requires_login=False
    )
    eyes = asyncio.run(session.open_signed_in(public, None))  # type: ignore[arg-type]
    assert isinstance(eyes, FakeEyes) and not eyes.signed_in
    assert session.needs_sign_in("standard_login", "secret/shop", requires_login=False) is False
