"""US-AUD-01: DSAR jobs table for access/erasure/withdraw."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dsar_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("request_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column("export_payload", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dsar_jobs_subject_id", "dsar_jobs", ["subject_id"])


def downgrade() -> None:
    op.drop_index("ix_dsar_jobs_subject_id", table_name="dsar_jobs")
    op.drop_table("dsar_jobs")
