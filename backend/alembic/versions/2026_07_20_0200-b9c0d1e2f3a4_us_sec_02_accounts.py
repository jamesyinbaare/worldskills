"""US-SEC-02: user account provisioning fields + invite notification template."""

from datetime import datetime
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("users", sa.Column("invite_token_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("invite_expires_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("created_by_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_created_by_id_users"),
        "users",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_users_created_by_id"), "users", ["created_by_id"])

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO notification_templates (id, event_key, language, subject, body, essential, created_at)
            VALUES (:id, :event_key, :language, :subject, :body, :essential, :created_at)
            ON CONFLICT (event_key, language) DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "event_key": "USER_ACCOUNT_INVITE",
            "language": "en",
            "subject": "Your SCMS account invitation",
            "body": (
                "Hello {{fullName}},\n\n"
                "You have been invited to the Skills Competition Management System.\n"
                "Set your password using this link (expires {{expiresAt}}):\n"
                "{{inviteUrl}}\n"
            ),
            "essential": True,
            "created_at": datetime.utcnow(),
        },
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM notification_templates WHERE event_key = 'USER_ACCOUNT_INVITE' AND language = 'en'"
        )
    )
    op.drop_index(op.f("ix_users_created_by_id"), table_name="users")
    op.drop_constraint(op.f("fk_users_created_by_id_users"), "users", type_="foreignkey")
    op.drop_column("users", "created_by_id")
    op.drop_column("users", "invite_expires_at")
    op.drop_column("users", "invite_token_hash")
    op.drop_column("users", "must_change_password")
