"""Unique users.phone_number (canonical local Ghana form)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Clear duplicate non-null phones, keeping the earliest row per normalized digits.
    conn.execute(
        sa.text(
            """
            WITH ranked AS (
              SELECT
                id,
                regexp_replace(phone_number, '\\D', '', 'g') AS digits,
                ROW_NUMBER() OVER (
                  PARTITION BY regexp_replace(phone_number, '\\D', '', 'g')
                  ORDER BY created_at ASC NULLS LAST, id ASC
                ) AS rn
              FROM users
              WHERE phone_number IS NOT NULL
                AND btrim(phone_number) <> ''
            )
            UPDATE users u
            SET phone_number = NULL
            FROM ranked r
            WHERE u.id = r.id
              AND r.rn > 1
            """
        )
    )
    op.drop_index(op.f("ix_users_phone_number"), table_name="users")
    op.create_index(
        op.f("ix_users_phone_number"),
        "users",
        ["phone_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_users_phone_number"), table_name="users")
    op.create_index(
        op.f("ix_users_phone_number"),
        "users",
        ["phone_number"],
        unique=False,
    )
