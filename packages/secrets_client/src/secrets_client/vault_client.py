"""Vault-backed SecretsClient adapter (Story 1.3, architecture AD-5).

Dev-mode HashiCorp Vault chosen over a cloud-KMS adapter: portable across the
still-undecided SaaS/on-prem topology, trivial to run locally/in CI via a
container, no cloud account dependency. The Vault-vs-cloud-KMS choice is
explicitly deferred to deploy time by the architecture — this is not that
decision, just what unblocks the build now.

Credentials are written to Vault's KV v2 secrets engine; `SecretRef` is the
opaque path segment (organization-scoped, UUID4-suffixed), never the raw
credential — this is what Application.secret_ref stores.
"""

import os
import uuid
from dataclasses import dataclass

import hvac

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "dev-only-root-token")
VAULT_MOUNT_POINT = "secret"


@dataclass(frozen=True)
class SecretRef:
    """Opaque reference to a stored secret — never the raw credential."""

    path: str


class VaultSecretsClient:
    """SecretsClient (Protocol) adapter backed by Vault's KV v2 engine."""

    def __init__(self, client: hvac.Client | None = None) -> None:
        self._client = client or hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)

    def store(self, organization_id: uuid.UUID, secret: bytes) -> SecretRef:
        path = f"applications/{organization_id}/{uuid.uuid4()}"
        self._client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret={"value": secret.decode()},
            mount_point=VAULT_MOUNT_POINT,
        )
        return SecretRef(path=path)

    def resolve(self, ref: SecretRef) -> bytes:
        result = self._client.secrets.kv.v2.read_secret_version(
            path=ref.path,
            mount_point=VAULT_MOUNT_POINT,
            raise_on_deleted_version=True,
        )
        return result["data"]["data"]["value"].encode()
