"""US-SCH-01: venues, schedule sessions, slot assignments, H&S incidents."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "venues",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("zone_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("workstations", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["zones.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cycle_id", "name", name="uq_venues_cycle_id_name"),
    )
    op.create_index("ix_venues_cycle_id", "venues", ["cycle_id"])
    op.create_index("ix_venues_zone_id", "venues", ["zone_id"])

    op.create_table(
        "schedule_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("workstations", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedule_sessions_cycle_id", "schedule_sessions", ["cycle_id"])
    op.create_index("ix_schedule_sessions_venue_id", "schedule_sessions", ["venue_id"])

    op.create_table(
        "slot_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("workstation", sa.String(length=64), nullable=False),
        sa.Column("readiness", sa.String(length=32), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("assigned_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["schedule_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "competitor_id", name="uq_slot_assignments_session_competitor"),
        sa.UniqueConstraint("session_id", "workstation", name="uq_slot_assignments_session_workstation"),
    )
    op.create_index("ix_slot_assignments_session_id", "slot_assignments", ["session_id"])
    op.create_index("ix_slot_assignments_competitor_id", "slot_assignments", ["competitor_id"])

    op.create_table(
        "health_safety_incidents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("recorded_by", sa.UUID(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["schedule_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_safety_incidents_session_id", "health_safety_incidents", ["session_id"])
    op.create_index("ix_health_safety_incidents_cycle_id", "health_safety_incidents", ["cycle_id"])


def downgrade() -> None:
    op.drop_index("ix_health_safety_incidents_cycle_id", table_name="health_safety_incidents")
    op.drop_index("ix_health_safety_incidents_session_id", table_name="health_safety_incidents")
    op.drop_table("health_safety_incidents")

    op.drop_index("ix_slot_assignments_competitor_id", table_name="slot_assignments")
    op.drop_index("ix_slot_assignments_session_id", table_name="slot_assignments")
    op.drop_table("slot_assignments")

    op.drop_index("ix_schedule_sessions_venue_id", table_name="schedule_sessions")
    op.drop_index("ix_schedule_sessions_cycle_id", table_name="schedule_sessions")
    op.drop_table("schedule_sessions")

    op.drop_index("ix_venues_zone_id", table_name="venues")
    op.drop_index("ix_venues_cycle_id", table_name="venues")
    op.drop_table("venues")
