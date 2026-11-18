"""Vault-backed SecretsClient adapter (Story 1.3, architecture AD-5).

HashiCorp Vault chosen over a cloud-KMS adapter: portable across the
still-undecided SaaS/on-prem topology, trivial to run locally/in CI via a
container, no cloud account dependency. Local dev runs a persistent
file-storage Vault (docker-compose.yml); CI runs an ephemeral dev-mode one. The Vault-vs-cloud-KMS choice is
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
# The fixed dev token is only a fallback for a Vault on this machine (docker-
# compose, CI). Any other address with no VAULT_TOKEN set fails closed, like
# auth.py does for the session key, instead of silently using a known root token.
_LOCAL_VAULT_PREFIXES = ("http://localhost", "http://127.0.0.1")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN") or (
    "dev-only-root-token" if VAULT_ADDR.startswith(_LOCAL_VAULT_PREFIXES) else ""
)
VAULT_MOUNT_POINT = "secret"


@dataclass(frozen=True)
class SecretRef:
    """Opaque reference to a stored secret — never the raw credential."""

    path: str


class VaultSecretsClient:
    """SecretsClient (Protocol) adapter backed by Vault's KV v2 engine."""

    def __init__(self, client: hvac.Client | None = None) -> None:
        if client is None and not VAULT_TOKEN:
            raise RuntimeError(f"VAULT_TOKEN is not set (VAULT_ADDR={VAULT_ADDR})")
        self._client = client or hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)

    def store(self, organization_id: uuid.UUID, secret: bytes) -> SecretRef:
        path = f"applications/{organization_id}/{uuid.uuid4()}"
        self._client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret={"value": secret.decode()},
            mount_point=VAULT_MOUNT_POINT,
        )
        return SecretRef(path=path)

    def update(self, ref: SecretRef, secret: bytes) -> None:
        """Overwrites `ref`'s existing path in place — KV v2 versions the
        write automatically, so `secret_ref` never changes and nothing is
        orphaned (unlike `store`, which always mints a fresh path)."""
        self._client.secrets.kv.v2.create_or_update_secret(
            path=ref.path,
            secret={"value": secret.decode()},
            mount_point=VAULT_MOUNT_POINT,
        )

    def resolve(self, ref: SecretRef) -> bytes:
        result = self._client.secrets.kv.v2.read_secret_version(
            path=ref.path,
            mount_point=VAULT_MOUNT_POINT,
            raise_on_deleted_version=True,
        )
        return result["data"]["data"]["value"].encode()

    def delete(self, ref: SecretRef) -> None:
        """Permanently destroys every version of the secret (not a soft
        delete) — used only by the deleted-project purge job. `hvac` treats
        deleting an already-gone path as a no-op, not an error, so a retried
        purge activity stays safe to call this again."""
        self._client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=ref.path,
            mount_point=VAULT_MOUNT_POINT,
        )
