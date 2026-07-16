"""SecretsClient port (architecture AD-5).

Credentials and session state are written/read only through this interface,
backed by a dedicated secrets store — never a plaintext column in the
primary database. `VaultSecretsClient` (Story 1.3) is the first concrete
adapter; a CloudKMSSecretsClient would be an equally valid alternative
(the Vault-vs-cloud-KMS choice is deferred to deploy time by architecture).
"""

from typing import Protocol
from uuid import UUID

from secrets_client.vault_client import SecretRef, VaultSecretsClient


class SecretsClient(Protocol):
    def store(self, organization_id: UUID, secret: bytes) -> SecretRef:
        ...

    def resolve(self, ref: SecretRef) -> bytes:
        ...


__all__ = ["SecretRef", "SecretsClient", "VaultSecretsClient"]
