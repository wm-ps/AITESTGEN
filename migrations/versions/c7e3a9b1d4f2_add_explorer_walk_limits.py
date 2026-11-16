"""Explorer limits: steps per scenario / full-flow scenario, and when a walk
gives up (same screen in a row, visits to one screen, button retries).

Revision ID: c7e3a9b1d4f2
Revises: d8b4f1a2c6e3
"""

import sqlalchemy as sa
from alembic import op

revision: str = "c7e3a9b1d4f2"
down_revision: str | None = "d8b4f1a2c6e3"
branch_labels = None
depends_on = None

# Defaults are the values Explorer used before these were settings.
COLUMNS = {
    "steps_per_scenario": 20,
    "steps_per_journey": 40,
    "same_screen_repeats": 3,
    "screen_visits": 4,
    "press_retries": 2,
}


def upgrade() -> None:
    for name, default in COLUMNS.items():
        op.add_column(
            "explorer_settings",
            sa.Column(name, sa.Integer(), nullable=False, server_default=str(default)),
        )


def downgrade() -> None:
    for name in COLUMNS:
        op.drop_column("explorer_settings", name)
