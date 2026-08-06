"""Invite — an admin-issued, single-use signup link (enterprise onboarding).

No self-service signup exists (matches `platform_user.py`/`seed_dev_data.py`'s
established constraint) — the only way a new `PlatformUser` gets created
post-seed is accepting one of these. `token_hash` (sha256 of a
`secrets.token_urlsafe` value) is the sole secret; the raw token is never
stored, only emailed once. `external_id` is the separate, safe-to-expose id
an admin's "pending invites" list/revoke action uses — the accept flow never
touches it, only the token.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Invite(SQLModel, table=True):
    __tablename__ = "invite"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("organization.id"),
            nullable=False,
            index=True,
        ),
    )
    invited_by_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("platform_user.id"), nullable=False),
    )
    email: str = Field(nullable=False, index=True)
    role: str = Field(default="member", nullable=False)
    token_hash: str = Field(unique=True, index=True, nullable=False)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
