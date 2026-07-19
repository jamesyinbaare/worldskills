"""Phase 0 schema evolution: roles, cycles, config entities, audit."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "8a56fe232f0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expand userrole enum values
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'ADMIN'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'CHIEF_EXPERT'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'EXPERT'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'MODERATOR'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'INSTITUTION'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'COMPETITOR'")

    cyclestatus = postgresql.ENUM(
        "DRAFT", "ACTIVE", "LOCKED", "CLOSED", name="cyclestatus", create_type=False
    )
    cyclestatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "cycles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("DRAFT", "ACTIVE", "LOCKED", "CLOSED", name="cyclestatus", create_type=False),
            nullable=False,
        ),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("organising_body", sa.JSON(), nullable=True),
        sa.Column("branding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cycles")),
    )
    op.create_index(op.f("ix_cycles_name"), "cycles", ["name"], unique=False)

    op.create_table(
        "age_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("max_age", sa.Integer(), nullable=False),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], name=op.f("fk_age_rules_cycle_id_cycles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_age_rules")),
    )
    op.create_index(op.f("ix_age_rules_cycle_id"), "age_rules", ["cycle_id"], unique=False)

    op.create_table(
        "pathways",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], name=op.f("fk_pathways_cycle_id_cycles"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pathways")),
    )
    op.create_index(op.f("ix_pathways_cycle_id"), "pathways", ["cycle_id"], unique=False)

    op.create_table(
        "marking_schemes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["cycles.id"], name=op.f("fk_marking_schemes_cycle_id_cycles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marking_schemes")),
    )
    op.create_index(op.f("ix_marking_schemes_cycle_id"), "marking_schemes", ["cycle_id"], unique=False)

    op.create_table(
        "skills",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=True),
        sa.Column("family_id", sa.String(length=64), nullable=True),
        sa.Column("age_rule_id", sa.UUID(), nullable=True),
        sa.Column("pathway_id", sa.UUID(), nullable=True),
        sa.Column("scheme_id", sa.UUID(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["age_rule_id"], ["age_rules.id"], name=op.f("fk_skills_age_rule_id_age_rules"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], name=op.f("fk_skills_cycle_id_cycles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pathway_id"], ["pathways.id"], name=op.f("fk_skills_pathway_id_pathways"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["scheme_id"], ["marking_schemes.id"], name=op.f("fk_skills_scheme_id_marking_schemes"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("cycle_id", "name", name="uq_skills_cycle_id_name"),
    )
    op.create_index(op.f("ix_skills_cycle_id"), "skills", ["cycle_id"], unique=False)

    op.create_table(
        "stages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("skill_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("stage_type", sa.String(length=64), nullable=False),
        sa.Column("opens_at", sa.DateTime(), nullable=True),
        sa.Column("closes_at", sa.DateTime(), nullable=True),
        sa.Column("quota", sa.Integer(), nullable=True),
        sa.Column("min_score", sa.Integer(), nullable=True),
        sa.Column("scheme_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["cycle_id"], ["cycles.id"], name=op.f("fk_stages_cycle_id_cycles"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["scheme_id"], ["marking_schemes.id"], name=op.f("fk_stages_scheme_id_marking_schemes"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], name=op.f("fk_stages_skill_id_skills"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stages")),
    )
    op.create_index(op.f("ix_stages_cycle_id"), "stages", ["cycle_id"], unique=False)
    op.create_index(op.f("ix_stages_skill_id"), "stages", ["skill_id"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("actor_role", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_events_cycle_id"), "audit_events", ["cycle_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_cycle_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_stages_skill_id"), table_name="stages")
    op.drop_index(op.f("ix_stages_cycle_id"), table_name="stages")
    op.drop_table("stages")
    op.drop_index(op.f("ix_skills_cycle_id"), table_name="skills")
    op.drop_table("skills")
    op.drop_index(op.f("ix_marking_schemes_cycle_id"), table_name="marking_schemes")
    op.drop_table("marking_schemes")
    op.drop_index(op.f("ix_pathways_cycle_id"), table_name="pathways")
    op.drop_table("pathways")
    op.drop_index(op.f("ix_age_rules_cycle_id"), table_name="age_rules")
    op.drop_table("age_rules")
    op.drop_index(op.f("ix_cycles_name"), table_name="cycles")
    op.drop_table("cycles")
    sa.Enum(name="cyclestatus").drop(op.get_bind(), checkfirst=True)
