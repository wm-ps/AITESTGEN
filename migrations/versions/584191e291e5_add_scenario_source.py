"""add scenario source

Revision ID: 584191e291e5
Revises: cecd1e4927c8
Create Date: 2026-09-01 13:11:49.245535

NLM "Add Test Case" feature: `Scenario.source` distinguishes a Scenario
created through the normal Discovery -> Journey -> Scenario pipeline from one
created ad hoc via a user's plain-English request — the frontend labels only
the latter "NLM Test Case" (`TestSuiteTab.tsx`).

Every pre-existing `Scenario` row gets `source='discovery'` via the column's
`server_default` — no existing test case is relabeled by this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "584191e291e5"
down_revision: str | None = "cecd1e4927c8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scenario",
        sa.Column(
            "source",
            sqlmodel.sql.sqltypes.AutoString(),
            server_default="discovery",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("scenario", "source")
