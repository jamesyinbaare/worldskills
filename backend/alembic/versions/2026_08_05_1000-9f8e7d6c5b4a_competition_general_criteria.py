"""Add competition general criteria document columns.

Revision ID: 9f8e7d6c5b4a
Revises: f6a7b8c9d0e2
Create Date: 2026-08-05 10:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f8e7d6c5b4a"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitions",
        sa.Column("general_criteria_object_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "competitions",
        sa.Column("general_criteria_file_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "competitions",
        sa.Column("general_criteria_content_type", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "competitions",
        sa.Column("general_criteria_scan_status", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("competitions", "general_criteria_scan_status")
    op.drop_column("competitions", "general_criteria_content_type")
    op.drop_column("competitions", "general_criteria_file_name")
    op.drop_column("competitions", "general_criteria_object_key")
