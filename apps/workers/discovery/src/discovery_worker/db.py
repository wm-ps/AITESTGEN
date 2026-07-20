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

engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
