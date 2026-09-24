"""Resolving a pre-authenticated `storageState` for `auth_mode="authenticated"`
recordings (plan §4) — reuses `discovery_worker.session.establish_session`,
the same login/SSO logic Discovery already relies on, exactly the way
`generation_worker.live_exploration.auth_bootstrap.bootstrap_storage_state`
already does for live-exploration sessions. Duplicated rather than imported
from that module — different caller/app, and it's a ~15-line function, not
worth a cross-worker-app import purely for this (the two existing
cross-worker-app dependencies in this repo — execution->generation,
generation->discovery — are for genuinely larger shared logic, not this).

For `auth_mode="logged_out"` recordings this module is never called —
Codegen launches against a fresh, logged-out browser and the human's own
recorded actions include the login step itself.
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
    """Logs in once against the real application (or reuses its stored SSO
    session) and returns the path to a storage_state JSON file suitable for
    `playwright codegen --load-storage=<path>`. Caller owns cleanup of the
    returned file."""
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

    path = Path(tempfile.gettempdir()) / f"recording-auth-{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(storage_state))
    return path
