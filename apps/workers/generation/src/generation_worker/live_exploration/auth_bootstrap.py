"""Authenticated storage_state bootstrap for a live-exploration session.

Reuses `discovery_worker.session.establish_session` — the same login/SSO
logic Discovery already relies on — but only long enough to dump a
Playwright `storageState` JSON blob to a temp file. Python Playwright is
never used past this point; the actual exploration browser is 100%
owned by the spawned `@playwright/mcp` subprocess (mcp_client.py), so raw
credentials never reach an LLM prompt or the live-flow transcript.
"""

import json
import tempfile
import uuid
from pathlib import Path

from discovery_worker.session import establish_session
from domain import Application
from playwright.async_api import async_playwright
from secrets_client import SecretRef, VaultSecretsClient


async def bootstrap_storage_state(application: Application) -> Path:
    """Logs in once against the real application and returns the path to a
    storage_state JSON file suitable for `PlaywrightMCPClient(storage_state_path=...)`.
    Caller owns cleanup of the returned file."""
    vault_client = VaultSecretsClient()
    credential = vault_client.resolve(SecretRef(path=application.secret_ref))

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await establish_session(
                browser,
                auth_method=application.auth_method,
                credential=credential,
                base_url=application.url,
                login_url=application.login_url,
            )
            storage_state = await context.storage_state()
        finally:
            await browser.close()

    fd_path = Path(tempfile.gettempdir()) / f"live-exploration-auth-{uuid.uuid4().hex}.json"
    fd_path.write_text(json.dumps(storage_state))
    return fd_path
