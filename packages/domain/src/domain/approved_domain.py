"""ApprovedDomain — an admin-approved host that Applications may be onboarded on.

`host` is a bare, lowercase hostname (no scheme/port/path). A URL is approved
when its host equals an entry or is a subdomain of one (`api.example.com`
under `example.com`) — matching lives in `api.approved_domains`.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class ApprovedDomain(SQLModel, table=True):
    __tablename__ = "approved_domain"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("organization_id", "host", name="uq_approved_domain_org_host"),)

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
    host: str = Field(nullable=False)
    created_by_name: str = Field(default="", nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
