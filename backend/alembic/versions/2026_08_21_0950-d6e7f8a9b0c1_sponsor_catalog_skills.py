"""Link sponsors to catalog skill areas (optional many-to-many).

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-21 09:50:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sponsor_catalog_skills",
        sa.Column("sponsor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("catalog_skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sponsor_id"],
            ["sponsors.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_skill_id"],
            ["catalog_skills.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sponsor_id", "catalog_skill_id"),
    )


def downgrade() -> None:
    op.drop_table("sponsor_catalog_skills")
