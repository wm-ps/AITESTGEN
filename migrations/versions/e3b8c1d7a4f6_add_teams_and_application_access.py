"""add teams, team members and application access

Revision ID: e3b8c1d7a4f6
Revises: d1a7f3c9e5b2
Create Date: 2026-11-23 00:30:00.000000

Team workspaces. Everything that exists today moves into one "Default" team
per organisation so behaviour is unchanged on deploy:

* every user becomes a member of the Default team;
* every application moves into it;
* every non-admin user keeps the access they had: an old member becomes a
  `contributor` and an old viewer a `viewer` on every application (super
  admins need no rows, they are implicitly admin on every team application);
* the organisation-level `viewer` role is retired, folded into
  `standard_user` plus the viewer grants above.

Applications added after this are private to their adder and the team admins
until shared. Existing applications have no recorded creator.

ponytail: the downgrade restores the old single-organisation shape — team
structure and per-application grants are dropped (a user whose only grants were
viewer grants is turned back into a `viewer`); it is not a lossless round trip.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3b8c1d7a4f6"
down_revision: str | None = "d1a7f3c9e5b2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("external_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_team_external_id"), "team", ["external_id"], unique=True)
    op.create_index(op.f("ix_team_organization_id"), "team", ["organization_id"], unique=False)
    op.create_index("ux_team_org_lower_name", "team", ["organization_id", sa.text("lower(name)")], unique=True)

    op.create_table(
        "team_member",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["team.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["platform_user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member_team_user"),
    )
    op.create_index(op.f("ix_team_member_team_id"), "team_member", ["team_id"], unique=False)
    op.create_index(op.f("ix_team_member_user_id"), "team_member", ["user_id"], unique=False)

    op.add_column("application", sa.Column("team_id", sa.UUID(), nullable=True))
    op.add_column("application", sa.Column("created_by_id", sa.UUID(), nullable=True))
    op.add_column("application", sa.Column("created_by_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_foreign_key("fk_application_team_id", "application", "team", ["team_id"], ["id"])
    op.create_foreign_key(
        "fk_application_created_by_id", "application", "platform_user", ["created_by_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(op.f("ix_application_team_id"), "application", ["team_id"], unique=False)

    op.create_table(
        "application_member",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("granted_by_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["platform_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["platform_user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "user_id", name="uq_application_member_app_user"),
    )
    op.create_index(op.f("ix_application_member_application_id"), "application_member", ["application_id"])
    op.create_index(op.f("ix_application_member_user_id"), "application_member", ["user_id"])

    # Backfill — every statement is safe to repeat.
    op.execute(
        """
        INSERT INTO team (organization_id, external_id, name, is_default, created_at)
        SELECT o.id, gen_random_uuid(), 'Default', true, now() FROM organization o
        WHERE NOT EXISTS (SELECT 1 FROM team t WHERE t.organization_id = o.id AND t.is_default)
        """
    )
    op.execute(
        """
        INSERT INTO team_member (team_id, user_id, role, created_at)
        SELECT t.id, u.id, 'team_member', now()
        FROM platform_user u JOIN team t ON t.organization_id = u.organization_id AND t.is_default
        ON CONFLICT (team_id, user_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE application a SET team_id = t.id
        FROM team t WHERE t.organization_id = a.organization_id AND t.is_default AND a.team_id IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO application_member (application_id, user_id, role, created_at)
        SELECT a.id, u.id, CASE u.role WHEN 'viewer' THEN 'viewer' ELSE 'contributor' END, now()
        FROM application a JOIN platform_user u ON u.organization_id = a.organization_id
        WHERE u.role IN ('standard_user', 'viewer')
        ON CONFLICT (application_id, user_id) DO NOTHING
        """
    )
    # The organisation-level viewer role is retired (its read-only rights are
    # the viewer grants above); a pending viewer invite becomes a plain user.
    op.execute("UPDATE platform_user SET role = 'standard_user' WHERE role = 'viewer'")
    op.execute("UPDATE invite SET role = 'standard_user' WHERE role = 'viewer'")


def downgrade() -> None:
    op.execute(
        """
        UPDATE platform_user u SET role = 'viewer'
        WHERE u.role = 'standard_user'
          AND EXISTS (SELECT 1 FROM application_member m WHERE m.user_id = u.id)
          AND NOT EXISTS (SELECT 1 FROM application_member m WHERE m.user_id = u.id AND m.role <> 'viewer')
        """
    )
    op.drop_table("application_member")
    op.drop_index(op.f("ix_application_team_id"), table_name="application")
    op.drop_constraint("fk_application_created_by_id", "application", type_="foreignkey")
    op.drop_constraint("fk_application_team_id", "application", type_="foreignkey")
    op.drop_column("application", "created_by_name")
    op.drop_column("application", "created_by_id")
    op.drop_column("application", "team_id")
    op.drop_table("team_member")
    op.drop_index("ux_team_org_lower_name", table_name="team")
    op.drop_table("team")
