"""Authenticated storage_state bootstrap for a live-exploration session.

Reuses `discovery_worker.session.establish_session` — the same login/SSO
logic Discovery already relies on — but only long enough to dump a
Playwright `storageState` JSON blob to a temp file. Python Playwright is
never used past this point; the actual exploration browser is 100%
owned by the spawned `@playwright/mcp` subprocess (mcp_client.py), so raw
credentials never reach an LLM prompt or the live-flow transcript.
"""

import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path

from discovery_worker.crawler import CapturedForm, CapturedPage
from discovery_worker.session import establish_session
from domain import Application
from playwright.async_api import BrowserContext, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from secrets_client import SecretRef, VaultSecretsClient
from temporalio.exceptions import ApplicationError
from workflows.live_exploration_workflow import LOGIN_FAILED_ERROR_TYPE

from generation_worker.live_exploration.login_capture import (
    login_capture_kwargs,
    needs_login_capture,
    persist_login_capture,
)

logger = logging.getLogger(__name__)


async def _still_on_login_form(context: BrowserContext, url: str) -> bool:
    """True when a fresh page at the app's URL still shows a password field —
    the same login-form signal establish_session itself keys off."""
    page = await context.new_page()
    try:
        await page.goto(url, timeout=30000)
        try:
            await page.wait_for_selector('input[type="password"]', state="visible", timeout=8000)
        except PlaywrightTimeoutError:
            return False
        return True
    finally:
        await page.close()


async def bootstrap_storage_state(application: Application) -> Path:
    """Logs in once against the real application and returns the path to a
    storage_state JSON file suitable for `PlaywrightMCPClient(storage_state_path=...)`.
    Caller owns cleanup of the returned file.

    For a no-Discovery app whose login form was never captured, the same login
    also records it (see `login_capture`) so the exported suite's auth setup
    has real locators; any other app logs in exactly as before."""
    vault_client = VaultSecretsClient()
    credential = vault_client.resolve(SecretRef(path=application.secret_ref))

    captured: list[CapturedPage | CapturedForm] = []
    capture_kwargs = (
        login_capture_kwargs(captured)
        if await asyncio.to_thread(needs_login_capture, application)
        else {}
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await establish_session(
                browser,
                auth_method=application.auth_method,
                credential=credential,
                base_url=application.url,
                login_url=application.login_url,
                **capture_kwargs,
            )
            # establish_session is best-effort and never says whether the login
            # took. A rejected login used to slip through as a logged-out
            # session: the agent then guessed credentials against the real
            # login form (burning lockout attempts) and the request still
            # generated test cases from a transcript of login failures.
            if await _still_on_login_form(context, application.url):
                raise ApplicationError(
                    "Vantage couldn't sign in to the application with its saved credentials. "
                    "Update the application's login details in Settings, then try again.",
                    type=LOGIN_FAILED_ERROR_TYPE,
                    # A retry is another failed login against an account
                    # that may lock out after a few.
                    non_retryable=True,
                )
            storage_state = await context.storage_state()
        finally:
            await browser.close()

    if captured:
        try:
            await asyncio.to_thread(persist_login_capture, application.id, captured)
        except Exception:
            # Best-effort: the exploration this login serves must not fail on it.
            logger.exception("login_capture: failed to store login form for %s", application.id)

    fd_path = Path(tempfile.gettempdir()) / f"live-exploration-auth-{uuid.uuid4().hex}.json"
    fd_path.write_text(json.dumps(storage_state))
    return fd_path
