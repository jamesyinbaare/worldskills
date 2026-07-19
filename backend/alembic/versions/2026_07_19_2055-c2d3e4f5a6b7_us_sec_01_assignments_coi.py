"""US-SEC-01: institutions, zones, assignments, competitors, submissions, scores."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institutions")),
        sa.UniqueConstraint("name", name=op.f("uq_institutions_name")),
    )

    op.add_column("users", sa.Column("institution_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_users_institution_id"), "users", ["institution_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_users_institution_id_institutions"),
        "users",
        "institutions",
        ["institution_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "zones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], name=op.f("fk_zones_cycle_id_cycles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zones")),
        sa.UniqueConstraint("cycle_id", "name", name="uq_zones_cycle_id_name"),
    )
    op.create_index(op.f("ix_zones_cycle_id"), "zones", ["cycle_id"], unique=False)

    op.create_table(
        "expert_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("expert_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("zone_id", sa.UUID(), nullable=False),
        sa.Column("coi_flags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_expert_assignments_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["expert_id"], ["users.id"], name=op.f("fk_expert_assignments_expert_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_expert_assignments_skill_id_skills"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["zone_id"], ["zones.id"], name=op.f("fk_expert_assignments_zone_id_zones"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_expert_assignments")),
        sa.UniqueConstraint(
            "cycle_id",
            "expert_id",
            "skill_id",
            "zone_id",
            name="uq_expert_assignments_cycle_expert_skill_zone",
        ),
    )
    op.create_index(op.f("ix_expert_assignments_cycle_id"), "expert_assignments", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_expert_assignments_expert_id"), "expert_assignments", ["expert_id"], unique=False)
    op.create_index(op.f("ix_expert_assignments_skill_id"), "expert_assignments", ["skill_id"], unique=False)
    op.create_index(op.f("ix_expert_assignments_zone_id"), "expert_assignments", ["zone_id"], unique=False)

    op.create_table(
        "competitors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=False),
        sa.Column("zone_id", sa.UUID(), nullable=False),
        sa.Column("institution_id", sa.UUID(), nullable=True),
        sa.Column("ref_no", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_competitors_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_competitors_skill_id_skills"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["zone_id"], ["zones.id"], name=op.f("fk_competitors_zone_id_zones"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_competitors_institution_id_institutions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competitors")),
    )
    op.create_index(op.f("ix_competitors_cycle_id"), "competitors", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_competitors_skill_id"), "competitors", ["skill_id"], unique=False)
    op.create_index(op.f("ix_competitors_zone_id"), "competitors", ["zone_id"], unique=False)
    op.create_index(op.f("ix_competitors_institution_id"), "competitors", ["institution_id"], unique=False)

    op.create_table(
        "submissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("competitor_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_submissions_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["competitor_id"],
            ["competitors.id"],
            name=op.f("fk_submissions_competitor_id_competitors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submissions")),
    )
    op.create_index(op.f("ix_submissions_cycle_id"), "submissions", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_submissions_competitor_id"), "submissions", ["competitor_id"], unique=False)

    op.create_table(
        "scores",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("submission_id", sa.UUID(), nullable=False),
        sa.Column("assessor_id", sa.UUID(), nullable=False),
        sa.Column("criterion_id", sa.String(length=64), nullable=False),
        sa.Column("raw", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["submissions.id"], name=op.f("fk_scores_submission_id_submissions"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["assessor_id"], ["users.id"], name=op.f("fk_scores_assessor_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scores")),
    )
    op.create_index(op.f("ix_scores_submission_id"), "scores", ["submission_id"], unique=False)
    op.create_index(op.f("ix_scores_assessor_id"), "scores", ["assessor_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scores_assessor_id"), table_name="scores")
    op.drop_index(op.f("ix_scores_submission_id"), table_name="scores")
    op.drop_table("scores")
    op.drop_index(op.f("ix_submissions_competitor_id"), table_name="submissions")
    op.drop_index(op.f("ix_submissions_cycle_id"), table_name="submissions")
    op.drop_table("submissions")
    op.drop_index(op.f("ix_competitors_institution_id"), table_name="competitors")
    op.drop_index(op.f("ix_competitors_zone_id"), table_name="competitors")
    op.drop_index(op.f("ix_competitors_skill_id"), table_name="competitors")
    op.drop_index(op.f("ix_competitors_cycle_id"), table_name="competitors")
    op.drop_table("competitors")
    op.drop_index(op.f("ix_expert_assignments_zone_id"), table_name="expert_assignments")
    op.drop_index(op.f("ix_expert_assignments_skill_id"), table_name="expert_assignments")
    op.drop_index(op.f("ix_expert_assignments_expert_id"), table_name="expert_assignments")
    op.drop_index(op.f("ix_expert_assignments_cycle_id"), table_name="expert_assignments")
    op.drop_table("expert_assignments")
    op.drop_index(op.f("ix_zones_cycle_id"), table_name="zones")
    op.drop_table("zones")
    op.drop_constraint(op.f("fk_users_institution_id_institutions"), "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_institution_id"), table_name="users")
    op.drop_column("users", "institution_id")
    op.drop_table("institutions")
