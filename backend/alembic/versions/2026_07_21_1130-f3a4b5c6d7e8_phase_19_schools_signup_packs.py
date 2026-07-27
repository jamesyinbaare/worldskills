"""Phase 1.9 — Institution.code, competitor user uniqueness, exercise pack, scheme document.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-21 11:30:00.000000
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("institutions", sa.Column("code", sa.String(length=64), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM institutions WHERE code IS NULL")).fetchall()
    for (inst_id,) in rows:
        code = f"LEGACY-{str(inst_id)[:8]}"
        conn.execute(
            sa.text("UPDATE institutions SET code = :code WHERE id = :id"),
            {"code": code, "id": inst_id},
        )
    op.alter_column("institutions", "code", nullable=False)
    op.create_unique_constraint("uq_institutions_code", "institutions", ["code"])

    # Backfill region_id for any orphan institutions using first active region
    first_region = conn.execute(
        sa.text("SELECT id FROM regions WHERE active IS TRUE ORDER BY name LIMIT 1")
    ).fetchone()
    if first_region:
        conn.execute(
            sa.text("UPDATE institutions SET region_id = :rid WHERE region_id IS NULL"),
            {"rid": first_region[0]},
        )
    op.alter_column("institutions", "region_id", nullable=False)

    op.create_unique_constraint(
        "uq_competitors_cycle_id_user_id", "competitors", ["cycle_id", "user_id"]
    )

    op.add_column("exercises", sa.Column("pack_object_key", sa.String(length=512), nullable=True))
    op.add_column("exercises", sa.Column("pack_file_name", sa.String(length=255), nullable=True))
    op.add_column("exercises", sa.Column("pack_content_type", sa.String(length=120), nullable=True))
    op.add_column("exercises", sa.Column("pack_scan_status", sa.String(length=32), nullable=True))

    op.add_column(
        "marking_schemes", sa.Column("document_object_key", sa.String(length=512), nullable=True)
    )
    op.add_column(
        "marking_schemes", sa.Column("document_file_name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "marking_schemes", sa.Column("document_content_type", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "marking_schemes", sa.Column("document_scan_status", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("marking_schemes", "document_scan_status")
    op.drop_column("marking_schemes", "document_content_type")
    op.drop_column("marking_schemes", "document_file_name")
    op.drop_column("marking_schemes", "document_object_key")

    op.drop_column("exercises", "pack_scan_status")
    op.drop_column("exercises", "pack_content_type")
    op.drop_column("exercises", "pack_file_name")
    op.drop_column("exercises", "pack_object_key")

    op.drop_constraint("uq_competitors_cycle_id_user_id", "competitors", type_="unique")
    op.drop_constraint("uq_institutions_code", "institutions", type_="unique")
    op.drop_column("institutions", "code")
