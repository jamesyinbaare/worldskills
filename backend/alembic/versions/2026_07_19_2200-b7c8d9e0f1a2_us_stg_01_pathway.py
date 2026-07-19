"""US-STG-01: stage pathway fields — branch, quota_by_zone, unique skill order."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stages", sa.Column("quota_by_zone", sa.JSON(), nullable=True))
    op.add_column("stages", sa.Column("branch", sa.JSON(), nullable=True))
    op.create_unique_constraint("uq_stages_skill_id_order", "stages", ["skill_id", "order"])


def downgrade() -> None:
    op.drop_constraint("uq_stages_skill_id_order", "stages", type_="unique")
    op.drop_column("stages", "branch")
    op.drop_column("stages", "quota_by_zone")
