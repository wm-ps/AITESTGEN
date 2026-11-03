"""ApplicationEnvironment — an additional deployment of an Application that
the same test cases can run against (Application Settings → Environments).

The Application row itself is the *default* environment (its `environment`
label, `url`, `login_url`, `auth_method`, `secret_ref`); a run, schedule or
download with no environment (`environment_id IS NULL`) means exactly that, so
every pre-existing row keeps its behavior with no backfill. This table holds
only the extra ones.

Each row points at its own Vault secret (`secret_ref`), in the same blob shape
the default uses for its `auth_method`. Hard-deleted — the API refuses the
delete while any `TestRun` or `Schedule` references the row, and both FKs are
`ON DELETE RESTRICT`, so history can never dangle.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, Session, SQLModel, select

from domain.application import Application


class ApplicationEnvironment(SQLModel, table=True):
    __tablename__ = "application_environment"  # pyright: ignore[reportAssignmentType]

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
    url: str = Field(sa_column=Column(String, nullable=False))
    login_url: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    auth_method: str = Field(default="standard_login", sa_column=Column(String, nullable=False))
    requires_login: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default=text("true")),
    )
    secret_ref: str = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


def find_environment(
    session: Session, application: Application, external_id: uuid.UUID | str
) -> ApplicationEnvironment:
    """The environment with this external id *of this application*. Raises
    `LookupError` for an unknown id or one that belongs to another
    Application."""
    environment = session.exec(
        select(ApplicationEnvironment).where(
            ApplicationEnvironment.external_id == uuid.UUID(str(external_id)),
            ApplicationEnvironment.application_id == application.id,
        )
    ).first()
    if environment is None:
        raise LookupError(f"environment {external_id} not found for application")
    return environment


def effective_application(
    application: Application, environment: ApplicationEnvironment | None
) -> Application:
    """The Application as a run/download should see it: `application` itself
    when `environment` is None (the default environment), otherwise a
    detached copy with the environment's name/url/login_url/auth_method/
    requires_login/secret_ref swapped in. The assembler and the execution
    worker's auth helpers already take an `Application`, so they need no
    signature change — they just receive this copy.

    The copy is a brand-new transient instance, never added to a session, so
    it can't be flushed or accidentally mutate the real row.
    """
    if environment is None:
        return application
    values = {column.name: getattr(application, column.name) for column in Application.__table__.columns}  # pyright: ignore[reportAttributeAccessIssue]
    values.update(
        environment=environment.name,
        url=environment.url,
        login_url=environment.login_url,
        auth_method=environment.auth_method,
        requires_login=environment.requires_login,
        secret_ref=environment.secret_ref,
    )
    return Application(**values)
