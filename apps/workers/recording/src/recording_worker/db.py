"""Database engine wiring for the recording worker (Record and Play).

`apps/workers/recording` is its own deployable, separate from `apps/api` and
every other worker — it needs its own DB engine, reading the same
`DATABASE_URL` convention `api.db`/`discovery_worker.db`/`generation_worker.db`
already established.
"""

import os
from collections.abc import Generator

from sqlmodel import Session, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/aitestgen",
)

engine = create_engine(DATABASE_URL, echo=False)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
