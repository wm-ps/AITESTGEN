"""Database engine wiring for the generation worker (Story 4.1).

`apps/workers/generation` is its own deployable, separate from `apps/api`
and `apps/workers/discovery` — it needs its own DB engine, reading the same
`DATABASE_URL` convention `api.db`/`discovery_worker.db` established.
"""

import os
from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/aitestgen",
)

engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
