"""rename the Default team to Migrated

Revision ID: c5e7a9b1d3f6
Revises: b9d4f1a6c3e7
Create Date: 2026-11-24 10:00:00.000000

"Default" said nothing about the team: it is where everything that existed
before teams shipped was moved. An organisation that already has a team called
Migrated keeps the old name rather than break the unique team name.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5e7a9b1d3f6"
down_revision: str | None = "b9d4f1a6c3e7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE team SET name = 'Migrated'
        WHERE is_default AND name = 'Default'
          AND NOT EXISTS (
              SELECT 1 FROM team other
              WHERE other.organization_id = team.organization_id AND lower(other.name) = 'migrated'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE team SET name = 'Default'
        WHERE is_default AND name = 'Migrated'
          AND NOT EXISTS (
              SELECT 1 FROM team other
              WHERE other.organization_id = team.organization_id AND lower(other.name) = 'default'
          )
        """
    )
