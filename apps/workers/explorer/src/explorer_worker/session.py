"""Open a browser that is signed in to the target application — the one
way both the first look and every mission get in."""

import asyncio
import json
import uuid
from dataclasses import dataclass

from domain import Application
from explorer_core import ExplorerRun
from playwright.async_api import Error as PlaywrightError
from secrets_client import SecretRef, VaultSecretsClient
from sqlmodel import Session

from explorer_worker.browser import Eyes, storage_state_from
from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.memory import known_facts


@dataclass
class Target:
    app_name: str
    app_url: str
    login_url: str | None
    auth_method: str
    secret_ref: str
    notes: str | None
    # Test environments let missions save their own test data.
    non_production: bool = False
    application_id: uuid.UUID | None = None


def needs_sign_in(auth_method: str, secret_ref: str) -> bool:
    """Does using the app need a signed-in session? (Decides the `@auth`
    tag on every test Explorer hands over.)"""
    if auth_method == "sso_session_reuse":
        return True
    try:
        creds = json.loads(VaultSecretsClient().resolve(SecretRef(path=secret_ref)))
    except Exception:
        return True
    return bool(str(creds.get("username") or "").strip())


def load_target(run_id: uuid.UUID) -> Target:
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        if run is None:
            raise ValueError(f"explorer run {run_id} not found")
        app = session.get(Application, run.application_id)
        if app is None:
            raise ValueError("application not found")
        return Target(
            app.name,
            app.url,
            app.login_url,
            app.auth_method,
            app.secret_ref,
            _with_memory(run.notes, known_facts(app.id)),
            non_production=app.safety_posture == "non_production",
            application_id=app.id,
        )


def _with_memory(notes: str | None, facts: list[str]) -> str | None:
    """The user's notes plus everything remembered about this app — your
    answers and documents are trusted knowledge in every prompt."""
    if not facts:
        return notes
    known = "\n".join(f"- {f}" for f in facts)
    return f"{notes or ''}\nWhat the user has told Explorer before (trusted):\n{known}".strip()


async def open_signed_out(target: Target, record_dir: str | None = None) -> Eyes:
    """A browser that has not signed in, for sign-in tests. It knows the
    saved login so `{{username}}`/`{{password}}` can be typed. The caller
    closes it."""
    eyes = Eyes(target.app_url)
    await eyes.open(record_dir=record_dir)
    if target.auth_method != "sso_session_reuse":
        secret = await asyncio.to_thread(
            VaultSecretsClient().resolve, SecretRef(path=target.secret_ref)
        )
        creds = json.loads(secret)
        eyes.remember_login(
            target.login_url or target.app_url,
            str(creds.get("username") or ""),
            str(creds.get("password") or ""),
        )
    return eyes


async def open_signed_in(
    target: Target, journal: Journal, record_dir: str | None = None
) -> Eyes | None:
    """A signed-in browser on the app, or None (with a visible error event)
    when sign-in fails. The caller closes it."""
    eyes = Eyes(target.app_url)
    try:
        secret = await asyncio.to_thread(
            VaultSecretsClient().resolve, SecretRef(path=target.secret_ref)
        )
    except Exception:  # missing or unreadable: say so plainly, not a raw Vault error
        journal.event(
            "error",
            "The saved login is missing",
            "Explorer couldn't find this app's saved username and password. Enter them "
            "again in the app's settings, then start Explorer again.",
        )
        return None
    if target.auth_method == "sso_session_reuse":
        await eyes.open(storage_state=storage_state_from(secret), record_dir=record_dir)
        await eyes.goto(target.app_url)
        return eyes
    await eyes.open(record_dir=record_dir)
    creds = json.loads(secret)
    try:
        signed_in = await eyes.sign_in(
            target.login_url or target.app_url, creds.get("username", ""), creds.get("password", "")
        )
    except PlaywrightError:
        signed_in = False
    if signed_in:
        return eyes
    visit = await eyes.look(target.login_url or target.app_url, None, 0)
    journal.event(
        "error",
        "Couldn't sign in",
        "The login screen was still showing after signing in. Check the saved username and password.",
        journal.shot(visit.shot),
    )
    await eyes.close()
    return None
