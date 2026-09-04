"""One-off backfill — ensures every existing Application has the 3 default
schedules (`_DEFAULT_SCHEDULE_SPECS` in `api.main`: Nightly/Weekly/Monthly
Regression, disabled) that `create_application` now seeds automatically for
*new* Applications only. Applications created before that change has no
retroactive effect, hence this script.

Reuses `_seed_default_schedules` as-is — no second scheduling
implementation. Idempotent per default name, not just per run: that helper
already turns a name collision with an existing (application_id, name) row
into a caught IntegrityError (via the partial unique index), rolled back
and logged, before any Temporal RPC — so re-running this script, or running
it against an Application that already has some but not all 3 defaults,
only creates the ones actually missing and never duplicates the rest.

Run with: uv run --package api python -m api.scripts.backfill_default_schedules
"""

import asyncio

from domain import Application
from sqlmodel import Session, select

from api.db import engine, init_db
from api.main import _seed_default_schedules


async def backfill() -> None:
    init_db()
    with Session(engine) as session:
        applications = session.exec(
            select(Application).where(Application.deleted_at.is_(None))  # type: ignore[attr-defined]
        ).all()
        print(f"backfilling default schedules for {len(applications)} application(s)")
        for application in applications:
            print(f"  {application.name} ({application.external_id})")
            await _seed_default_schedules(session, application)
    print("done")


if __name__ == "__main__":
    asyncio.run(backfill())
