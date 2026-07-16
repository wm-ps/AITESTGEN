"""Create the first Organization + PlatformUser for dev/testing (Story 1.2).

No PRD story covers self-service registration (no "Sign Up" screen exists in
the UX inventory) — this is the only, non-UX way to create a signed-in-able
account locally. Idempotent: re-running with the same email is a no-op.

Usage: `uv run python -m api.scripts.seed_dev_data [email] [password] [org name]`
"""

import sys

from domain import Organization, PlatformUser
from sqlmodel import Session, select

from api.auth import hash_password
from api.db import engine, init_db

DEFAULT_EMAIL = "dev@example.com"
DEFAULT_PASSWORD = "devpassword123"
DEFAULT_NAME = "Dev User"
DEFAULT_ORG_NAME = "Dev Organization"


def seed(
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
    org_name: str = DEFAULT_ORG_NAME,
    name: str = DEFAULT_NAME,
) -> PlatformUser:
    init_db()
    with Session(engine) as session:
        existing = session.exec(select(PlatformUser).where(PlatformUser.email == email)).first()
        if existing is not None:
            print(f"already seeded: {email}")
            return existing

        org = Organization(name=org_name)
        session.add(org)
        session.flush()

        user = PlatformUser(
            organization_id=org.id,
            email=email,
            name=name,
            hashed_password=hash_password(password),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        print(f"seeded organization {org.name!r} and user {user.email!r}")
        return user


if __name__ == "__main__":
    args = sys.argv[1:]
    seed(*args)
