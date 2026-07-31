"""SMS deliveries + exercise availability_notified_at."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a7"
down_revision: Union[str, Sequence[str], None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exercises",
        sa.Column("availability_notified_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "sms_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("competition_id", sa.UUID(), nullable=True),
        sa.Column("stage_id", sa.UUID(), nullable=True),
        sa.Column("submission_id", sa.UUID(), nullable=True),
        sa.Column("recipient_role", sa.String(length=32), nullable=False),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("msisdn", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_response", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.Column("retried_from_id", sa.UUID(), nullable=True),
        sa.Column("triggered_by_user_id", sa.UUID(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name=op.f("fk_sms_deliveries_competitor_id_competitors"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sms_deliveries_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competitions.id"],
            name=op.f("fk_sms_deliveries_competition_id_competitions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["stages.id"],
            name=op.f("fk_sms_deliveries_stage_id_stages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.id"],
            name=op.f("fk_sms_deliveries_submission_id_submissions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["retried_from_id"],
            ["sms_deliveries.id"],
            name=op.f("fk_sms_deliveries_retried_from_id_sms_deliveries"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            name=op.f("fk_sms_deliveries_triggered_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sms_deliveries")),
    )
    op.create_index(op.f("ix_sms_deliveries_competitor_id"), "sms_deliveries", ["competitor_id"])
    op.create_index(op.f("ix_sms_deliveries_user_id"), "sms_deliveries", ["user_id"])
    op.create_index(op.f("ix_sms_deliveries_competition_id"), "sms_deliveries", ["competition_id"])
    op.create_index(op.f("ix_sms_deliveries_stage_id"), "sms_deliveries", ["stage_id"])
    op.create_index(op.f("ix_sms_deliveries_submission_id"), "sms_deliveries", ["submission_id"])
    op.create_index(op.f("ix_sms_deliveries_message_type"), "sms_deliveries", ["message_type"])
    op.create_index(op.f("ix_sms_deliveries_status"), "sms_deliveries", ["status"])
    op.create_index(op.f("ix_sms_deliveries_dedupe_key"), "sms_deliveries", ["dedupe_key"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sms_deliveries_dedupe_key"), table_name="sms_deliveries")
    op.drop_index(op.f("ix_sms_deliveries_status"), table_name="sms_deliveries")
    op.drop_index(op.f("ix_sms_deliveries_message_type"), table_name="sms_deliveries")
    op.drop_index(op.f("ix_sms_deliveries_submission_id"), table_name="sms_deliveries")
    op.drop_index(op.f("ix_sms_deliveries_stage_id"), table_name="sms_deliveries")
    op.drop_index(op.f("ix_sms_deliveries_competition_id"), table_name="sms_deliveries")
    op.drop_index(op.f("ix_sms_deliveries_user_id"), table_name="sms_deliveries")
    op.drop_index(op.f("ix_sms_deliveries_competitor_id"), table_name="sms_deliveries")
    op.drop_table("sms_deliveries")
    op.drop_column("exercises", "availability_notified_at")
