"""SecretsClient port (architecture AD-5).

Credentials and session state are written/read only through this interface,
backed by a dedicated secrets store (Vault or cloud KMS-backed envelope
encryption) — never a plaintext column in the primary database.
Implementations (VaultSecretsClient, CloudKMSSecretsClient) land in Story 1.3.

`SecretRef` is a value type not yet defined (lands with Story 1.3) — `Any`
stands in for it here rather than a placeholder class.
"""

from typing import Any, Protocol
from uuid import UUID


class SecretsClient(Protocol):
    def store(self, organization_id: UUID, secret: bytes) -> Any:
        """-> SecretRef."""
        ...

    def resolve(self, ref: Any) -> bytes:
        """ref: SecretRef."""
        ...
