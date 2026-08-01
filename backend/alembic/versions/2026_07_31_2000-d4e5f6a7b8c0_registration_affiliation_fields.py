"""Registration affiliation, ID kind, and heard-about fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c0"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("affiliation_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("organization_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("organization_city", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("organization_phone", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("organization_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("id_document_kind", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("other_id_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "competitors",
        sa.Column("heard_about", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("competitors", "heard_about")
    op.drop_column("competitors", "other_id_type")
    op.drop_column("competitors", "id_document_kind")
    op.drop_column("competitors", "organization_email")
    op.drop_column("competitors", "organization_phone")
    op.drop_column("competitors", "organization_city")
    op.drop_column("competitors", "organization_name")
    op.drop_column("competitors", "affiliation_type")
