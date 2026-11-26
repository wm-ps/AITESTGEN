"""drop team memberships of super admins

Revision ID: d6f8a0b2c4e7
Revises: c5e7a9b1d3f6
Create Date: 2026-11-26 12:00:00.000000

A Super Admin is a team admin of every team without a membership row. People
promoted before that rule had a plain `team_member` row (usually in Migrated),
so they showed under Members. Their rows are redundant: access comes from the
role, so nothing is lost. Not reversible — the old rows carried no information.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6f8a0b2c4e7"
down_revision: str | None = "c5e7a9b1d3f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM team_member
        WHERE user_id IN (SELECT id FROM platform_user WHERE role = 'super_admin')
        """
    )


def downgrade() -> None:
    pass
