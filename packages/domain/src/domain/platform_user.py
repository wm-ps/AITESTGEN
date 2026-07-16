"""PlatformUser — a signed-in user of the platform itself (Story 1.2).

Named `platform_user` (not `user`, a reserved SQL keyword, and not `User`,
which would collide with the future notion of a target Application's own
end users) — this is strictly the QA Director / Engineering Leader persona
signing into this tool.

`hashed_password` is never plaintext (bcrypt). Its id is never returned in
an API response as of this story (the avatar menu shows name/email only) —
if a future story needs to expose it, apply the UUIDv7-internal /
UUIDv4-external split established by `Application` (Story 1.3) rather than
leaking this table's PK.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class PlatformUser(SQLModel, table=True):
    __tablename__ = "platform_user"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("organization.id"),
            nullable=False,
            index=True,
        ),
    )
    email: str = Field(unique=True, index=True, nullable=False)
    name: str
    hashed_password: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
