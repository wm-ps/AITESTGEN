"""ActivityEvent — one row on the admin Activity page that no other table
already records: who changed a setting, policy, credential, teammate or
schedule, and who started scenario/test case generation.

Discovery runs and test runs are deliberately *not* copied in here — their
own `DiscoveryRun`/`TestRun` rows already carry status, counts and failure
reasons, so `GET /activity` reads them directly (and their status updates in
place instead of needing a second "finished" row).

`actor_name` and `application_name` are snapshots, so a row still reads
correctly after the person is removed or the Application is purged
(`application_id` is SET NULL then).
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

ActivityCategory = Literal["discovery", "scenarios", "test_cases", "test_runs", "settings"]
ActivityOutcome = Literal["running", "done", "failed", "changed", "stopped"]


class ActivityEvent(SQLModel, table=True):
    __tablename__ = "activity_event"  # pyright: ignore[reportAssignmentType]

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    external_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True),
    )
    organization_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
        ),
    )
    application_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("application.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    application_name: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    actor_name: str = Field(sa_column=Column(String, nullable=False))
    category: str = Field(sa_column=Column(String, nullable=False))
    outcome: str = Field(sa_column=Column(String, nullable=False))
    summary: str = Field(sa_column=Column(String, nullable=False))
    # Free-form per kind: `changes` ([{field, before, after}]) for a config
    # change, `journeys` ([{id, attempt}]) for a generation start — read back
    # by `api.activity` only.
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
