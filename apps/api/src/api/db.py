"""Database engine wiring — Story 1.1 scaffold only.

Reads `DATABASE_URL` from the environment with a local-dev default. A real
settings/config-loading convention (e.g. pydantic-settings) is intentionally
not established here — deferred to whichever story next touches app
configuration.
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
