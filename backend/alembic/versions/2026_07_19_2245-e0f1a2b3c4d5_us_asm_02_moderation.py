"""US-ASM-02: moderation_flags table for judgement standardisation."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moderation_flags",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("criterion_id", sa.String(length=64), nullable=False),
        sa.Column("spread", sa.Integer(), nullable=True),
        sa.Column("raw_marks", sa.JSON(), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("method", sa.String(length=32), nullable=True),
        sa.Column("standardised_value", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("moderator_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "criterion_id", name="uq_moderation_flags_submission_criterion"),
    )
    op.create_index("ix_moderation_flags_submission_id", "moderation_flags", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_moderation_flags_submission_id", table_name="moderation_flags")
    op.drop_table("moderation_flags")
