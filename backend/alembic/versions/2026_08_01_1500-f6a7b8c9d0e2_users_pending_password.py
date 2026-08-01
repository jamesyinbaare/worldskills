"""Add pending password reset columns on users."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e2"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pending_password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("pending_password_expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "pending_password_expires_at")
    op.drop_column("users", "pending_password_hash")
