"""Proof-of-wiring entity for Story 1.1 — not a real domain entity.

Exists solely to confirm FastAPI + SQLModel + Alembic + PostgreSQL are wired
end-to-end (AC2). The real domain model (Organization, Application, etc.)
lands in Stories 1.2/1.3 — do not build it out here. Safe to drop this table
once the real model supersedes it.

Primary key uses Postgres 18's native `uuidv7()` (architecture Consistency
Conventions: internal PKs are UUIDv7 for index locality) — this is the first
table in the repo, so it sets the pattern every later entity follows.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ScaffoldProbe(SQLModel, table=True):
    __tablename__ = "scaffold_probe"  # pyright: ignore[reportAssignmentType]  # SQLModel typing quirk

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=text("uuidv7()"),
        ),
    )
    note: str = Field(default="scaffold-ok")
    # tz-aware column so the UTC offset survives the round trip — this is the
    # first table in the repo, so it sets the timestamp convention 1.2+ copy.
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
