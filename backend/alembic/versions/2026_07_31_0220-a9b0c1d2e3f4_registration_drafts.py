"""Allow draft competitor registration rows (nullable skill/zone/ref)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "competitors",
        "skill_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.alter_column(
        "competitors",
        "zone_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.alter_column(
        "competitors",
        "ref_no",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.add_column(
        "competitors",
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.execute(sa.text("UPDATE competitors SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))
    op.alter_column("competitors", "updated_at", nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))


def downgrade() -> None:
    op.drop_column("competitors", "updated_at")
    # Non-draft rows must already have skill/zone/ref; drafts would block NOT NULL.
    op.execute(sa.text("DELETE FROM competitors WHERE status = 'DRAFT'"))
    op.alter_column(
        "competitors",
        "ref_no",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.alter_column(
        "competitors",
        "zone_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.alter_column(
        "competitors",
        "skill_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
