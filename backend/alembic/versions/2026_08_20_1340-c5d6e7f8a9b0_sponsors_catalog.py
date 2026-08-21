"""Create sponsors catalog table.

Revision ID: c5d6e7f8a9b0
Revises: 9f8e7d6c5b4a
Create Date: 2026-08-20 13:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "9f8e7d6c5b4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sponsors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("logo_object_key", sa.String(length=512), nullable=True),
        sa.Column("logo_file_name", sa.String(length=255), nullable=True),
        sa.Column("logo_content_type", sa.String(length=120), nullable=True),
        sa.Column("logo_scan_status", sa.String(length=32), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("sponsors")
