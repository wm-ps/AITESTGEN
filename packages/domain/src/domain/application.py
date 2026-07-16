"""Application — a target system registered for discovery (Story 1.3).

**First entity whose id is ever exposed to the frontend** — establishes the
architecture's UUIDv7-internal / UUIDv4-external convention for every entity
after it (`DiscoveryRun`, `Journey`, `Scenario`, `TestAsset`, ...): `id` is
the internal PK (UUIDv7, index locality) and never leaves the backend;
`external_id` (UUIDv4, opaque) is the only id ever returned in an API
response, since a UUIDv7's embedded timestamp would leak creation time.

`secret_ref` stores only the opaque reference returned by `SecretsClient`
(AD-5) — never the raw credential.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class Application(SQLModel, table=True):
    __tablename__ = "application"  # pyright: ignore[reportAssignmentType]

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
    name: str
    url: str
    environment: str
    secret_ref: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
