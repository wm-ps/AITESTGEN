"""rename organisation roles: admin -> super_admin, member -> standard_user

Revision ID: d1a7f3c9e5b2
Revises: c4e8a1f6b2d9
Create Date: 2026-11-23 00:00:00.000000

First step of team workspaces: the stored organisation roles get names that
cannot be confused with the team and application roles added later. Pure data
rename, same permissions — `viewer` is untouched (it is retired when
application-level roles land). Applies to both `platform_user.role` and the
pending `invite.role`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1a7f3c9e5b2"
down_revision: str | None = "c4e8a1f6b2d9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_RENAMES = (("admin", "super_admin"), ("member", "standard_user"))


def _rename(pairs: Sequence[tuple[str, str]]) -> None:
    for table in ("platform_user", "invite"):
        for old, new in pairs:
            op.execute(sa.text(f"UPDATE {table} SET role = :new WHERE role = :old").bindparams(old=old, new=new))


def upgrade() -> None:
    _rename(_RENAMES)
    op.alter_column("platform_user", "role", server_default="standard_user")


def downgrade() -> None:
    op.alter_column("platform_user", "role", server_default="member")
    _rename([(new, old) for old, new in _RENAMES])
