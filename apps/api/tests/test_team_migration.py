"""Migration e3b8c1d7a4f6 (teams + application access) keeps existing data and
access intact.

Builds a throwaway database, migrates it to the revision before teams, adds a
realistic org (super admin, user, viewer, applications, a pending viewer
invite) plus a second org, upgrades, and checks that nobody loses access and
nothing leaks across organisations; then downgrades and upgrades again.

Slow (it runs Alembic several times) and needs a PostgreSQL server where the
DATABASE_URL user may CREATE DATABASE.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from api.db import engine
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parents[3]
BEFORE_TEAMS = "d1a7f3c9e5b2"


def _db_available() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(),
    reason="no PostgreSQL reachable at DATABASE_URL — start docker compose to run this test",
)


def _alembic(url: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
    )


def _insert_org(conn, name: str) -> uuid.UUID:
    return conn.execute(
        text("INSERT INTO organization (name, created_at) VALUES (:n, now()) RETURNING id"), {"n": name}
    ).scalar_one()


def _insert_user(conn, org_id: uuid.UUID, role: str) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO platform_user (organization_id, email, name, hashed_password, role, created_at)"
            " VALUES (:o, :e, :n, 'x', :r, now()) RETURNING id"
        ),
        {"o": org_id, "e": f"{role}-{uuid.uuid4()}@example.com", "n": role, "r": role},
    ).scalar_one()


def _insert_app(conn, org_id: uuid.UUID, name: str) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO application (external_id, organization_id, name, url, environment, secret_ref, created_at)"
            " VALUES (gen_random_uuid(), :o, :n, 'https://example.com', 'uat', 'ref', now()) RETURNING id"
        ),
        {"o": org_id, "n": name},
    ).scalar_one()


def _grants(conn) -> dict[tuple[uuid.UUID, uuid.UUID], str]:
    rows = conn.execute(text("SELECT application_id, user_id, role FROM application_member")).all()
    return {(r.application_id, r.user_id): r.role for r in rows}


def test_teams_migration_preserves_access_and_is_repeatable() -> None:
    db_name = f"aitestgen_mig_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    url = engine.url.set(database=db_name).render_as_string(hide_password=False)
    scratch = create_engine(url)
    try:
        _alembic(url, "upgrade", BEFORE_TEAMS)
        with scratch.begin() as conn:
            org_a, org_b = _insert_org(conn, "Org A"), _insert_org(conn, "Org B")
            boss = _insert_user(conn, org_a, "super_admin")
            worker = _insert_user(conn, org_a, "standard_user")
            reader = _insert_user(conn, org_a, "viewer")
            outsider = _insert_user(conn, org_b, "standard_user")
            app_1, app_2 = _insert_app(conn, org_a, "One"), _insert_app(conn, org_a, "Two")
            app_b = _insert_app(conn, org_b, "Other org")
            conn.execute(
                text(
                    "INSERT INTO invite (external_id, organization_id, invited_by_id, email, role, token_hash,"
                    " expires_at, created_at) VALUES (gen_random_uuid(), :o, :b, 'pending@example.com', 'viewer',"
                    " 'hash', now() + interval '1 day', now())"
                ),
                {"o": org_a, "b": boss},
            )

        _alembic(url, "upgrade", "head")
        with scratch.connect() as conn:
            teams = conn.execute(text("SELECT id, organization_id, name, is_default FROM team")).all()
            org_count = conn.execute(text("SELECT count(*) FROM organization")).scalar_one()
            # Exactly one "Migrated" team per organisation (earlier migrations may seed organisations of their own).
            assert len(teams) == org_count
            assert {(t.name, t.is_default) for t in teams} == {("Migrated", True)}
            default = {t.organization_id: t.id for t in teams}
            ours = {boss, worker, reader, outsider}

            members = {
                (m.team_id, m.user_id): m.role
                for m in conn.execute(text("SELECT * FROM team_member")).all()
                if m.user_id in ours
            }
            # The super admin's membership row is dropped: they are in every team by role.
            assert members == {
                (default[org_a], worker): "team_member",
                (default[org_a], reader): "team_member",
                (default[org_b], outsider): "team_member",
            }

            team_of = {a.id: a.team_id for a in conn.execute(text("SELECT id, team_id FROM application")).all()}
            assert team_of == {app_1: default[org_a], app_2: default[org_a], app_b: default[org_b]}

            # Nobody loses access: user -> contributor, old viewer -> viewer, on every application of their org;
            # the super admin needs no rows, nothing crosses organisations.
            assert {k: v for k, v in _grants(conn).items() if k[1] in ours} == {
                (app_1, worker): "contributor",
                (app_2, worker): "contributor",
                (app_1, reader): "viewer",
                (app_2, reader): "viewer",
                (app_b, outsider): "contributor",
            }
            roles = {r.id: r.role for r in conn.execute(text("SELECT id, role FROM platform_user")).all()}
            assert {k: v for k, v in roles.items() if k in ours} == {
                boss: "super_admin",
                worker: "standard_user",
                reader: "standard_user",
                outsider: "standard_user",
            }
            assert conn.execute(text("SELECT role FROM invite WHERE email = 'pending@example.com'")).scalar_one() == "standard_user"
            assert conn.execute(text("SELECT count(*) FROM application WHERE created_by_id IS NOT NULL")).scalar_one() == 0

        # The later migration (a user who invited/recorded can be removed) is in place too.
        with scratch.connect() as conn:
            nullable = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'invite' AND column_name = 'invited_by_id'"
                )
            ).scalar_one()
            assert nullable == "YES"
            assert conn.execute(
                text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'platform_user' AND column_name = 'last_workspace'")
            ).scalar_one() == 1

        _alembic(url, "downgrade", BEFORE_TEAMS)
        with scratch.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('team')")).scalar_one() is None
            roles = {r.id: r.role for r in conn.execute(text("SELECT id, role FROM platform_user")).all()}
            assert roles[reader] == "viewer"  # only viewer grants -> turned back into a viewer
            assert roles[worker] == "standard_user"

        _alembic(url, "upgrade", "head")
        with scratch.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM team")).scalar_one() == org_count
            assert len({k: v for k, v in _grants(conn).items() if k[1] in ours}) == 5
    finally:
        scratch.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin_engine.dispose()
