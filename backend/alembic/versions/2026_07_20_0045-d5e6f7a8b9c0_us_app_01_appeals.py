"""US-APP-01: appeals config, appeal cases, competitor DQ fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "appeals_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("appeal_window_opens_at", sa.DateTime(), nullable=False),
        sa.Column("appeal_window_closes_at", sa.DateTime(), nullable=False),
        sa.Column("dq_reasons", sa.JSON(), nullable=False),
        sa.Column("tie_break_rules", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id"),
    )
    op.create_index("ix_appeals_configs_cycle_id", "appeals_configs", ["cycle_id"])

    op.create_table(
        "appeal_cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("stage_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("officer_id", sa.UUID(), nullable=True),
        sa.Column("ruling_outcome", sa.String(length=32), nullable=True),
        sa.Column("ruling_reason", sa.Text(), nullable=True),
        sa.Column("remedy", sa.String(length=32), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("ruled_at", sa.DateTime(), nullable=True),
        sa.Column("lodged_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lodged_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["officer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["stage_id"], ["stages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appeal_cases_cycle_id", "appeal_cases", ["cycle_id"])
    op.create_index("ix_appeal_cases_competitor_id", "appeal_cases", ["competitor_id"])
    op.create_index("ix_appeal_cases_stage_id", "appeal_cases", ["stage_id"])
    op.create_index("ix_appeal_cases_officer_id", "appeal_cases", ["officer_id"])

    op.add_column("competitors", sa.Column("dq_reason", sa.String(length=64), nullable=True))
    op.add_column("competitors", sa.Column("dq_at", sa.DateTime(), nullable=True))
    op.add_column("competitors", sa.Column("dq_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_competitors_dq_by_users",
        "competitors",
        "users",
        ["dq_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_competitors_dq_by_users", "competitors", type_="foreignkey")
    op.drop_column("competitors", "dq_by")
    op.drop_column("competitors", "dq_at")
    op.drop_column("competitors", "dq_reason")

    op.drop_index("ix_appeal_cases_officer_id", table_name="appeal_cases")
    op.drop_index("ix_appeal_cases_stage_id", table_name="appeal_cases")
    op.drop_index("ix_appeal_cases_competitor_id", table_name="appeal_cases")
    op.drop_index("ix_appeal_cases_cycle_id", table_name="appeal_cases")
    op.drop_table("appeal_cases")

    op.drop_index("ix_appeals_configs_cycle_id", table_name="appeals_configs")
    op.drop_table("appeals_configs")
