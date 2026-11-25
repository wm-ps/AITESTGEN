"""The run report goes only to someone who can still see the application.

A scheduled run mails the schedule's creator and a manual run its starter; if
that person has since been taken off the application (or out of its team), the
email is skipped instead of sending them results they may no longer see.
"""

import uuid

import pytest
from api.db import engine, init_db
from domain import (
    Application,
    ApplicationMember,
    Organization,
    PlatformUser,
    Team,
    TeamMember,
    TestRun,
)
from execution_worker.activities import _resolve_report_recipient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="requires PostgreSQL reachable")


def _setup(session: Session, *, grant: str | None, team: bool = True, role: str = "standard_user"):
    init_db()
    org = Organization(name=f"Org Recipient {uuid.uuid4().hex[:6]}")
    session.add(org)
    session.flush()
    user = PlatformUser(
        organization_id=org.id,
        email=f"u-{uuid.uuid4()}@example.com",
        name="Starter",
        hashed_password="x",
        role=role,
    )
    session.add(user)
    session.flush()
    team_row = Team(organization_id=org.id, name="Crew", is_default=True)
    session.add(team_row)
    session.flush()
    session.add(TeamMember(team_id=team_row.id, user_id=user.id))
    application = Application(
        organization_id=org.id,
        team_id=team_row.id if team else None,
        name="App",
        url="https://example.com/",
        environment="staging",
        auth_method="standard_login",
        secret_ref="unused",
    )
    session.add(application)
    session.flush()
    if grant:
        session.add(ApplicationMember(application_id=application.id, user_id=user.id, role=grant))
    run = TestRun(
        application_id=application.id,
        run_number=1,
        status="completed",
        environment_snapshot="staging",
        target_base_url_snapshot="https://example.com/",
        triggered_by_user_id=user.id,
    )
    session.add(run)
    session.commit()
    return user, application, run


@pytest.mark.parametrize("grant", ["viewer", "contributor", "app_admin"])
def test_a_starter_with_access_gets_the_report(grant: str) -> None:
    with Session(engine) as session:
        user, application, run = _setup(session, grant=grant)
        recipient, reason = _resolve_report_recipient(session, run, application)
    assert recipient is not None and recipient.id == user.id and reason == "ok"


def test_a_starter_who_lost_access_is_skipped() -> None:
    with Session(engine) as session:
        _, application, run = _setup(session, grant=None)
        recipient, reason = _resolve_report_recipient(session, run, application)
    assert recipient is None
    assert reason == "the recipient no longer has access to the application"


def test_a_super_admin_still_gets_reports_of_team_applications_but_not_personal_ones() -> None:
    with Session(engine) as session:
        _, application, run = _setup(session, grant=None, role="super_admin")
        recipient, _ = _resolve_report_recipient(session, run, application)
        assert recipient is not None  # implicit admin on a team application

        application.team_id = None  # now a personal application of someone else
        session.add(application)
        session.commit()
        recipient, reason = _resolve_report_recipient(session, run, application)
    assert recipient is None and "no longer has access" in reason
