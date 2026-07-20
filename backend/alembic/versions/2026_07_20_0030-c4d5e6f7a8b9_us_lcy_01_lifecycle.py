"""US-LCY-01: lifecycle config + competitor withdrawal/substitution fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lifecycle_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("substitution_cutoff_at", sa.DateTime(), nullable=False),
        sa.Column("waitlist_order", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id"),
    )
    op.create_index("ix_lifecycle_configs_cycle_id", "lifecycle_configs", ["cycle_id"])

    op.add_column("competitors", sa.Column("withdrawn_at", sa.DateTime(), nullable=True))
    op.add_column("competitors", sa.Column("withdrawn_reason", sa.Text(), nullable=True))
    op.add_column("competitors", sa.Column("withdrawn_by", sa.UUID(), nullable=True))
    op.add_column("competitors", sa.Column("substitutes_id", sa.UUID(), nullable=True))
    op.add_column("competitors", sa.Column("substituted_by_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_competitors_withdrawn_by_users",
        "competitors",
        "users",
        ["withdrawn_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_competitors_substitutes_id",
        "competitors",
        "competitors",
        ["substitutes_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_competitors_substituted_by_id",
        "competitors",
        "competitors",
        ["substituted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_competitors_substitutes_id", "competitors", ["substitutes_id"])
    op.create_index("ix_competitors_substituted_by_id", "competitors", ["substituted_by_id"])


def downgrade() -> None:
    op.drop_index("ix_competitors_substituted_by_id", table_name="competitors")
    op.drop_index("ix_competitors_substitutes_id", table_name="competitors")
    op.drop_constraint("fk_competitors_substituted_by_id", "competitors", type_="foreignkey")
    op.drop_constraint("fk_competitors_substitutes_id", "competitors", type_="foreignkey")
    op.drop_constraint("fk_competitors_withdrawn_by_users", "competitors", type_="foreignkey")
    op.drop_column("competitors", "substituted_by_id")
    op.drop_column("competitors", "substitutes_id")
    op.drop_column("competitors", "withdrawn_by")
    op.drop_column("competitors", "withdrawn_reason")
    op.drop_column("competitors", "withdrawn_at")

    op.drop_index("ix_lifecycle_configs_cycle_id", table_name="lifecycle_configs")
    op.drop_table("lifecycle_configs")
