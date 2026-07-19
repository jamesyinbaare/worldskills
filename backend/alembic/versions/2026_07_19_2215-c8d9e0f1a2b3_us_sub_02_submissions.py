"""US-SUB-02: submission lifecycle fields, artefacts, stage submission_rules."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("competitors", sa.Column("user_id", sa.UUID(), nullable=True))
    op.create_index("ix_competitors_user_id", "competitors", ["user_id"])
    op.create_foreign_key(
        "fk_competitors_user_id_users",
        "competitors",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("stages", sa.Column("submission_rules", sa.JSON(), nullable=True))

    op.add_column("submissions", sa.Column("stage_id", sa.UUID(), nullable=True))
    op.create_index("ix_submissions_stage_id", "submissions", ["stage_id"])
    op.create_foreign_key(
        "fk_submissions_stage_id_stages",
        "submissions",
        "stages",
        ["stage_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column("submissions", sa.Column("deadline_at", sa.DateTime(), nullable=True))
    op.add_column("submissions", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    op.add_column(
        "submissions",
        sa.Column("late", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("submissions", sa.Column("content_hash", sa.String(length=128), nullable=True))
    op.add_column("submissions", sa.Column("timed_started_at", sa.DateTime(), nullable=True))
    op.add_column("submissions", sa.Column("timed_expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "submissions",
        sa.Column("upload_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("submissions", sa.Column("receipt", sa.String(length=64), nullable=True))
    # Change default state semantics: existing rows may be ACCEPTED stubs
    op.alter_column("submissions", "state", server_default="OPEN")
    op.create_unique_constraint(
        "uq_submissions_competitor_stage", "submissions", ["competitor_id", "stage_id"]
    )

    op.create_table(
        "artefacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("deliverable_code", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("sha256", sa.String(length=128), nullable=True),
        sa.Column("scan_status", sa.String(length=32), nullable=False),
        sa.Column("quarantined", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("upload_id", sa.String(length=64), nullable=True),
        sa.Column("total_size", sa.Integer(), nullable=True),
        sa.Column("received_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_id"),
    )
    op.create_index("ix_artefacts_submission_id", "artefacts", ["submission_id"])
    op.create_index("ix_artefacts_upload_id", "artefacts", ["upload_id"])


def downgrade() -> None:
    op.drop_index("ix_artefacts_upload_id", table_name="artefacts")
    op.drop_index("ix_artefacts_submission_id", table_name="artefacts")
    op.drop_table("artefacts")

    op.drop_constraint("uq_submissions_competitor_stage", "submissions", type_="unique")
    op.alter_column("submissions", "state", server_default="ACCEPTED")
    op.drop_column("submissions", "receipt")
    op.drop_column("submissions", "upload_locked")
    op.drop_column("submissions", "timed_expires_at")
    op.drop_column("submissions", "timed_started_at")
    op.drop_column("submissions", "content_hash")
    op.drop_column("submissions", "late")
    op.drop_column("submissions", "submitted_at")
    op.drop_column("submissions", "deadline_at")
    op.drop_constraint("fk_submissions_stage_id_stages", "submissions", type_="foreignkey")
    op.drop_index("ix_submissions_stage_id", table_name="submissions")
    op.drop_column("submissions", "stage_id")

    op.drop_column("stages", "submission_rules")

    op.drop_constraint("fk_competitors_user_id_users", "competitors", type_="foreignkey")
    op.drop_index("ix_competitors_user_id", table_name="competitors")
    op.drop_column("competitors", "user_id")
