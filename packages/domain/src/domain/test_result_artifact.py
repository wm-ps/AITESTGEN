"""TestResultArtifact — a pointer to one failure-capture artifact in object
storage (Run All Tests feature).

Metadata only, never a blob (AD-8's structured-metadata/object-storage-key
split, the same convention discovery's own screenshots already follow via
`packages/object_store`). Only ever written for a failing/timed-out/errored
`TestResult` — a passing test never gets a row here, by design, to bound
storage cost rather than by omission.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Column, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel

ArtifactType = Literal["screenshot", "trace", "video"]


class TestResultArtifact(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_result_artifact"  # pyright: ignore[reportAssignmentType]

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
    test_result_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("test_result.id"), nullable=False, index=True
        ),
    )
    artifact_type: str
    object_store_key: str
    content_type: str
    size_bytes: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
