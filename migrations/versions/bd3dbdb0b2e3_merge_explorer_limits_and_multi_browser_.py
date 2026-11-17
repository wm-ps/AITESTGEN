"""merge explorer limits and multi-browser runs

Revision ID: bd3dbdb0b2e3
Revises: f1b6d4e8a3c5, e2c6d4a8f1b7
Create Date: 2026-11-17 22:25:52.833459

Two branches each added a migration (Explorer limits; multi-browser run
counts). No schema change here: it only joins the two heads.
"""

from collections.abc import Sequence

revision: str = "bd3dbdb0b2e3"
down_revision: str | Sequence[str] | None = ("f1b6d4e8a3c5", "e2c6d4a8f1b7")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
