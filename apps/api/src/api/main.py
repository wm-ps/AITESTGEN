"""apps/api FastAPI entrypoint — Story 1.1 scaffold.

Only a health check and the scaffold-probe proof-of-wiring endpoints exist
here. Real domain endpoints (Onboarding, Review, Analytics) land in Stories
1.2+ (architecture Module Map).
"""

import uuid
from typing import Annotated

from domain import ScaffoldProbe
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

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
def get_scaffold_probe(probe_id: uuid.UUID, session: SessionDep) -> ScaffoldProbe:
    probe = session.get(ScaffoldProbe, probe_id)
    if probe is None:
        raise HTTPException(status_code=404, detail="scaffold probe not found")
    return probe
