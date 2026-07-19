"""US-NOT-01: notification templates, preferences, outbox delivery fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notification_outbox", sa.Column("event_key", sa.String(length=128), nullable=True))
    op.create_index("ix_notification_outbox_event_key", "notification_outbox", ["event_key"])
    op.add_column("notification_outbox", sa.Column("channel", sa.String(length=32), nullable=True))
    op.add_column("notification_outbox", sa.Column("language", sa.String(length=16), nullable=True))
    op.add_column("notification_outbox", sa.Column("rendered_subject", sa.String(length=512), nullable=True))
    op.add_column("notification_outbox", sa.Column("rendered_body", sa.Text(), nullable=True))
    op.add_column(
        "notification_outbox",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="QUEUED"),
    )
    op.add_column("notification_outbox", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("notification_outbox", sa.Column("dedupe_key", sa.String(length=128), nullable=True))
    op.create_index("ix_notification_outbox_dedupe_key", "notification_outbox", ["dedupe_key"])

    op.create_table(
        "notification_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("essential", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", "language", name="uq_notification_templates_event_language"),
    )
    op.create_index("ix_notification_templates_event_key", "notification_templates", ["event_key"])

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("preferred_channel", sa.String(length=32), nullable=False),
        sa.Column("fallback_channel", sa.String(length=32), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("whatsapp", sa.String(length=32), nullable=True),
        sa.Column("opt_out_non_essential", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_preferences_user_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")
    op.drop_index("ix_notification_templates_event_key", table_name="notification_templates")
    op.drop_table("notification_templates")

    op.drop_index("ix_notification_outbox_dedupe_key", table_name="notification_outbox")
    op.drop_column("notification_outbox", "dedupe_key")
    op.drop_column("notification_outbox", "error")
    op.drop_column("notification_outbox", "status")
    op.drop_column("notification_outbox", "rendered_body")
    op.drop_column("notification_outbox", "rendered_subject")
    op.drop_column("notification_outbox", "language")
    op.drop_column("notification_outbox", "channel")
    op.drop_index("ix_notification_outbox_event_key", table_name="notification_outbox")
    op.drop_column("notification_outbox", "event_key")
