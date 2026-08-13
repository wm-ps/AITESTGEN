"""ExplorationStep — a human-readable diagnostic record of how the crawler
reached a `BlockedTask` (Story 2.16 Task 1).

Deliberately not named `JourneyStep` (see Architecture AD-20): this records
a crawl-time path that may never become a `Journey` — `InferenceActivity`
(Story 2.6) creates `Journey` rows from the confirmed Application Model
after Discovery completes, independent of any `BlockedTask`. It is also
explicitly **not a replay script** — Story 2.16's re-crawl resume mechanism
never executes these steps; it re-crawls forward under normal rules from the
nearest confirmed entry point. See that story's Dev Notes for why the
original step-replay design was replaced.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ExplorationStep(SQLModel, table=True):
    __tablename__ = "exploration_step"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("blocked_task_id", "step_order"),)

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
    )
    blocked_task_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("blocked_task.id"), nullable=False, index=True
        ),
    )
    step_order: int = Field(sa_column=Column(Integer, nullable=False))
    page_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("page.id"), nullable=False),
    )
    action_description: str
    input_values: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
