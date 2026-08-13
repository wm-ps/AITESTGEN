"""ExecutionPolicy — per-Application declaration of whether/where generated
tests may be executed (Run All Tests feature).

Mirrors `Application.safety_posture`'s "declaration, not detection"
philosophy: `execution_enabled`/`allowed_base_urls`/
`destructive_actions_permitted` are explicit choices the user makes about
this Application, not something inferred from its URL. A production target
is a normal `allowed_base_urls` entry like any other — this table draws no
distinction between environments, only between "on the list" and "not on
the list" (consistent with this architecture's existing position that no
platform-side guardrail special-cases a production target — see
ARCHITECTURE-SPINE.md's Non-production technical safeguard note).

One row per Application (unique FK). `version` is bumped on every edit so a
`TestRun` can snapshot which policy version it validated against even after
the policy is later edited — see `TestRun.execution_policy_version`.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ExecutionPolicy(SQLModel, table=True):
    __tablename__ = "execution_policy"  # pyright: ignore[reportAssignmentType]

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
            PGUUID(as_uuid=True),
            ForeignKey("application.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
    )
    execution_enabled: bool = Field(default=False)
    allowed_base_urls: list[str] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    destructive_actions_permitted: bool = Field(default=False)
    video_capture_enabled: bool = Field(default=False)
    version: int = Field(default=1)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
