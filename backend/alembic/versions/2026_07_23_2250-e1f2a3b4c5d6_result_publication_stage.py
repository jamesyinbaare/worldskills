"""Add stage_id to result publications for stage-scoped release."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "result_publications",
        sa.Column("stage_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_result_publications_stage_id",
        "result_publications",
        ["stage_id"],
    )
    op.create_foreign_key(
        "fk_result_publications_stage_id",
        "result_publications",
        "stages",
        ["stage_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_result_publications_stage_id",
        "result_publications",
        type_="foreignkey",
    )
    op.drop_index("ix_result_publications_stage_id", table_name="result_publications")
    op.drop_column("result_publications", "stage_id")
