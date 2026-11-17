"""A NUL byte (typed by the model, read off a page) never crashes a write."""

import uuid

from domain import Application, Organization
from explorer_core import ExplorerEvent, ExplorerRun
from explorer_worker.db import engine
from explorer_worker.journal import Journal
from sqlmodel import Session, select


def test_nul_bytes_are_dropped_before_writing() -> None:
    with Session(engine) as session:
        org = Organization(name=f"Org {uuid.uuid4()}")
        session.add(org)
        session.flush()
        app = Application(
            organization_id=org.id, name="x", url="https://x", environment="staging", secret_ref=""
        )
        session.add(app)
        session.flush()
        run = ExplorerRun(application_id=app.id, status="tested", insights={"v": ["a\x00b"]})
        session.add(run)
        session.commit()
        run_id = run.id
    Journal(run_id).event("thought", "C\x00C", "typed\x00")
    with Session(engine) as session:
        event = session.exec(select(ExplorerEvent).where(ExplorerEvent.run_id == run_id)).one()
        assert (event.title, event.detail) == ("CC", "typed")
        assert session.get(ExplorerRun, run_id).insights == {"v": ["ab"]}
