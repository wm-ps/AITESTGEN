"""Vault dev-mode round trip (Story 1.3, AD-5).

Requires a live dev-mode Vault (docker compose). Skips cleanly when
unreachable, same convention as `apps/api`'s scaffold-probe DB test.
"""

import uuid

import hvac
import pytest
from hvac.exceptions import VaultError
from secrets_client.vault_client import VAULT_ADDR, VAULT_TOKEN, VaultSecretsClient


def _vault_available() -> bool:
    try:
        return hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN).sys.is_initialized()
    except (VaultError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _vault_available(),
    reason="no Vault reachable at VAULT_ADDR — start docker compose to run this test",
)


def test_store_and_resolve_round_trip() -> None:
    client = VaultSecretsClient()
    secret = b"super-secret-password"

    ref = client.store(uuid.uuid4(), secret)

    assert secret not in ref.path.encode()  # the ref is opaque, never the raw value
    assert client.resolve(ref) == secret
