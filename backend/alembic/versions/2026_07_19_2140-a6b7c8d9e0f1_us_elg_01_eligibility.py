"""US-ELG-01: eligibility columns, open-category flag on age rules."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "age_rules",
        sa.Column("open_category_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("skills", sa.Column("eligibility_rules", sa.JSON(), nullable=True))

    op.add_column("competitors", sa.Column("nationality", sa.String(length=8), nullable=True))
    op.add_column(
        "competitors",
        sa.Column("enrolment_attested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("competitors", sa.Column("eligibility_status", sa.String(length=32), nullable=True))
    op.add_column(
        "competitors",
        sa.Column("eligibility_failed_rules", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column("competitors", sa.Column("eligibility_category", sa.String(length=32), nullable=True))
    op.add_column("competitors", sa.Column("eligibility_override_reason", sa.Text(), nullable=True))
    op.add_column("competitors", sa.Column("eligibility_override_at", sa.DateTime(), nullable=True))
    op.add_column("competitors", sa.Column("eligibility_override_by", sa.UUID(), nullable=True))


def downgrade() -> None:
    op.drop_column("competitors", "eligibility_override_by")
    op.drop_column("competitors", "eligibility_override_at")
    op.drop_column("competitors", "eligibility_override_reason")
    op.drop_column("competitors", "eligibility_category")
    op.drop_column("competitors", "eligibility_failed_rules")
    op.drop_column("competitors", "eligibility_status")
    op.drop_column("competitors", "enrolment_attested")
    op.drop_column("competitors", "nationality")
    op.drop_column("skills", "eligibility_rules")
    op.drop_column("age_rules", "open_category_enabled")
