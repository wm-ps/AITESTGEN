"""credential_check.verify_login — the "Start discovery" login pre-check.

Real Chromium against a tiny local app with a server-rendered login (same
convention as test_page_readiness.py) — own app rather than fixtures/
target_app.py, which accepts *any* credentials and so can't exercise the
rejected paths. Settle/wait windows are shrunk so the "no signal" cases don't
wait out the real 60 s.
"""

import json
import socket
import threading
import time

import pytest
import uvicorn
from discovery_worker import credential_check
from discovery_worker.credential_check import verify_login
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from playwright.async_api import async_playwright

_app = FastAPI()


def _login_form(action: str, message: str = "") -> str:
    return f"""
    <html><body>
    {message}
    <form method="post" action="{action}">
      <input type="text" name="username">
      <input type="password" name="password">
      <button type="submit">Log in</button>
    </form>
    </body></html>
    """


@_app.get("/", response_class=HTMLResponse)
def landing() -> str:
    return '<html><body><a href="/login">Sign in</a></body></html>'


@_app.get("/noform", response_class=HTMLResponse)
def no_form() -> str:
    return "<html><body><h1>Hello — nothing to sign in to</h1></body></html>"


@_app.get("/home", response_class=HTMLResponse)
def home() -> str:
    return "<html><body><h1>Welcome</h1></body></html>"


@_app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return _login_form("/login")


@_app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if password == "good":
        return RedirectResponse(url="/home", status_code=303)
    return HTMLResponse(
        _login_form("/login", '<div role="alert">Invalid username or password</div>')
    )


# A rejection that never says why — the check can't prove anything either way.
@_app.get("/silent", response_class=HTMLResponse)
def silent_page() -> str:
    return _login_form("/silent")


@_app.post("/silent", response_class=HTMLResponse)
def silent_login(username: str = Form(...), password: str = Form(...)) -> str:
    return _login_form("/silent")


# A rejection in wording the (English-only) matcher doesn't recognise.
@_app.get("/foreign", response_class=HTMLResponse)
def foreign_page() -> str:
    return _login_form("/foreign")


@_app.post("/foreign", response_class=HTMLResponse)
def foreign_login(username: str = Form(...), password: str = Form(...)) -> str:
    return _login_form("/foreign", '<div role="alert">Zugangsdaten falsch eingegeben</div>')


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def login_site():
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(_app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def short_windows(monkeypatch):
    monkeypatch.setattr(credential_check, "_SETTLE_SECONDS", 3)
    monkeypatch.setattr(credential_check, "_POLL_SECONDS", 0.2)
    monkeypatch.setattr(credential_check, "_FORM_WAIT_MS", 1500)
    monkeypatch.setattr(credential_check, "_GOTO_TIMEOUT_MS", 3000)
    monkeypatch.setattr(credential_check, "_GOTO_ATTEMPTS", 1)


async def _verify(base_url: str, *, login_url: str | None = None, password: str = "good"):
    credential = json.dumps({"username": "qa-account", "password": password}).encode()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            return await verify_login(
                browser, credential=credential, base_url=base_url, login_url=login_url
            )
        finally:
            await browser.close()


async def test_valid_credentials_via_the_login_url(login_site):
    result = await _verify(login_site, login_url=f"{login_site}/login")

    assert result.status == "valid"


async def test_valid_credentials_found_by_following_the_sign_in_link(login_site):
    result = await _verify(f"{login_site}/")

    assert result.status == "valid"


async def test_login_url_is_preferred_over_the_deployed_url(login_site):
    # The Deployed URL has no login form at all; only the Login URL does.
    result = await _verify(f"{login_site}/noform", login_url=f"{login_site}/login")

    assert result.status == "valid"


async def test_wrong_password_is_invalid_when_the_app_says_so(login_site):
    result = await _verify(login_site, login_url=f"{login_site}/login", password="bad")

    assert result.status == "invalid"
    assert "Invalid username or password" in (result.detail or "")


async def test_silent_rejection_is_uncertain_not_invalid(login_site):
    result = await _verify(login_site, login_url=f"{login_site}/silent", password="bad")

    assert result.status == "uncertain"


async def test_unrecognised_error_wording_is_uncertain_not_invalid(login_site):
    result = await _verify(login_site, login_url=f"{login_site}/foreign", password="bad")

    assert result.status == "uncertain"


async def test_no_login_form_is_uncertain(login_site):
    result = await _verify(f"{login_site}/noform")

    assert result.status == "uncertain"
    assert "login form" in (result.detail or "")


async def test_unreachable_site_is_uncertain():
    result = await _verify(f"http://127.0.0.1:{_free_port()}/")

    assert result.status == "uncertain"
