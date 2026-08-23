"""Global expert catalog skill areas; nullable assignment zone.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-23 11:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expert_skill_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("catalog_skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["catalog_skill_id"], ["catalog_skills.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["expert_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "expert_id",
            "catalog_skill_id",
            name="uq_expert_skill_areas_expert_catalog_skill",
        ),
    )
    op.create_index(
        op.f("ix_expert_skill_areas_catalog_skill_id"),
        "expert_skill_areas",
        ["catalog_skill_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expert_skill_areas_expert_id"),
        "expert_skill_areas",
        ["expert_id"],
        unique=False,
    )

    op.drop_constraint(
        "uq_expert_assignments_competition_expert_skill_zone",
        "expert_assignments",
        type_="unique",
    )
    op.alter_column(
        "expert_assignments",
        "zone_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_index(
        "uq_expert_assignments_comp_expert_skill_zone_not_null",
        "expert_assignments",
        ["competition_id", "expert_id", "skill_id", "zone_id"],
        unique=True,
        postgresql_where=sa.text("zone_id IS NOT NULL"),
    )
    op.create_index(
        "uq_expert_assignments_comp_expert_skill_all_zones",
        "expert_assignments",
        ["competition_id", "expert_id", "skill_id"],
        unique=True,
        postgresql_where=sa.text("zone_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_expert_assignments_comp_expert_skill_all_zones",
        table_name="expert_assignments",
    )
    op.drop_index(
        "uq_expert_assignments_comp_expert_skill_zone_not_null",
        table_name="expert_assignments",
    )
    op.execute("DELETE FROM expert_assignments WHERE zone_id IS NULL")
    op.alter_column(
        "expert_assignments",
        "zone_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_expert_assignments_competition_expert_skill_zone",
        "expert_assignments",
        ["competition_id", "expert_id", "skill_id", "zone_id"],
    )

    op.drop_index(op.f("ix_expert_skill_areas_expert_id"), table_name="expert_skill_areas")
    op.drop_index(op.f("ix_expert_skill_areas_catalog_skill_id"), table_name="expert_skill_areas")
    op.drop_table("expert_skill_areas")
