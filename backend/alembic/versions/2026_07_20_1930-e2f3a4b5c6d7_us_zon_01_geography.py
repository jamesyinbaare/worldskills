"""US-ZON-01 — regions catalog, cycle region-zone map, geography columns.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-20 19:30:00.000000
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GHANA_REGIONS = (
    "Ashanti",
    "Bono",
    "Bono East",
    "Ahafo",
    "Central",
    "Eastern",
    "Greater Accra",
    "Northern",
    "North East",
    "Savannah",
    "Upper East",
    "Upper West",
    "Volta",
    "Oti",
    "Western",
    "Western North",
)


def upgrade() -> None:
    op.create_table(
        "regions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("name", name="uq_regions_name"),
    )

    conn = op.get_bind()
    first_region_id: str | None = None
    for name in _GHANA_REGIONS:
        rid = str(uuid.uuid4())
        if first_region_id is None:
            first_region_id = rid
        conn.execute(
            sa.text(
                "INSERT INTO regions (id, name, active, created_at) VALUES (:id, :name, true, CURRENT_TIMESTAMP)"
            ),
            {"id": rid, "name": name},
        )

    op.create_table(
        "cycle_region_zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("cycle_id", "region_id", name="uq_cycle_region_zones_cycle_region"),
    )
    op.create_index("ix_cycle_region_zones_cycle_id", "cycle_region_zones", ["cycle_id"])
    op.create_index("ix_cycle_region_zones_region_id", "cycle_region_zones", ["region_id"])
    op.create_index("ix_cycle_region_zones_zone_id", "cycle_region_zones", ["zone_id"])

    op.add_column(
        "institutions",
        sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_institutions_region_id_regions",
        "institutions",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_institutions_region_id", "institutions", ["region_id"])

    if first_region_id:
        conn.execute(
            sa.text("UPDATE institutions SET region_id = :rid WHERE region_id IS NULL"),
            {"rid": first_region_id},
        )

    op.add_column(
        "competitors",
        sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_competitors_region_id_regions",
        "competitors",
        "regions",
        ["region_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_competitors_region_id", "competitors", ["region_id"])

    op.add_column(
        "stages",
        sa.Column("selection_mode", sa.String(length=32), nullable=False, server_default="PER_ZONE"),
    )


def downgrade() -> None:
    op.drop_column("stages", "selection_mode")
    op.drop_index("ix_competitors_region_id", table_name="competitors")
    op.drop_constraint("fk_competitors_region_id_regions", "competitors", type_="foreignkey")
    op.drop_column("competitors", "region_id")
    op.drop_index("ix_institutions_region_id", table_name="institutions")
    op.drop_constraint("fk_institutions_region_id_regions", "institutions", type_="foreignkey")
    op.drop_column("institutions", "region_id")
    op.drop_index("ix_cycle_region_zones_zone_id", table_name="cycle_region_zones")
    op.drop_index("ix_cycle_region_zones_region_id", table_name="cycle_region_zones")
    op.drop_index("ix_cycle_region_zones_cycle_id", table_name="cycle_region_zones")
    op.drop_table("cycle_region_zones")
    op.drop_table("regions")
