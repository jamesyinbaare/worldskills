"""US-SHL-01: shortlists and shortlist_entries."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shortlists",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("stage_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="PROVISIONAL"),
        sa.Column("is_final_stage", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by", sa.UUID(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stage_id"], ["stages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shortlists_cycle_id", "shortlists", ["cycle_id"])
    op.create_index("ix_shortlists_stage_id", "shortlists", ["stage_id"])
    op.create_index("ix_shortlists_skill_id", "shortlists", ["skill_id"])

    op.create_table(
        "shortlist_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("shortlist_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("zone_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("advanced", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shortlist_id"], ["shortlists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shortlist_entries_shortlist_id", "shortlist_entries", ["shortlist_id"])
    op.create_index("ix_shortlist_entries_competitor_id", "shortlist_entries", ["competitor_id"])
    op.create_index("ix_shortlist_entries_zone_id", "shortlist_entries", ["zone_id"])


def downgrade() -> None:
    op.drop_index("ix_shortlist_entries_zone_id", table_name="shortlist_entries")
    op.drop_index("ix_shortlist_entries_competitor_id", table_name="shortlist_entries")
    op.drop_index("ix_shortlist_entries_shortlist_id", table_name="shortlist_entries")
    op.drop_table("shortlist_entries")
    op.drop_index("ix_shortlists_skill_id", table_name="shortlists")
    op.drop_index("ix_shortlists_stage_id", table_name="shortlists")
    op.drop_index("ix_shortlists_cycle_id", table_name="shortlists")
    op.drop_table("shortlists")
