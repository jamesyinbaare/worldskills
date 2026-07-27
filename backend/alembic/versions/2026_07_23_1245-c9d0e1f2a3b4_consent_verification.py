"""Add admin consent verification fields on competitors.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-23 12:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("consent_verification_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("consent_verified_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("consent_verified_by", sa.UUID(), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("consent_verification_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_competitors_consent_verified_by_users",
        "competitors",
        "users",
        ["consent_verified_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_competitors_consent_verified_by_users",
        "competitors",
        type_="foreignkey",
    )
    op.drop_column("competitors", "consent_verification_reason")
    op.drop_column("competitors", "consent_verified_by")
    op.drop_column("competitors", "consent_verified_at")
    op.drop_column("competitors", "consent_verification_status")
