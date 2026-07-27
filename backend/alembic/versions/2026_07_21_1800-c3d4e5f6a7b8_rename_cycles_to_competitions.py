"""Rename cycles → competitions and cycle_id → competition_id.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-21 18:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Child tables that keep a FK competition_id → competitions.id after rename.
# Association tables appear under their *post-rename* names.
FK_CHILD_TABLES = (
    "age_rules",
    "pathways",
    "marking_schemes",
    "skills",
    "zones",
    "competition_region_zones",
    "expert_assignments",
    "competitors",
    "registration_windows",
    "registration_form_definitions",
    "idempotency_records",
    "institution_competition_memberships",
    "nomination_limits",
    "nominations",
    "submissions",
    "stages",
    "exercises",
    "shortlists",
    "lifecycle_configs",
    "appeals_configs",
    "appeal_cases",
    "venues",
    "schedule_sessions",
    "health_safety_incidents",
    "public_portal_configs",
    "results_configs",
    "certificate_templates",
    "result_publications",
    "certificates",
    "dsar_jobs",
)

# Unique / index names that models expect after rename (optional but keeps schema tidy).
CONSTRAINT_RENAMES = (
    ("uq_skills_cycle_id_name", "uq_skills_competition_id_name"),
    ("uq_skills_cycle_id_catalog_skill_id", "uq_skills_competition_id_catalog_skill_id"),
    ("uq_competitors_cycle_id_ref_no", "uq_competitors_competition_id_ref_no"),
    ("uq_competitors_cycle_id_user_id", "uq_competitors_competition_id_user_id"),
    ("uq_venues_cycle_id_name", "uq_venues_competition_id_name"),
    ("uq_zones_cycle_id_name", "uq_zones_competition_id_name"),
    ("uq_idempotency_records_cycle_key", "uq_idempotency_records_competition_key"),
    ("uq_cycle_region_zones_cycle_region", "uq_competition_region_zones_competition_region"),
    (
        "uq_institution_cycle_memberships_cycle_institution",
        "uq_institution_competition_memberships_competition_institution",
    ),
    (
        "uq_nomination_limits_cycle_institution_skill",
        "uq_nomination_limits_competition_institution_skill",
    ),
    (
        "uq_expert_assignments_cycle_expert_skill_zone",
        "uq_expert_assignments_competition_expert_skill_zone",
    ),
)


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :name
                """
            ),
            {"name": name},
        ).scalar()
    )


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table
                  AND column_name = :column
                """
            ),
            {"table": table, "column": column},
        ).scalar()
    )


def _drop_fks_referencing(conn, referenced_table: str) -> None:
    rows = conn.execute(
        text(
            """
            SELECT con.conname AS constraint_name, rel.relname AS table_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
            JOIN pg_class ref ON ref.oid = con.confrelid
            WHERE con.contype = 'f'
              AND nsp.nspname = 'public'
              AND ref.relname = :referenced_table
            """
        ),
        {"referenced_table": referenced_table},
    ).mappings().all()
    for row in rows:
        conn.execute(
            text(
                f'ALTER TABLE "{row["table_name"]}" '
                f'DROP CONSTRAINT IF EXISTS "{row["constraint_name"]}"'
            )
        )


def _rename_column_cycle_id(conn) -> list[str]:
    """Rename cycle_id → competition_id on every public table that still has it."""
    tables = [
        row[0]
        for row in conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name = 'cycle_id'
                ORDER BY table_name
                """
            )
        )
    ]
    for table in tables:
        conn.execute(text(f'ALTER TABLE "{table}" RENAME COLUMN cycle_id TO competition_id'))
    return tables


def _rename_indexes_containing_cycle(conn) -> None:
    rows = conn.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public' AND indexname LIKE '%cycle%'
            """
        )
    ).all()
    for (indexname,) in rows:
        new_name = (
            indexname.replace("cycle_id", "competition_id")
            .replace("cycle_region", "competition_region")
            .replace("cycle_institution", "competition_institution")
            .replace("_cycle_", "_competition_")
        )
        if new_name != indexname:
            conn.execute(text(f'ALTER INDEX IF EXISTS "{indexname}" RENAME TO "{new_name}"'))


def _rename_constraints(conn) -> None:
    for old, new in CONSTRAINT_RENAMES:
        row = conn.execute(
            text(
                """
                SELECT rel.relname AS table_name
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                WHERE con.conname = :old
                LIMIT 1
                """
            ),
            {"old": old},
        ).mappings().first()
        if not row:
            continue
        exists_new = conn.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname = :new"),
            {"new": new},
        ).scalar()
        if exists_new:
            continue
        conn.execute(
            text(
                f'ALTER TABLE "{row["table_name"]}" '
                f'RENAME CONSTRAINT "{old}" TO "{new}"'
            )
        )


def _recreate_competition_fks(conn) -> None:
    for table in FK_CHILD_TABLES:
        if not _table_exists(conn, table):
            continue
        if not _column_exists(conn, table, "competition_id"):
            continue
        fk_name = f"fk_{table}_competition_id_competitions"
        conn.execute(
            text(
                f'ALTER TABLE "{table}" '
                f'DROP CONSTRAINT IF EXISTS "{fk_name}"'
            )
        )
        conn.execute(
            text(
                f'ALTER TABLE "{table}" '
                f'ADD CONSTRAINT "{fk_name}" '
                f'FOREIGN KEY (competition_id) REFERENCES competitions(id) ON DELETE CASCADE'
            )
        )


def upgrade() -> None:
    conn = op.get_bind()

    # Drop FKs pointing at cycles (query catalog — do not try/except failed DDL).
    if _table_exists(conn, "cycles"):
        _drop_fks_referencing(conn, "cycles")
        conn.execute(text('ALTER TABLE cycles RENAME TO competitions'))
    elif not _table_exists(conn, "competitions"):
        raise RuntimeError("Neither cycles nor competitions table exists")

    if _table_exists(conn, "cycle_region_zones"):
        conn.execute(text("ALTER TABLE cycle_region_zones RENAME TO competition_region_zones"))
    if _table_exists(conn, "institution_cycle_memberships"):
        conn.execute(
            text(
                "ALTER TABLE institution_cycle_memberships "
                "RENAME TO institution_competition_memberships"
            )
        )

    _rename_column_cycle_id(conn)
    _rename_indexes_containing_cycle(conn)
    _rename_constraints(conn)
    _recreate_competition_fks(conn)

    conn.execute(
        text(
            """
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cyclestatus')
                 AND NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'competitionstatus') THEN
                ALTER TYPE cyclestatus RENAME TO competitionstatus;
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    if _table_exists(conn, "competitions"):
        _drop_fks_referencing(conn, "competitions")

    # Rename competition_id → cycle_id
    tables = [
        row[0]
        for row in conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND column_name = 'competition_id'
                ORDER BY table_name
                """
            )
        )
    ]
    for table in tables:
        conn.execute(
            text(f'ALTER TABLE "{table}" RENAME COLUMN competition_id TO cycle_id')
        )

    if _table_exists(conn, "competition_region_zones"):
        conn.execute(text("ALTER TABLE competition_region_zones RENAME TO cycle_region_zones"))
    if _table_exists(conn, "institution_competition_memberships"):
        conn.execute(
            text(
                "ALTER TABLE institution_competition_memberships "
                "RENAME TO institution_cycle_memberships"
            )
        )

    if _table_exists(conn, "competitions"):
        conn.execute(text("ALTER TABLE competitions RENAME TO cycles"))

    # Recreate FKs to cycles for tables that still have cycle_id
    child_tables_old = [
        t.replace("competition_region_zones", "cycle_region_zones").replace(
            "institution_competition_memberships", "institution_cycle_memberships"
        )
        for t in FK_CHILD_TABLES
    ]
    for table in child_tables_old:
        if not _table_exists(conn, table) or not _column_exists(conn, table, "cycle_id"):
            continue
        fk_name = f"fk_{table}_cycle_id_cycles"
        conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{fk_name}"'))
        conn.execute(
            text(
                f'ALTER TABLE "{table}" '
                f'ADD CONSTRAINT "{fk_name}" '
                f'FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE'
            )
        )

    conn.execute(
        text(
            """
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'competitionstatus')
                 AND NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cyclestatus') THEN
                ALTER TYPE competitionstatus RENAME TO cyclestatus;
              END IF;
            END $$;
            """
        )
    )
