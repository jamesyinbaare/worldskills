"""US-ASM-01: rubric on marking schemes, score fields, submission anon/total."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("marking_schemes", sa.Column("rubric", sa.JSON(), nullable=True))

    op.add_column("submissions", sa.Column("anon_code", sa.String(length=32), nullable=True))
    op.create_index("ix_submissions_anon_code", "submissions", ["anon_code"])
    op.add_column("submissions", sa.Column("score_total", sa.Integer(), nullable=True))

    op.add_column(
        "scores",
        sa.Column("score_type", sa.String(length=32), nullable=False, server_default="MEASUREMENT"),
    )
    op.add_column("scores", sa.Column("standardised", sa.Integer(), nullable=True))
    op.add_column("scores", sa.Column("penalty", sa.Integer(), nullable=True))
    op.add_column("scores", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column("scores", sa.Column("judge_id", sa.UUID(), nullable=True))
    op.create_index("ix_scores_judge_id", "scores", ["judge_id"])
    op.create_foreign_key(
        "fk_scores_judge_id_users",
        "scores",
        "users",
        ["judge_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "scores",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
    )
    op.add_column(
        "scores",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.add_column(
        "scores",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_unique_constraint(
        "uq_scores_submission_criterion_assessor_type",
        "scores",
        ["submission_id", "criterion_id", "assessor_id", "score_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_scores_submission_criterion_assessor_type", "scores", type_="unique")
    op.drop_column("scores", "updated_at")
    op.drop_column("scores", "created_at")
    op.drop_column("scores", "status")
    op.drop_constraint("fk_scores_judge_id_users", "scores", type_="foreignkey")
    op.drop_index("ix_scores_judge_id", table_name="scores")
    op.drop_column("scores", "judge_id")
    op.drop_column("scores", "comment")
    op.drop_column("scores", "penalty")
    op.drop_column("scores", "standardised")
    op.drop_column("scores", "score_type")

    op.drop_column("submissions", "score_total")
    op.drop_index("ix_submissions_anon_code", table_name="submissions")
    op.drop_column("submissions", "anon_code")

    op.drop_column("marking_schemes", "rubric")
