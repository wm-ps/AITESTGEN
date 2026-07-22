"""Scenario — an AI-generated integration test Scenario for a Journey (Story 4.1, AD-8).

`generation_run_id` stores the `Journey.attempt` value this Scenario's
`GenerationWorkflow` run belongs to (matching the `generation-{journey_id}-
{attempt}` workflow-ID convention) — lets the workflow ID always be
reconstructed from `journey_id` + `generation_run_id` for tracing, and gives
Story 4.3's regeneration something to supersede by by flipping `current` to
`False` rather than deleting.

`test_data` is the AI-defined field schema (name + mandatory flag) a reviewer
must fill in before this Scenario is considered complete — each entry's
`value` starts `None` and is filled in later via the API, never by the AI.
Completeness is computed on read (`test_data_complete`), not cached as a
separate column — a reasoned default: a stored flag would need to stay in
sync with every `test_data` write, and this codebase already prefers
deriving state over duplicating it (e.g. `Journey`/`Capability` excluding
`status="deleted"` rows rather than a separate active-count).
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

ScenarioType = Literal["happy", "negative", "edge"]


class Scenario(SQLModel, table=True):
    __tablename__ = "scenario"  # pyright: ignore[reportAssignmentType]

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
    journey_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("journey.id"), nullable=False, index=True
        ),
    )
    type: str
    name: str
    steps: list[str] = Field(default_factory=list, sa_column=Column(JSONB, nullable=False))
    expected_result: str = Field(default="")
    test_data: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    generation_run_id: int
    current: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def test_data_complete(self) -> bool:
        return all(
            bool(field.get("value")) for field in self.test_data if field.get("mandatory")
        )
