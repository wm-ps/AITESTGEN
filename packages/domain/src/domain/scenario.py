"""Scenario — an AI-generated integration test Scenario for a Journey (Story 4.1, AD-8).

`generation_run_id` stores the `Journey.attempt` value this Scenario's
`GenerationWorkflow` run belongs to (matching the `generation-{journey_id}-
{attempt}` workflow-ID convention) — lets the workflow ID always be
reconstructed from `journey_id` + `generation_run_id` for tracing, and gives
any future attempt-bump something to supersede by flipping `current` to
`False` rather than deleting (no feature triggers a second attempt today —
Story 4.3/FR-18 is cut in full, see sprint-change-proposal-2026-07-27.md).

`test_data` is the AI-defined field schema (name + mandatory flag) a reviewer
must fill in before this Scenario is considered complete — each entry's
`value` starts `None` and is filled in later via the API, never by the AI.
Completeness is computed on read (`test_data_complete`), not cached as a
separate column — a reasoned default: a stored flag would need to stay in
sync with every `test_data` write, and this codebase already prefers
deriving state over duplicating it (e.g. `Journey`/`Capability` excluding
`status="deleted"` rows rather than a separate active-count).

`safety_classification` (Run All Tests feature) is computed once, at
generation time, by reusing `discovery_worker.safety_engine`'s `classify()`
against every step in `steps` and keeping the most severe verdict —
`DESTRUCTIVE` > `UNKNOWN` > `SAFE`. It is persisted (not derived on read,
unlike `test_data_complete`) because classification only needs the AI/
pattern-matched output once; execution-time gating then trusts this stored
value as authoritative rather than reclassifying on every run.

`source` distinguishes a Scenario created through the normal Discovery ->
Journey -> Scenario pipeline (`ScenarioGenerationActivity`, called with its
default `source="discovery"`) from one created via `LiveExplorationTestWorkflow`
(live browser exploration from a user's plain-English request, see
`natural_language_flow.png`, which passes `source="nl"` explicitly), from one
created via Record and Play (a human drives a worker-hosted headed browser
through the real `playwright codegen` CLI; the recording service persists
`source="recorded"` — no LLM authors this code, unlike the other two
sources) — the frontend labels each of the latter two distinctly ("NL Test
Case" / "Recorded"). Every pre-existing row gets `'discovery'` via the
column's `server_default`, so a migration adding this column (or widening
this Literal) never relabels a test case that predates the feature.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

ScenarioType = Literal["happy", "negative", "edge"]
ScenarioSource = Literal["discovery", "nl", "recorded"]


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
    # Test Case Number feature: persistent, sequential, per-Application
    # display id (TC-001, TC-002, ...) — assigned once via an atomic claim
    # against Application.next_test_case_number at Scenario creation and
    # never reassigned, so it survives renames/test-data edits/executions
    # and TestAsset supersession (heal, suite regen) which all keep the
    # same scenario_id. ponytail: default 0 exists only so the ~14
    # pre-existing test fixtures that construct Scenario(...) directly
    # (without exercising this feature) keep working — every real row
    # gets a real value >=1 from the two creation activities.
    test_case_number: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    current: bool = Field(default=True)
    safety_classification: str = Field(
        default="UNKNOWN",
        sa_column=Column(String, server_default=text("'UNKNOWN'"), nullable=False),
    )
    safety_classification_reason: str | None = Field(default=None)
    source: str = Field(
        default="discovery",
        sa_column=Column(String, server_default=text("'discovery'"), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    def test_data_complete(self) -> bool:
        return all(
            bool(field.get("value")) for field in self.test_data if field.get("mandatory")
        )
