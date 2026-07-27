"""Add skill-area criteria document columns.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-23 16:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("criteria_object_key", sa.String(length=512), nullable=True))
    op.add_column("skills", sa.Column("criteria_file_name", sa.String(length=255), nullable=True))
    op.add_column("skills", sa.Column("criteria_content_type", sa.String(length=120), nullable=True))
    op.add_column("skills", sa.Column("criteria_scan_status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("skills", "criteria_scan_status")
    op.drop_column("skills", "criteria_content_type")
    op.drop_column("skills", "criteria_file_name")
    op.drop_column("skills", "criteria_object_key")
