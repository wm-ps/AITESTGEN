"""A non-local Vault with no VAULT_TOKEN must fail closed, not fall back to the
known dev root token. No Vault needed."""

import importlib

import pytest
import secrets_client.vault_client as vault_client


def _reload(monkeypatch, addr, token):
    monkeypatch.setenv("VAULT_ADDR", addr)
    if token is None:
        monkeypatch.delenv("VAULT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("VAULT_TOKEN", token)
    return importlib.reload(vault_client)


@pytest.fixture(autouse=True)
def _restore_module(monkeypatch):
    yield
    monkeypatch.undo()
    importlib.reload(vault_client)


def test_remote_vault_without_token_raises(monkeypatch):
    module = _reload(monkeypatch, "http://vault:8200", None)
    with pytest.raises(RuntimeError, match="VAULT_TOKEN is not set"):
        module.VaultSecretsClient()


def test_local_vault_without_token_uses_dev_token(monkeypatch):
    module = _reload(monkeypatch, "http://localhost:8200", None)
    assert module.VAULT_TOKEN == "dev-only-root-token"
    module.VaultSecretsClient()


def test_explicit_token_wins_for_remote_vault(monkeypatch):
    module = _reload(monkeypatch, "http://vault:8200", "scoped-token")
    assert module.VAULT_TOKEN == "scoped-token"
    module.VaultSecretsClient()
