"""`find_login_page_evidence`'s cross-origin fallback (`[FIXED]` in
assembler.py): for an OAuth/OIDC app, Discovery's captured login page is the
identity provider's own already-redirected authorization URL, carrying a
one-time `state`/`code_challenge` — replaying that verbatim on every later
test run reuses an expired, single-use request. A same-origin login form (the
common case) must keep working exactly as before."""

import os
import uuid

import pytest
from domain import Application, DiscoveryRun, Form, FormField, Organization, Page
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel
from test_suite_assembler.assembler import find_login_page_evidence

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/aitestgen",
)
engine = create_engine(DATABASE_URL, echo=False)


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="requires PostgreSQL reachable — start docker compose"
)


def _seed_login_page(session: Session, *, application_url: str, login_page_url: str) -> Application:
    org = Organization(name=f"Test Org {uuid.uuid4()}")
    session.add(org)
    session.flush()

    application = Application(
        organization_id=org.id,
        name="Test App",
        url=application_url,
        environment="staging",
        secret_ref="applications/org/secret",
        auth_method="standard_login",
    )
    session.add(application)
    session.flush()

    run = DiscoveryRun(application_id=application.id)
    session.add(run)
    session.flush()

    page = Page(application_id=application.id, discovery_run_id=run.id, url=login_page_url)
    session.add(page)
    session.flush()

    form = Form(
        application_id=application.id,
        discovery_run_id=run.id,
        page_id=page.id,
        action_url=login_page_url,
    )
    session.add(form)
    session.flush()

    session.add(FormField(form_id=form.id, input_type="password"))
    session.add(FormField(form_id=form.id, input_type="text"))
    session.flush()

    return application


def test_uses_the_captured_url_for_a_same_origin_login_form() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        application = _seed_login_page(
            session,
            application_url="https://acme.example.com",
            login_page_url="https://acme.example.com/login",
        )
        session.commit()

        evidence = find_login_page_evidence(session, application)

        assert evidence is not None
        assert evidence.url == "https://acme.example.com/login"


def test_falls_back_to_the_application_url_for_a_cross_origin_oauth_redirect() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        application = _seed_login_page(
            session,
            application_url="https://acme.example.com",
            login_page_url=(
                "https://idp.example.com/realms/acme/protocol/openid-connect/auth"
                "?response_type=code&client_id=acme-web&state=one-time-state"
                "&code_challenge=one-time-challenge&code_challenge_method=S256"
            ),
        )
        session.commit()

        evidence = find_login_page_evidence(session, application)

        assert evidence is not None
        assert evidence.url == "https://acme.example.com"


def test_falls_back_to_login_url_when_set_for_a_cross_origin_oauth_redirect() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        application = _seed_login_page(
            session,
            application_url="https://acme.example.com",
            login_page_url="https://idp.example.com/realms/acme/protocol/openid-connect/auth?state=x",
        )
        application.login_url = "https://acme.example.com/login"
        session.add(application)
        session.commit()

        evidence = find_login_page_evidence(session, application)

        assert evidence is not None
        assert evidence.url == "https://acme.example.com/login"
