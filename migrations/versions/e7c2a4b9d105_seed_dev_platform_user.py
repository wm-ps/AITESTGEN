"""seed dev platform user and organization

Revision ID: e7c2a4b9d105
Revises: a4e1f9c2b7d3
Create Date: 2026-07-27 00:00:00.000000

Runs seeding as part of `alembic upgrade head` instead of a separate Jenkins
stage, so it applies wherever migrations run. No PRD story adds self-service
registration, so this is the only way a PlatformUser row gets created.
Idempotent: no-op if the email already exists.
"""

from collections.abc import Sequence

import bcrypt
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7c2a4b9d105"
down_revision: str | None = "a4e1f9c2b7d3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SEED_EMAIL = "dev@example.com"
SEED_PASSWORD = "devpassword123"
SEED_NAME = "Dev User"
SEED_ORG_NAME = "Dev Organization"


def upgrade() -> None:
    bind = op.get_bind()

    existing = bind.execute(
        sa.text("SELECT 1 FROM platform_user WHERE email = :email"),
        {"email": SEED_EMAIL},
    ).first()
    if existing is not None:
        return

    org_id = bind.execute(
        sa.text(
            "INSERT INTO organization (name, created_at) VALUES (:name, now()) "
            "RETURNING id"
        ),
        {"name": SEED_ORG_NAME},
    ).scalar_one()

    hashed_password = bcrypt.hashpw(SEED_PASSWORD.encode(), bcrypt.gensalt()).decode()
    bind.execute(
        sa.text(
            "INSERT INTO platform_user "
            "(organization_id, email, name, hashed_password, created_at) "
            "VALUES (:organization_id, :email, :name, :hashed_password, now())"
        ),
        {
            "organization_id": org_id,
            "email": SEED_EMAIL,
            "name": SEED_NAME,
            "hashed_password": hashed_password,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM platform_user WHERE email = :email"),
        {"email": SEED_EMAIL},
    )