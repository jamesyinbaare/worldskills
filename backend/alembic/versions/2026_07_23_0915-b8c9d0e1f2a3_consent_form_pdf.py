"""Add signed consent form storage fields on competitors.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-23 09:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("consent_form_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("consent_form_uploaded_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("consent_form_sha256", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("competitors", "consent_form_sha256")
    op.drop_column("competitors", "consent_form_uploaded_at")
    op.drop_column("competitors", "consent_form_key")
