"""BlockedTask — one aggregated, open ask for a DEFER the Planner (Story
2.11) reached, from either the Safety Engine (Story 2.12, `required_type=
"approval"`) or the Data Resolver (Story 2.13, `required_type="data"`)
(Story 2.15).

Identity is `(application_id, aggregation_key)`, never
`(discovery_run_id, ...)` — a block is a property of the Application, not
one run of it, so the same missing thing found again on a later Discovery
Run still attaches to the same open row rather than creating a second one.
`discovery_run_id` is only the run that first created the row (informational
— which run to point a user back to — not part of the lookup key).

`waiting_count` is this story's own placeholder for AC 5's "how many
exploration paths are waiting on it": incremented on every attach. Story
2.16's `ExplorationStep` (which references this entity by FK, not owned
here) will eventually give an exact per-path count — swapping this counter
for a `COUNT(*)` over that table is a natural upgrade, not a conflict, once
2.16 exists.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

BlockedTaskStatus = Literal["blocked_data", "blocked_approval", "blocked_both", "resolved"]
RequiredType = Literal["data", "approval"]


class BlockedTask(SQLModel, table=True):
    __tablename__ = "blocked_task"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # AC 1: the attach-or-create lookup's own index — an open row for
        # this Application with this key, found in one indexed query.
        Index("ix_blocked_task_app_key_status", "application_id", "aggregation_key", "status"),
    )

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
    application_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("application.id"), nullable=False, index=True
        ),
    )
    discovery_run_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("discovery_run.id"), nullable=False),
    )
    # str, not the Literal — same SQLModel/Literal limitation as
    # Application.auth_method; the Literal is still the source of truth for
    # callers.
    status: str = Field(default="blocked_data")
    aggregation_key: str = Field(index=True, nullable=False)
    required_description: str
    required_type: str
    waiting_count: int = Field(default=1)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    resolved_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
