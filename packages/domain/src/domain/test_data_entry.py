"""TestDataEntry — the Test Data Pool (Story 2.20 Task 1).

User-seeded, per-Application values that persist across Discovery Runs and
are consulted first (ahead of page scanning, run reuse and synthesis) by the
Data Resolver (Story 2.13). `normalized_key` uses the same shared function
Story 2.15's `BlockedTask.aggregation_key` will use — see
`domain.key_normalization.aggregation_key` — so a pool entry and a blocked
requirement for the same underlying field always match automatically.

Sensitive values are held via `packages/secrets_client`'s existing Vault-
backed client, not in plain Postgres storage: `value` is null and
`secret_ref` (the opaque Vault path) is set instead, mirroring
`Application.secret_ref`.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class TestDataEntry(SQLModel, table=True):
    __tablename__ = "test_data_entry"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("application_id", "normalized_key"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("application.id"), nullable=False, index=True
        ),
    )
    label: str
    normalized_key: str = Field(sa_column=Column(String, nullable=False, index=True))
    value: str | None = Field(default=None)
    secret_ref: str | None = Field(default=None)
    is_sensitive: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
