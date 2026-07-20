"""US-PUB-01: public portal config for field allow-list and rate limits."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "public_portal_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("public_fields", sa.JSON(), nullable=False),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("max_page_size", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id"),
    )
    op.create_index("ix_public_portal_configs_cycle_id", "public_portal_configs", ["cycle_id"])


def downgrade() -> None:
    op.drop_index("ix_public_portal_configs_cycle_id", table_name="public_portal_configs")
    op.drop_table("public_portal_configs")
