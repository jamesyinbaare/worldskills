"""Drop unique constraint on institutions.name — only code is unique.

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-07-21 16:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_institutions_name", "institutions", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_institutions_name", "institutions", ["name"])
