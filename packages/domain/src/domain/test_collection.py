"""TestCollection — a user-made, named group of test cases ("Test suites" in
the UI) for one Application, e.g. Smoke or Regression.

Named `TestCollection`, not `TestSuite`, because `domain.TestSuite` already
means one Journey's generated tests. The UI label stays "Test suites".

`TestCollectionMember` is the many-to-many link: a test case can sit in any
number of collections and removing it from one never touches another. The
member points at a `Scenario` (not a `TestAsset`): a heal or suite
regeneration supersedes the `TestAsset` row and gives it a new id, but keeps
the same `scenario_id`, so membership survives them. A Scenario that is later
retired (`current=False`, e.g. by an Explorer re-promote) stays a member row
and is reported as "unavailable" until the user removes it.

Deleting a collection hard-deletes its member rows and (when the user agrees)
the runs started from it — see `api.test_collections`. No FK here uses
`ondelete`, matching the rest of the schema, so those deletes are explicit.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class TestCollection(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_collection"  # pyright: ignore[reportAssignmentType]
    # Name is unique per application, case-insensitively — a functional
    # unique index (`uq_test_collection_application_id_name`), created in the
    # migration since SQLModel can't declare `lower(name)` here.

    id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(PGUUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")),
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
    name: str = Field(sa_column=Column(String, nullable=False))
    # Users are hard-deleted, hence SET NULL (same as `TestRun.triggered_by_user_id`).
    created_by_user_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("platform_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TestCollectionMember(SQLModel, table=True):
    __test__ = False  # pytest: not a test class, despite the name prefix
    __tablename__ = "test_collection_member"  # pyright: ignore[reportAssignmentType]

    collection_id: uuid.UUID = Field(
        sa_column=Column(PGUUID(as_uuid=True), ForeignKey("test_collection.id"), primary_key=True),
    )
    scenario_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("scenario.id"),
            primary_key=True,
            index=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
