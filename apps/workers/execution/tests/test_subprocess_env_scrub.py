"""Generated specs must never inherit the worker's platform secrets, and only
see the target-app login when they actually sign in themselves. No DB, no
Vault: the credential lookup is stubbed."""

import json
from types import SimpleNamespace

import execution_worker.activities as activities_module
import pytest

HOSTILE = {
    "VAULT_TOKEN": "root",
    "DATABASE_URL": "postgresql://u:p@h/db",
    "POSTGRES_PASSWORD": "pw",
    "AWS_ACCESS_KEY_ID": "AKIA",
    "AWS_SECRET_ACCESS_KEY": "secret",
    "SESSION_SECRET_KEY": "sess",
    "ANTHROPIC_API_KEY": "sk-ant",
    "LITELLM_API_KEY": "sk-lite",
}
SAFE = {"PATH": "/bin", "NODE_OPTIONS": "--x", "PLAYWRIGHT_BROWSERS_PATH": "/pw", "LC_ALL": "C"}


@pytest.fixture
def worker_env(monkeypatch):
    for key in list(activities_module.os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**HOSTILE, **SAFE}.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def vault(monkeypatch):
    class FakeVault:
        resolved = 0

        def resolve(self, _ref):
            FakeVault.resolved += 1
            return self.payload

    monkeypatch.setattr(activities_module, "VaultSecretsClient", FakeVault)
    monkeypatch.setattr(activities_module, "_load_screenshot_capture_sync", lambda _id: "failed")
    return FakeVault


def _app(auth_method):
    return SimpleNamespace(id=1, secret_ref="applications/x/y", auth_method=auth_method)


def test_scrubbed_env_keeps_only_allowlisted_keys(worker_env):
    assert activities_module._scrubbed_env() == SAFE


def test_spec_env_has_no_platform_secrets_or_credentials(worker_env, vault):
    vault.payload = json.dumps({"username": "u", "password": "p"}).encode()
    env = activities_module._build_subprocess_env(
        _app("username_password"), include_storage_state=False, include_login=False
    )
    assert env == SAFE
    assert vault.resolved == 0


def test_self_signing_spec_gets_login_but_no_platform_secrets(worker_env, vault):
    vault.payload = json.dumps({"username": "u", "password": "p"}).encode()
    env = activities_module._build_subprocess_env(
        _app("username_password"), include_storage_state=False, include_login=True
    )
    assert env == {**SAFE, "AITESTGEN_LOGIN_USERNAME": "u", "AITESTGEN_LOGIN_PASSWORD": "p"}


def test_spec_never_gets_the_live_session(worker_env, vault):
    vault.payload = b'{"cookies": []}'
    env = activities_module._build_subprocess_env(
        _app("sso_session_reuse"), include_storage_state=False, include_login=True
    )
    assert "AITESTGEN_STORAGE_STATE" not in env
    assert vault.resolved == 0


def test_setup_env_defaults_still_get_the_session(worker_env, vault):
    vault.payload = b'{"cookies": []}'
    env = activities_module._build_subprocess_env(_app("sso_session_reuse"))
    assert env == {**SAFE, "AITESTGEN_STORAGE_STATE": '{"cookies": []}'}


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("await fillCredentials(page)", True),
        ("page.fill('#u', CREDENTIALS.username)", True),
        ("process.env.AITESTGEN_LOGIN_USERNAME", True),
        ("await page.goto('/')", False),
        (None, False),
    ],
)
def test_needs_login_credentials(code, expected):
    assert activities_module._needs_login_credentials(code) is expected
