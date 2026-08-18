"""PasswordReset — a single-use, time-limited token for an existing PlatformUser.

Mirrors `invite.py`'s token design (`token_hash` is the sole secret, raw
token only ever emailed once) but ties to an existing `user_id` rather than
creating one — this never issues a new PlatformUser, only lets an existing
one set a new password.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class PasswordReset(SQLModel, table=True):
    __tablename__ = "password_reset"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("platform_user.id"), nullable=False, index=True),
    )
    token_hash: str = Field(unique=True, index=True, nullable=False)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
