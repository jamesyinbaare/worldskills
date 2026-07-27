"""US-SUB-01 — exercises table; backfill from stages.scheme_id.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-07-20 18:30:00.000000
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("brief", sa.Text(), nullable=True),
        sa.Column("deliverables", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("late_policy", sa.String(length=32), nullable=True),
        sa.Column("timed_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["stage_id"], ["stages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scheme_id"], ["marking_schemes.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("stage_id", name="uq_exercises_stage_id"),
    )
    op.create_index("ix_exercises_stage_id", "exercises", ["stage_id"])
    op.create_index("ix_exercises_cycle_id", "exercises", ["cycle_id"])

    # Backfill 1:1 Exercise from existing stages that have a scheme (published).
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, cycle_id, name, scheme_id, submission_rules
            FROM stages
            WHERE scheme_id IS NOT NULL
            """
        )
    ).fetchall()
    for row in rows:
        stage_id, cycle_id, name, scheme_id, submission_rules = row
        deliverables: list = []
        late_policy = None
        timed = None
        if isinstance(submission_rules, str):
            try:
                submission_rules = json.loads(submission_rules)
            except json.JSONDecodeError:
                submission_rules = None
        if isinstance(submission_rules, dict):
            late_policy = submission_rules.get("latePolicy")
            timed = submission_rules.get("timedDurationSeconds")
            for item in submission_rules.get("requiredDeliverables") or []:
                if not isinstance(item, dict) or not item.get("code"):
                    continue
                max_mb = item.get("maxMb")
                max_bytes = int(max_mb) * 1024 * 1024 if max_mb else None
                deliverables.append(
                    {
                        "code": item["code"],
                        "label": item.get("label"),
                        "required": True,
                        "allowedTypes": item.get("formats") or [],
                        "maxSizeBytes": max_bytes,
                    }
                )
        if not deliverables:
            deliverables = [
                {
                    "code": "main",
                    "label": "Main deliverable",
                    "required": True,
                    "allowedTypes": ["pdf", "zip"],
                    "maxSizeBytes": None,
                }
            ]
        conn.execute(
            sa.text(
                """
                INSERT INTO exercises (
                    id, stage_id, cycle_id, title, brief, deliverables, status,
                    scheme_id, late_policy, timed_duration_seconds, created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), :stage_id, :cycle_id, :title, NULL,
                    CAST(:deliverables AS json), 'PUBLISHED', :scheme_id,
                    :late_policy, :timed, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "stage_id": stage_id,
                "cycle_id": cycle_id,
                "title": name or "Exercise",
                "deliverables": json.dumps(deliverables),
                "scheme_id": scheme_id,
                "late_policy": late_policy,
                "timed": timed,
            },
        )

    # Drop legacy stage.scheme_id — scheme now lives on exercises.
    # Constraint name varies by migration history (alembic vs create_all).
    conn = op.get_bind()
    fk_name = conn.execute(
        sa.text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'stages'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'scheme_id'
            LIMIT 1
            """
        )
    ).scalar()
    if fk_name:
        op.drop_constraint(fk_name, "stages", type_="foreignkey")
    op.drop_column("stages", "scheme_id")


def downgrade() -> None:
    op.add_column(
        "stages",
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_stages_scheme_id_marking_schemes",
        "stages",
        "marking_schemes",
        ["scheme_id"],
        ["id"],
        ondelete="SET NULL",
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE stages AS s
            SET scheme_id = e.scheme_id
            FROM exercises AS e
            WHERE e.stage_id = s.id AND e.scheme_id IS NOT NULL
            """
        )
    )
    op.drop_index("ix_exercises_cycle_id", table_name="exercises")
    op.drop_index("ix_exercises_stage_id", table_name="exercises")
    op.drop_table("exercises")
