"""Database engine wiring for the execution worker (Run All Tests feature).

`apps/workers/execution` is its own deployable, separate from `apps/api` and
the other workers — it needs its own DB engine, reading the same
`DATABASE_URL` convention `api.db`/`discovery_worker.db`/`generation_worker.db`
already established.
"""

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/aitestgen",
)

engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
