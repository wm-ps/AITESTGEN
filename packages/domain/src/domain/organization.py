"""Organization — the tenant-boundary entity (architecture AD-12).

Every Application and User belongs to exactly one Organization; every
`apps/api` query is scoped by it through the one central mechanism in
`api.auth` (Story 1.2). Internal PK is UUIDv7 per the Consistency
Conventions established by Story 1.1's `ScaffoldProbe` — never exposed to
the frontend (this entity's id never leaves the backend; there is nothing
for a client to look up an Organization by).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Organization(SQLModel, table=True):
    __tablename__ = "organization"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    name: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
