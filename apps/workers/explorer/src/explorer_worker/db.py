"""Database engine wiring for the explorer worker.

`apps/workers/explorer` is its own deployable, separate from `apps/api`
and `apps/workers/discovery` — it needs its own DB engine, reading the same
`DATABASE_URL` convention `api.db`/`discovery_worker.db` established.
"""

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5433/aitestgen",
)

engine = create_engine(DATABASE_URL, echo=False)


def no_nul(value: Any) -> Any:
    """Postgres text can't hold a NUL (0x00) byte; a page or the model can
    produce one (a typed value, a read message)."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [no_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: no_nul(v) for k, v in value.items()}
    return value


@event.listens_for(Session, "before_flush")
def _strip_nul(session: Session, _context: Any, _instances: Any) -> None:
    for row in (*session.new, *session.dirty):
        for key, value in vars(row).items():
            if not key.startswith("_") and value is not None:
                clean = no_nul(value)
                if clean != value:
                    setattr(row, key, clean)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
