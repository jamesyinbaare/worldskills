"""Add passport fields to competitors.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-21 21:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("has_passport", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "competitors",
        sa.Column("passport_number", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("competitors", "passport_number")
    op.drop_column("competitors", "has_passport")
