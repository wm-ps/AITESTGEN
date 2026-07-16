"""apps/api FastAPI entrypoint — Story 1.1 scaffold.

Only a health check and the scaffold-probe proof-of-wiring endpoints exist
here. Real domain endpoints (Onboarding, Review, Analytics) land in Stories
1.2+ (architecture Module Map).
"""

from typing import Annotated

from domain import ScaffoldProbe
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from api.db import get_session

app = FastAPI(title="Application Intelligence Platform API")

# Dev-only: allow the Vite dev server to call this API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scaffold-probe", response_model=ScaffoldProbe)
def create_scaffold_probe(session: SessionDep) -> ScaffoldProbe:
    probe = ScaffoldProbe()
    session.add(probe)
    session.commit()
    session.refresh(probe)
    return probe


@app.get("/scaffold-probe/{probe_id}", response_model=ScaffoldProbe)
def get_scaffold_probe(probe_id: str, session: SessionDep) -> ScaffoldProbe:
    probe = session.exec(select(ScaffoldProbe).where(ScaffoldProbe.id == probe_id)).one()
    return probe
