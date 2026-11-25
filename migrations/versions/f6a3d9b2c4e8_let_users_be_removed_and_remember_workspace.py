"""let a user who invited, recorded or reset a password be removed; remember the last workspace

Revision ID: f6a3d9b2c4e8
Revises: e3b8c1d7a4f6
Create Date: 2026-11-23 01:00:00.000000

Removing a user hard-deletes the account (after a warning). Three tables still
blocked that with a NOT NULL foreign key and no `ondelete`:

* `invite.invited_by_id` and `recording_session.created_by_id` become nullable
  `SET NULL` (the invite / recording stays, just without a creator);
* `password_reset.user_id` becomes `ON DELETE CASCADE` (a deleted user's reset
  tokens go with them).

Also adds `platform_user.last_workspace`: where the user lands at sign-in.

ponytail: the downgrade deletes invites and recording sessions that have lost
their creator, since the old columns were NOT NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a3d9b2c4e8"
down_revision: str | None = "e3b8c1d7a4f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _repoint(table: str, column: str, constraint: str, *, ondelete: str | None, nullable: bool) -> None:
    op.drop_constraint(constraint, table, type_="foreignkey")
    op.alter_column(table, column, existing_type=sa.UUID(), nullable=nullable)
    op.create_foreign_key(constraint, table, "platform_user", [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    op.add_column("platform_user", sa.Column("last_workspace", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    _repoint("invite", "invited_by_id", "invite_invited_by_id_fkey", ondelete="SET NULL", nullable=True)
    _repoint(
        "recording_session", "created_by_id", "recording_session_created_by_id_fkey", ondelete="SET NULL", nullable=True
    )
    _repoint("password_reset", "user_id", "password_reset_user_id_fkey", ondelete="CASCADE", nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM invite WHERE invited_by_id IS NULL")
    op.execute("DELETE FROM recording_session WHERE created_by_id IS NULL")
    _repoint("password_reset", "user_id", "password_reset_user_id_fkey", ondelete=None, nullable=False)
    _repoint(
        "recording_session", "created_by_id", "recording_session_created_by_id_fkey", ondelete=None, nullable=False
    )
    _repoint("invite", "invited_by_id", "invite_invited_by_id_fkey", ondelete=None, nullable=False)
    op.drop_column("platform_user", "last_workspace")
