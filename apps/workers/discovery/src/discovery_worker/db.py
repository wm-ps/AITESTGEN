"""Database engine wiring for the discovery worker (Story 2.2).

`apps/workers/discovery` is its own deployable, separate from `apps/api` —
it needs its own DB engine, reading the same `DATABASE_URL` convention
`api.db` established in Story 1.1 rather than importing `apps/api` directly.
"""

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/aitestgen",
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    # No bound on either previously — a stuck connection attempt or a
    # lock-contended commit (both real possibilities against a shared dev
    # Postgres) could block indefinitely. Now that DB commits run via
    # `asyncio.to_thread` (see crawler.py's `_CaptureSink.add`), a stuck
    # call frees its thread within these bounds instead of parking it
    # forever.
    connect_args={"connect_timeout": 10, "options": "-c statement_timeout=30000"},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
