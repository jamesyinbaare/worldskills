"""US-INS-01: nomination limits, nominations, membership, notification outbox."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    nominationstatus = postgresql.ENUM(
        "PENDING_REVIEW", "APPROVED", "REJECTED", name="nominationstatus", create_type=False
    )
    nominationstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "institution_cycle_memberships",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=False),
        sa.Column("zone_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_institution_cycle_memberships_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_institution_cycle_memberships_institution_id_institutions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["zone_id"], ["zones.id"], name=op.f("fk_institution_cycle_memberships_zone_id_zones"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institution_cycle_memberships")),
        sa.UniqueConstraint("cycle_id", "institution_id", name="uq_institution_cycle_memberships_cycle_institution"),
    )
    op.create_index(
        op.f("ix_institution_cycle_memberships_cycle_id"), "institution_cycle_memberships", ["cycle_id"], unique=False
    )
    op.create_index(
        op.f("ix_institution_cycle_memberships_institution_id"),
        "institution_cycle_memberships",
        ["institution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_institution_cycle_memberships_zone_id"), "institution_cycle_memberships", ["zone_id"], unique=False
    )

    op.create_table(
        "nomination_limits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("max_nominations", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_nomination_limits_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_nomination_limits_institution_id_institutions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_nomination_limits_skill_id_skills"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nomination_limits")),
        sa.UniqueConstraint("cycle_id", "institution_id", "skill_id", name="uq_nomination_limits_cycle_institution_skill"),
    )
    op.create_index(op.f("ix_nomination_limits_cycle_id"), "nomination_limits", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_nomination_limits_institution_id"), "nomination_limits", ["institution_id"], unique=False)
    op.create_index(op.f("ix_nomination_limits_skill_id"), "nomination_limits", ["skill_id"], unique=False)

    op.create_table(
        "nominations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("competitor_ref", sa.String(length=64), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING_REVIEW", "APPROVED", "REJECTED", name="nominationstatus", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_nominations_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_nominations_institution_id_institutions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_nominations_skill_id_skills"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name=op.f("fk_nominations_competitor_id_competitors"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nominations")),
    )
    op.create_index(op.f("ix_nominations_cycle_id"), "nominations", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_nominations_institution_id"), "nominations", ["institution_id"], unique=False)
    op.create_index(op.f("ix_nominations_skill_id"), "nominations", ["skill_id"], unique=False)
    op.create_index(op.f("ix_nominations_competitor_id"), "nominations", ["competitor_id"], unique=False)

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=True),
        sa.Column("recipient_role", sa.String(length=64), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=True),
        sa.Column("template", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
    )
    op.create_index(op.f("ix_notification_outbox_cycle_id"), "notification_outbox", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_notification_outbox_recipient_id"), "notification_outbox", ["recipient_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_outbox_recipient_id"), table_name="notification_outbox")
    op.drop_index(op.f("ix_notification_outbox_cycle_id"), table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index(op.f("ix_nominations_competitor_id"), table_name="nominations")
    op.drop_index(op.f("ix_nominations_skill_id"), table_name="nominations")
    op.drop_index(op.f("ix_nominations_institution_id"), table_name="nominations")
    op.drop_index(op.f("ix_nominations_cycle_id"), table_name="nominations")
    op.drop_table("nominations")
    op.drop_index(op.f("ix_nomination_limits_skill_id"), table_name="nomination_limits")
    op.drop_index(op.f("ix_nomination_limits_institution_id"), table_name="nomination_limits")
    op.drop_index(op.f("ix_nomination_limits_cycle_id"), table_name="nomination_limits")
    op.drop_table("nomination_limits")
    op.drop_index(op.f("ix_institution_cycle_memberships_zone_id"), table_name="institution_cycle_memberships")
    op.drop_index(op.f("ix_institution_cycle_memberships_institution_id"), table_name="institution_cycle_memberships")
    op.drop_index(op.f("ix_institution_cycle_memberships_cycle_id"), table_name="institution_cycle_memberships")
    op.drop_table("institution_cycle_memberships")
    sa.Enum(name="nominationstatus").drop(op.get_bind(), checkfirst=True)
