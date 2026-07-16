"""Scaffold-probe DB round-trip test (AC2: SQLModel + PostgreSQL wiring).

Requires a live PostgreSQL 18.x (the `uuidv7()` server default and PG UUID
column are Postgres-specific). Skips cleanly when no DB is reachable, so a
local run without `docker compose up` still passes the suite; CI provides a
Postgres service so this test actually exercises the round trip there.
"""

import pytest
from api.db import engine, init_db
from api.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


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


def test_scaffold_probe_round_trip() -> None:
    init_db()
    client = TestClient(app)

    created = client.post("/scaffold-probe")
    assert created.status_code == 200
    probe_id = created.json()["id"]
    assert probe_id

    fetched = client.get(f"/scaffold-probe/{probe_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == probe_id
    assert fetched.json()["note"] == "scaffold-ok"
